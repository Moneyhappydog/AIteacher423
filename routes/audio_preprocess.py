"""
音频预处理路由
"""
from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from routes.auth import login_required, get_current_user
import os
import json
import base64
import uuid
import zipfile
import io
import tempfile
import pandas as pd
import logging
import threading
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# 导出进度存储（线程安全）
# 格式: {session_id: {"total": 100, "current": 50, "status": "processing", "message": "添加文件..."}}
export_progress = {}
export_progress_lock = threading.Lock()

# 导入预处理服务
from services.audio_preprocess_service import (
    AudioPreprocessor,
    preprocess_audio,
    get_available_operations as get_audio_operations
)

audio_preprocess_bp = Blueprint('audio_preprocess', __name__, template_folder='../templates')


def verify_user_group(group_id: str) -> bool:
    """
    验证用户是否有权访问指定小组的数据

    Args:
        group_id: 小组ID

    Returns:
        True if user has access, False otherwise
    """
    user = get_current_user()
    if not user:
        return False
    # 教师/管理员可以访问所有小组
    if user.role in ('super_admin', 'teacher'):
        return True
    # 普通用户只能访问自己小组
    if user.group and user.group.group_code == group_id:
        return True
    return False


def get_user_group_id() -> str:
    """获取当前用户所属小组的ID，如果没有则返回空字符串"""
    user = get_current_user()
    if not user or not user.group:
        return ''
    return user.group.group_code


def get_group_audio_dir(group_id: str) -> str:
    """获取小组音频数据目录"""
    return os.path.join(current_app.config.get('DATA_DIR', 'data'), 'audio_data', group_id)


def get_preprocess_output_dir(group_id: str) -> str:
    """获取音频预处理输出目录"""
    output_dir = os.path.join(current_app.config.get('DATA_DIR', 'data'), 'audio_data', group_id, '_preprocessed')
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _generate_audio_labels_csv(audio_dir: str) -> str:
    """从文件名生成音频标签CSV内容"""
    if not os.path.exists(audio_dir):
        return ''

    AUDIO_TO_IDX = {
        'anger': 0, 'fear': 1, 'happy': 2,
        'neutral': 3, 'sad': 4, 'surprise': 5
    }

    rows = []
    for f in os.listdir(audio_dir):
        if not f.endswith('.wav'):
            continue
        # 解析情绪标签
        emotion = None
        parts = f.replace('.wav', '').split('_')
        for part in parts:
            if part in AUDIO_TO_IDX:
                emotion = part
                break
        if emotion:
            rows.append({
                'filename': f,
                'label': emotion,
                'label_idx': AUDIO_TO_IDX[emotion]
            })

    if not rows:
        return ''

    import csv as csv_module
    import io
    output = io.StringIO()
    writer = csv_module.DictWriter(output, fieldnames=['filename', 'label', 'label_idx'])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _update_export_progress(session_id: str, current: int, total: int, status: str, message: str):
    """更新导出进度"""
    with export_progress_lock:
        export_progress[session_id] = {
            'current': current,
            'total': total,
            'status': status,
            'message': message
        }


@audio_preprocess_bp.route('/')
@login_required
def index():
    """渲染音频预处理页面"""
    return render_template('audio_preprocess.html')


@audio_preprocess_bp.route('/export/progress', methods=['GET'])
@login_required
def get_export_progress():
    """获取导出进度"""
    session_id = request.remote_addr
    with export_progress_lock:
        progress = export_progress.get(session_id, {
            'total': 0,
            'current': 0,
            'status': 'idle',
            'message': ''
        })
    return jsonify(progress)


@audio_preprocess_bp.route('/operations', methods=['GET'])
@login_required
def list_operations():
    """获取可用的预处理操作"""
    operations = get_audio_operations()
    return jsonify({
        'success': True,
        'operations': operations
    })


@audio_preprocess_bp.route('/data', methods=['GET'])
@login_required
def get_group_data():
    """
    获取小组的已标注音频数据列表

    Query params:
        group_id: 小组ID（必填）
    """
    group_id = request.args.get('group_id')

    if not group_id:
        # 如果未指定group_id，尝试从当前用户获取
        group_id = get_user_group_id()
        if not group_id:
            return jsonify({'success': False, 'error': '缺少小组ID，且用户未绑定小组'})

    # 验证用户是否有权访问该小组
    if not verify_user_group(group_id):
        return jsonify({'success': False, 'error': '无权访问该小组数据'}), 403

    data_dir = get_group_audio_dir(group_id)

    if not os.path.exists(data_dir):
        return jsonify({
            'success': True,
            'data': [],
            'total': 0,
            'emotion_stats': {}
        })

    # 读取标签CSV
    labels_data = {}

    labels_file = os.path.join(data_dir, 'train_labels.csv')
    if os.path.exists(labels_file):
        try:
            df = pd.read_csv(labels_file)
            for _, row in df.iterrows():
                filename = row['filename']
                emotion = row.get('label', row.get('emotion', ''))
                # 标准化情绪标签（统一使用anger而非angry）
                if emotion == 'angry':
                    emotion = 'anger'
                labels_data[filename] = {
                    'emotion': emotion,
                    'label_idx': row.get('label_idx', '')
                }
        except Exception as e:
            print(f"读取标签文件失败: {e}")

    # 音频情绪标签列表（6类，用于统计）
    AUDIO_EMOTIONS = ['anger', 'fear', 'happy', 'neutral', 'sad', 'surprise']

    # 扫描音频文件
    audio_files = []
    for filename in os.listdir(data_dir):
        if filename.endswith(('.wav', '.mp3', '.webm', '.ogg')) and not filename.startswith('_'):
            filepath = os.path.join(data_dir, filename)
            stat = os.stat(filepath)

            # 获取文件信息
            label_info = labels_data.get(filename, {})

            # 如果CSV中没有，从文件名解析情绪标签
            emotion = label_info.get('emotion', '')
            if not emotion:
                emotion = _parse_emotion_from_filename(filename, AUDIO_EMOTIONS)

            audio_files.append({
                'filename': filename,
                'filepath': filepath,
                'url': f'/audio_data/files/{group_id}/{filename}',
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'emotion': emotion,
                'label_idx': label_info.get('label_idx', '')
            })

    # 按情绪分类统计（确保所有6种情绪都返回）
    emotion_stats = {e: 0 for e in AUDIO_EMOTIONS}
    for info in audio_files:
        emotion = info.get('emotion') or 'unknown'
        # 标准化标签
        if emotion == 'angry':
            emotion = 'anger'
        if emotion in emotion_stats:
            emotion_stats[emotion] += 1
        else:
            emotion_stats['unknown'] = emotion_stats.get('unknown', 0) + 1

    return jsonify({
        'success': True,
        'data': audio_files,
        'total': len(audio_files),
        'emotion_stats': emotion_stats
    })


def _parse_emotion_from_filename(filename: str, emotions: list) -> str:
    """从文件名解析情绪标签"""
    lower_name = filename.lower()
    for emotion in emotions:
        if emotion in lower_name:
            return emotion
    return 'unknown'


@audio_preprocess_bp.route('/preview', methods=['POST'])
@login_required
def preview_preprocess():
    """
    预览预处理效果

    Request body:
    {
        "audio": base64编码的音频,
        "operations": ["trim", "normalize", ...],
        "params": {...}
    }
    """
    try:
        data = request.json
        audio_data = data.get('audio')
        operations = data.get('operations', [])
        params = data.get('params', {})

        if not audio_data:
            return jsonify({'success': False, 'error': '缺少音频数据'})

        # 执行预处理
        result = preprocess_audio(audio_data, operations, params)

        if result.get('success'):
            return jsonify({
                'success': True,
                'original_audio': result['original_audio'],
                'processed_audio': result['processed_audio'],
                'suffix': result.get('suffix', ''),
                'duration': result.get('duration', 0),
                'sample_rate': result.get('sample_rate', 16000),
                'waveform': result.get('waveform', [])
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', '预处理失败')})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@audio_preprocess_bp.route('/batch', methods=['POST'])
@login_required
def batch_preprocess():
    """
    批量预处理音频数据

    Request body:
    {
        "group_id": "G01",
        "operations": ["trim", "normalize", ...],
        "params": {...},
        "file_indices": [0, 1, 2, ...] // 可选，处理指定文件
    }
    """
    try:
        data = request.json
        group_id = data.get('group_id')
        operations = data.get('operations', [])
        params = data.get('params', {})
        file_indices = data.get('file_indices')

        if not group_id:
            return jsonify({'success': False, 'error': '缺少小组ID'})

        # 验证用户是否有权访问该小组
        if not verify_user_group(group_id):
            return jsonify({'success': False, 'error': '无权访问该小组数据'}), 403

        preprocessor = AudioPreprocessor()

        # 获取数据目录
        data_dir = get_group_audio_dir(group_id)
        output_dir = get_preprocess_output_dir(group_id)

        # 读取标签
        labels_file = os.path.join(data_dir, 'train_labels.csv')
        labels_data = []
        original_filenames = []

        if os.path.exists(labels_file):
            try:
                df = pd.read_csv(labels_file)
                for _, row in df.iterrows():
                    labels_data.append({
                        'original_filename': row['filename'],
                        'emotion': row.get('label', row.get('emotion', '')),
                        'label_idx': row.get('label_idx', 0)
                    })
                    original_filenames.append(row['filename'])
            except Exception as e:
                print(f"读取标签失败: {e}")

        # 处理文件
        processed_files = []
        failed_files = []
        suffix = '_'.join(operations) if operations else 'original'

        # 扫描数据目录中的音频
        audio_files = []
        for filename in os.listdir(data_dir):
            if filename.endswith(('.wav', '.mp3', '.webm', '.ogg')) and not filename.startswith('_'):
                audio_files.append(filename)

        # 如果指定了索引，只处理指定文件
        if file_indices:
            audio_files = [audio_files[i] for i in file_indices if i < len(audio_files)]

        # 建立文件名到标签的映射（优先从CSV获取，否则从文件名解析）
        filename_to_label = {}
        for i, orig in enumerate(original_filenames):
            filename_to_label[orig] = labels_data[i]

        # 定义从文件名解析情绪标签的函数
        def parse_emotion_from_filename(filename):
            """从文件名解析情绪标签，如 G01_M01_happy_001.wav -> happy"""
            emotions = ['happy', 'sad', 'angry', 'fear', 'surprise', 'neutral']
            lower_name = filename.lower()
            for emotion in emotions:
                if emotion in lower_name:
                    return emotion
            return 'unknown'

        for filename in audio_files:
            filepath = os.path.join(data_dir, filename)
            try:
                # 加载音频
                audio, sr = preprocessor.load_audio_from_file(filepath)

                # 执行预处理
                processed_audio, output_sr, op_suffix = preprocessor.preprocess_single(
                    audio, sr, operations, params
                )

                # 生成输出文件名
                base_name = os.path.splitext(filename)[0]
                ext = os.path.splitext(filename)[1]
                output_filename = f"{base_name}_{op_suffix}{ext}"
                output_path = os.path.join(output_dir, output_filename)

                # 保存
                import soundfile as sf
                sf.write(output_path, processed_audio, output_sr)

                # 获取标签（优先从CSV，否则从文件名解析）
                # 使用正确的映射重新计算 label_idx
                AUDIO_TO_IDX = {
                    'anger': 0, 'fear': 1, 'happy': 2,
                    'neutral': 3, 'sad': 4, 'surprise': 5
                }
                if filename in filename_to_label:
                    label_info = filename_to_label[filename]
                    emotion = label_info['emotion']
                    # 重新从映射获取 label_idx，确保正确
                    label_idx = AUDIO_TO_IDX.get(emotion, 3)
                else:
                    emotion = parse_emotion_from_filename(filename)
                    label_idx = AUDIO_TO_IDX.get(emotion, 3)

                processed_files.append({
                    'original': filename,
                    'processed': output_filename,
                    'emotion': emotion,
                    'label_idx': label_idx,
                    'duration': float(len(processed_audio) / output_sr)
                })

            except Exception as e:
                print(f"处理文件 {filename} 失败: {e}")
                failed_files.append({'filename': filename, 'error': str(e)})

        # 生成新的标签CSV
        if processed_files:
            processed_labels = []
            for pf in processed_files:
                processed_labels.append({
                    'filename': pf['processed'],
                    'label': pf['emotion'],
                    'label_idx': pf.get('label_idx', 0),
                    'original_filename': pf['original'],
                    'duration': pf.get('duration', 0)
                })

            # 保存标签CSV
            labels_df = pd.DataFrame(processed_labels)
            labels_csv_path = os.path.join(output_dir, 'train_labels.csv')
            labels_df.to_csv(labels_csv_path, index=False)
            print(f"已保存音频标签CSV，包含 {len(processed_labels)} 条记录")

            # 复制原始标签
            if os.path.exists(labels_file):
                import shutil
                shutil.copy(labels_file, os.path.join(output_dir, 'train_labels_original.csv'))

        return jsonify({
            'success': True,
            'processed_count': len(processed_files),
            'failed_count': len(failed_files),
            'output_dir': output_dir,
            'suffix': suffix,
            'processed_files': processed_files[:20],
            'failed_files': failed_files
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@audio_preprocess_bp.route('/export', methods=['POST'])
@login_required
def export_data():
    """
    导出预处理后的音频数据（仅导出本次预处理操作生成的文件）

    Request body:
    {
        "group_id": "G01",
        "include_original": true,
        "include_processed": true
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 获取会话标识（使用 IP 地址确保与 progress 接口一致）
    session_id = request.remote_addr
    
    try:
        data = request.json
        group_id = data.get('group_id')
        include_original = data.get('include_original', True)
        include_processed = data.get('include_processed', True)

        if not group_id:
            return jsonify({'success': False, 'error': '缺少小组ID'})

        # 验证用户是否有权访问该小组
        if not verify_user_group(group_id):
            return jsonify({'success': False, 'error': '无权访问该小组数据'}), 403

        data_dir = get_group_audio_dir(group_id)
        output_dir = get_preprocess_output_dir(group_id)
        
        logger.info(f"[Audio Export] Starting export for group {group_id}, include_original={include_original}, include_processed={include_processed}")
        
        # 初始化进度
        _update_export_progress(session_id, 0, 100, 'scanning', '正在扫描文件...')

        # 收集要添加的文件
        files_to_add = []
        
        # 从 CSV 读取需要导出的文件列表
        labels_csv_path = os.path.join(output_dir, 'train_labels.csv')
        
        if include_processed and os.path.exists(labels_csv_path):
            try:
                df = pd.read_csv(labels_csv_path)
                for _, row in df.iterrows():
                    # 获取预处理后的文件名
                    processed_filename = row['filename']
                    processed_filepath = os.path.join(output_dir, processed_filename)
                    
                    if os.path.exists(processed_filepath):
                        files_to_add.append(('processed', processed_filename, processed_filepath))
                    else:
                        logger.warning(f"[Audio Export] Preprocessed file not found: {processed_filepath}")
            except Exception as e:
                logger.error(f"[Audio Export] Failed to read CSV: {e}")
        
        # 只在需要时才扫描原始数据
        if include_original and os.path.exists(data_dir):
            # 从 CSV 中获取原始文件名列表
            original_files_set = set()
            if os.path.exists(labels_csv_path):
                try:
                    df = pd.read_csv(labels_csv_path)
                    if 'original_filename' in df.columns:
                        original_files_set = set(df['original_filename'].tolist())
                except Exception as e:
                    logger.warning(f"[Audio Export] Failed to read original filenames from CSV: {e}")
            
            for filename in os.listdir(data_dir):
                if filename.endswith(('.wav', '.mp3', '.webm', '.ogg')) and not filename.startswith('_'):
                    # 如果 CSV 中有记录，只导出 CSV 中涉及的原文件
                    if original_files_set and filename not in original_files_set:
                        continue
                    filepath = os.path.join(data_dir, filename)
                    files_to_add.append(('original', filename, filepath))
        
        # 添加标签 CSV 文件
        if include_processed and os.path.exists(labels_csv_path):
            files_to_add.append(('processed', 'train_labels.csv', labels_csv_path))
        
        total_files = len(files_to_add)
        _update_export_progress(session_id, 0, total_files, 'processing', f'准备添加 {total_files} 个文件...')
        
        logger.info(f"[Audio Export] Found {total_files} files to add")

        # 使用临时文件
        temp_fd, temp_path = tempfile.mkstemp(suffix='.zip')
        os.close(temp_fd)
        
        temp_file = None
        try:
            temp_file = open(temp_path, 'wb')
            with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, (folder, filename, filepath) in enumerate(files_to_add):
                    zf.write(filepath, f"{folder}/{filename}")
                    
                    # 每添加5个文件或每50ms更新一次进度
                    if i % 5 == 0 or i == total_files - 1:
                        percent = int((i + 1) / total_files * 100) if total_files > 0 else 100
                        _update_export_progress(
                            session_id, 
                            i + 1, 
                            total_files, 
                            'processing', 
                            f'正在打包: {filename} ({i + 1}/{total_files})'
                        )
            
            temp_file.close()
            temp_file = None
            
            file_size = os.path.getsize(temp_path)
            logger.info(f"[Audio Export] ZIP file created successfully, size: {file_size} bytes")
            
            # 更新进度为完成状态
            _update_export_progress(
                session_id, 
                total_files, 
                total_files, 
                'completed', 
                '打包完成，准备下载...'
            )
            
            # 使用 after_this_request 确保请求完成后再删除临时文件
            def cleanup_temp_file(response):
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        logger.info(f"[Audio Export] Cleaned up temp file: {temp_path}")
                    except Exception as e:
                        logger.warning(f"[Audio Export] Failed to cleanup temp file: {e}")
                return response
            
            from flask import after_this_request
            after_this_request(cleanup_temp_file)
            
            return send_file(
                temp_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'audio_preprocessed_{group_id}.zip',
                conditional=True
            )
        
        except Exception as e:
            logger.error(f"[Audio Export] Error during ZIP creation: {e}")
            import traceback
            traceback.print_exc()
            _update_export_progress(session_id, 0, 0, 'error', f'导出失败: {str(e)}')
            return jsonify({'success': False, 'error': f'创建ZIP文件失败: {str(e)}'})
        finally:
            if temp_file and not temp_file.closed:
                temp_file.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@audio_preprocess_bp.route('/preview_file/<filename>', methods=['GET'])
@login_required
def preview_file(filename):
    """预览预处理后的单个音频文件"""
    group_id = request.args.get('group_id', 'G01')

    output_dir = get_preprocess_output_dir(group_id)
    filepath = os.path.join(output_dir, filename)

    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': '文件不存在'})

    return send_file(filepath)


@audio_preprocess_bp.route('/processed_list', methods=['GET'])
@login_required
def processed_list():
    """获取预处理后的音频文件列表"""
    group_id = request.args.get('group_id', 'G01')

    output_dir = get_preprocess_output_dir(group_id)

    if not os.path.exists(output_dir):
        return jsonify({
            'success': True,
            'data': [],
            'total': 0
        })

    files = []
    for filename in os.listdir(output_dir):
        if filename.endswith(('.wav', '.mp3', '.webm', '.ogg', '.csv')):
            filepath = os.path.join(output_dir, filename)
            stat = os.stat(filepath)

            files.append({
                'filename': filename,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'url': f'/audio_preprocess/preview_file/{filename}?group_id={group_id}'
            })

    return jsonify({
        'success': True,
        'data': files,
        'total': len(files),
        'output_dir': output_dir
    })
