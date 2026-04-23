"""
数据导出路由
支持导出：人脸图片/标签、音频文件/标签、模型文件
"""
import os
import io
import csv
import zipfile
import tempfile
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, session

from config import Config
from routes.auth import login_required

export_bp = Blueprint('export', __name__, url_prefix='/export')

# 导出进度存储（线程安全）
# 格式: {session_id: {"total": 100, "current": 50, "status": "processing", "message": "添加文件..."}}
export_progress = {}
export_progress_lock = threading.Lock()


def _update_export_progress(session_id: str, current: int, total: int, status: str, message: str):
    """更新导出进度"""
    with export_progress_lock:
        export_progress[session_id] = {
            'current': current,
            'total': total,
            'status': status,
            'message': message
        }


def _clear_export_progress(session_id: str):
    """清除导出进度"""
    with export_progress_lock:
        if session_id in export_progress:
            del export_progress[session_id]


@export_bp.route('/')
@login_required
def index():
    """数据导出页面"""
    from flask import render_template
    return render_template('export_data.html')


@export_bp.route('/check_permissions', methods=['GET'])
@login_required
def check_permissions():
    """检查当前用户的导出权限和可导出的数据"""
    role = session.get('role', 'group')
    user_id = session.get('user_id')
    # 确保 group_id 与数据库中的 group_code 一致
    group_id = session.get('group_id')
    if not group_id:
        # 尝试从数据库获取正确的 group_code
        from models import User
        user = User.query.get(user_id)
        if user and user.group:
            group_id = user.group.group_code
        elif user_id:
            # 降级处理：假设 user_id 4 = G01, 5 = G02, ...
            # 但如果数据库中 group_code 是 G01 格式，直接用 username
            if role == 'group':
                user_obj = User.query.get(user_id)
                if user_obj:
                    group_id = user_obj.username  # 用户名就是 G01, G02 等
            if not group_id:
                group_id = f'G{user_id:03d}'
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Export Check] user_id={user_id}, role={role}, group_id={group_id}")
    
    # 检查可导出的数据
    exportable = {
        'face_images': _count_face_images(group_id),
        'face_labels': _has_face_labels(group_id),
        'audio_files': _count_audio_files(group_id),
        'audio_labels': _has_audio_labels(group_id),
        'models': _count_group_models(group_id)
    }
    
    # 检查是否是管理员/教师，可以导出所有小组数据
    is_admin = role in ('super_admin', 'teacher')
    
    return jsonify({
        'role': role,
        'is_admin': is_admin,
        'group_id': group_id,
        'exportable': exportable
    })


@export_bp.route('/progress', methods=['GET'])
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


@export_bp.route('/list_groups', methods=['GET'])
@login_required
def list_groups():
    """列出可导出的所有小组（仅管理员/教师）"""
    role = session.get('role', 'group')
    if role not in ('super_admin', 'teacher'):
        return jsonify({'error': '权限不足'}), 403
    
    groups = []
    
    # 人脸数据目录
    face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data')
    if os.path.exists(face_dir):
        for folder in os.listdir(face_dir):
            if folder.startswith('_'):
                continue
            path = os.path.join(face_dir, folder)
            if os.path.isdir(path):
                groups.append({
                    'group_id': folder,
                    'face_images': _count_files_with_ext(path, '.jpg'),
                    'audio_files': 0
                })
    
    # 音频数据目录
    audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data')
    if os.path.exists(audio_dir):
        for folder in os.listdir(audio_dir):
            if folder.startswith('_'):
                continue
            path = os.path.join(audio_dir, folder)
            if os.path.isdir(path):
                for g in groups:
                    if g['group_id'] == folder:
                        g['audio_files'] = _count_files_with_ext(path, '.wav')
                        break
                else:
                    groups.append({
                        'group_id': folder,
                        'face_images': 0,
                        'audio_files': _count_files_with_ext(path, '.wav')
                    })
    
    return jsonify({'groups': groups})


@export_bp.route('/download', methods=['POST'])
@login_required
def download():
    """
    批量下载选中的数据
    支持的导出类型：
    - face_images: 人脸图片 (zip)
    - face_labels: 人脸标签 (csv)
    - audio_files: 音频文件 (zip)
    - audio_labels: 音频标签 (csv)
    - models: 小组训练模型 (zip)
    """
    data = request.json
    export_types = data.get('types', [])  # ['face_images', 'face_labels', ...]
    group_ids = data.get('groups', [])   # ['G01', 'G02', ...] 或 ['__self__']
    
    role = session.get('role', 'group')
    user_id = session.get('user_id')
    session_id = request.remote_addr  # 用于进度跟踪
    
    # 确保获取正确的 group_id
    current_group = session.get('group_id')
    if not current_group:
        from models import User
        user = User.query.get(user_id)
        if user and user.group:
            current_group = user.group.group_code
        elif role == 'group' and user:
            current_group = user.username  # 用户名就是 G01, G02 等
        if not current_group:
            current_group = f'G{user_id:03d}'
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Export Download] User: {user_id}, Role: {role}, CurrentGroup: {current_group}, RequestedGroups: {group_ids}")
    
    # 普通用户只能导出自己的数据
    if role == 'group':
        group_ids = [current_group]
    
    if not export_types:
        return jsonify({'error': '请选择要导出的数据类型'}), 400
    if not group_ids:
        return jsonify({'error': '请选择要导出的小组'}), 400
    
    # 验证 group_ids 是否有效
    for gid in group_ids:
        face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', gid)
        if not os.path.exists(face_dir):
            logger.warning(f"[Export] Face data directory not found: {face_dir}")
        audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', gid)
        if not os.path.exists(audio_dir):
            logger.warning(f"[Export] Audio data directory not found: {audio_dir}")
    
    # 第一遍扫描：统计要导出的文件数量
    _update_export_progress(session_id, 0, 100, 'scanning', '正在扫描文件...')
    
    files_to_export = []
    for gid in group_ids:
        if 'face_images' in export_types:
            face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', gid)
            if os.path.exists(face_dir) and os.path.isdir(face_dir):
                for f in os.listdir(face_dir):
                    if f.endswith('.jpg'):
                        files_to_export.append(('face', gid, f))
        
        if 'audio_files' in export_types:
            audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', gid)
            if os.path.exists(audio_dir) and os.path.isdir(audio_dir):
                for f in os.listdir(audio_dir):
                    if f.endswith('.wav'):
                        files_to_export.append(('audio', gid, f))
        
        # 标签文件各算1个
        if 'face_labels' in export_types:
            files_to_export.append(('face_label', gid, 'train_labels.csv'))
        if 'audio_labels' in export_types:
            files_to_export.append(('audio_label', gid, 'train_labels.csv'))
        if 'models' in export_types:
            model_dir = os.path.join(Config.EDITOR_WORKSPACE_ROOT, gid)
            if os.path.exists(model_dir):
                for root, dirs, files in os.walk(model_dir):
                    for f in files:
                        if f.endswith(('.h5', '.pt', '.pth', '.pkl', '.joblib', '.onnx', '.json')):
                            files_to_export.append(('model', gid, f))
    
    total_files = len(files_to_export)
    logger.info(f"[Export] Total files to export: {total_files}")
    _update_export_progress(session_id, 0, total_files, 'processing', f'准备导出 {total_files} 个文件...')
    
    # 使用临时文件而不是内存，避免 gevent 协程在大文件传输时的问题
    temp_fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(temp_fd)
    
    temp_file = None
    try:
        temp_file = open(temp_path, 'wb')
        with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            exported_files = []
            
            for idx, (file_type, gid, filename) in enumerate(files_to_export):
                # 更新进度
                if idx % 10 == 0 or idx == total_files - 1:
                    _update_export_progress(
                        session_id, 
                        idx + 1, 
                        total_files, 
                        'processing', 
                        f'正在打包: {filename} ({idx + 1}/{total_files})'
                    )
                
                if file_type == 'face':
                    face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', gid)
                    src_path = os.path.join(face_dir, filename)
                    arcname = f'{gid}/face/{filename}'
                    zf.write(src_path, arcname)
                    exported_files.append(arcname)
                
                elif file_type == 'audio':
                    audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', gid)
                    src_path = os.path.join(audio_dir, filename)
                    arcname = f'{gid}/audio/{filename}'
                    zf.write(src_path, arcname)
                    exported_files.append(arcname)
                
                elif file_type == 'face_label':
                    face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', gid)
                    csv_path = os.path.join(face_dir, 'train_labels.csv')
                    if os.path.exists(csv_path):
                        arcname = f'{gid}/face_labels.csv'
                        zf.write(csv_path, arcname)
                        exported_files.append(arcname)
                    else:
                        csv_content = _generate_face_labels_csv(face_dir)
                        if csv_content:
                            arcname = f'{gid}/face_labels.csv'
                            zf.writestr(arcname, csv_content)
                            exported_files.append(arcname)
                
                elif file_type == 'audio_label':
                    audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', gid)
                    csv_path = os.path.join(audio_dir, 'train_labels.csv')
                    if os.path.exists(csv_path):
                        arcname = f'{gid}/audio_labels.csv'
                        zf.write(csv_path, arcname)
                        exported_files.append(arcname)
                    else:
                        csv_content = _generate_audio_labels_csv(audio_dir)
                        if csv_content:
                            arcname = f'{gid}/audio_labels.csv'
                            zf.writestr(arcname, csv_content)
                            exported_files.append(arcname)
                
                elif file_type == 'model':
                    model_dir = os.path.join(Config.EDITOR_WORKSPACE_ROOT, gid)
                    for root, dirs, files in os.walk(model_dir):
                        for f in files:
                            if f == filename and f.endswith(('.h5', '.pt', '.pth', '.pkl', '.joblib', '.onnx', '.json')):
                                src_path = os.path.join(root, f)
                                rel_path = os.path.relpath(src_path, Config.EDITOR_WORKSPACE_ROOT)
                                arcname = f'{gid}/models/{rel_path}'
                                zf.write(src_path, arcname)
                                exported_files.append(arcname)
            
            # 添加导出清单
            manifest = f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            manifest += f"导出的数据类型: {', '.join(export_types)}\n"
            manifest += f"导出的数据所有者: {', '.join(group_ids)}\n"
            manifest += f"共导出文件数: {len(exported_files)}\n\n"
            manifest += "文件列表:\n"
            if exported_files:
                for f in exported_files:
                    manifest += f"  - {f}\n"
            else:
                manifest += "  (无文件)\n"
            zf.writestr('manifest.txt', manifest)
            
            logger.info(f"[Export] Total exported files: {len(exported_files)}")
        
        temp_file.close()
        temp_file = None
        
        logger.info(f"[Export] ZIP file created successfully, size: {os.path.getsize(temp_path)} bytes")
        
        # 更新进度为完成
        _update_export_progress(
            session_id, 
            total_files, 
            total_files, 
            'completed', 
            '打包完成，准备下载...'
        )
        
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        # 使用 after_this_request 确保请求完成后再删除临时文件
        def cleanup_temp_file(response):
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.info(f"[Export] Cleaned up temp file: {temp_path}")
                except Exception as e:
                    logger.warning(f"[Export] Failed to cleanup temp file: {e}")
            # 清理进度
            _clear_export_progress(session_id)
            return response
        
        from flask import after_this_request
        after_this_request(cleanup_temp_file)
        
        # 使用临时文件发送，避免内存问题导致大文件传输中断
        return send_file(
            temp_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename,
            conditional=True
        )
    
    except Exception as e:
        logger.error(f"[Export] Error during export: {e}")
        _update_export_progress(session_id, 0, total_files, 'error', f'导出失败: {str(e)}')
        raise
    finally:
        # 只关闭文件句柄，文件清理由 after_this_request 在请求完成后处理
        if temp_file and not temp_file.closed:
            temp_file.close()


def _count_face_images(group_id):
    """统计人脸图片数量"""
    face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', group_id)
    if os.path.exists(face_dir):
        return _count_files_with_ext(face_dir, '.jpg')
    return 0


def _count_audio_files(group_id):
    """统计音频文件数量"""
    audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', group_id)
    if os.path.exists(audio_dir):
        return _count_files_with_ext(audio_dir, '.wav')
    return 0


def _count_group_models(group_id):
    """统计小组训练模型数量"""
    model_dir = os.path.join(Config.EDITOR_WORKSPACE_ROOT, group_id)
    count = 0
    if os.path.exists(model_dir):
        for root, dirs, files in os.walk(model_dir):
            for f in files:
                if f.endswith(('.h5', '.pt', '.pth', '.pkl', '.joblib', '.onnx')):
                    count += 1
    return count


def _has_face_labels(group_id):
    """检查是否存在人脸标签文件"""
    face_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', group_id)
    csv_path = os.path.join(face_dir, 'train_labels.csv')
    return os.path.exists(csv_path)


def _has_audio_labels(group_id):
    """检查是否存在音频标签文件"""
    audio_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', group_id)
    csv_path = os.path.join(audio_dir, 'train_labels.csv')
    return os.path.exists(csv_path)


def _count_files_with_ext(dir_path, ext):
    """统计指定扩展名的文件数量"""
    if os.path.exists(dir_path):
        return len([f for f in os.listdir(dir_path) if f.endswith(ext)])
    return 0


def _generate_face_labels_csv(face_dir):
    """生成人脸标签CSV内容"""
    if not os.path.exists(face_dir):
        return None
    
    EMOTION_TO_IDX = {
        'angry': 0, 'disgust': 1, 'fear': 2,
        'happy': 3, 'sad': 4, 'surprise': 5, 'neutral': 6
    }
    
    rows = []
    for f in os.listdir(face_dir):
        if not f.endswith('.jpg'):
            continue
        # 解析情绪标签
        emotion = None
        parts = f.replace('.jpg', '').split('_')
        for part in parts:
            if part in EMOTION_TO_IDX:
                emotion = part
                break
        if emotion:
            rows.append({
                'filename': f,
                'label': emotion,
                'label_idx': EMOTION_TO_IDX[emotion]
            })
    
    if not rows:
        return None
    
    import csv as csv_module
    output = io.StringIO()
    writer = csv_module.DictWriter(output, fieldnames=['filename', 'label', 'label_idx'])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _generate_audio_labels_csv(audio_dir):
    """生成音频标签CSV内容"""
    if not os.path.exists(audio_dir):
        return None
    
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
                'emotion': emotion,
                'emotion_idx': AUDIO_TO_IDX[emotion]
            })
    
    if not rows:
        return None
    
    import csv as csv_module
    output = io.StringIO()
    writer = csv_module.DictWriter(output, fieldnames=['filename', 'emotion', 'emotion_idx'])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
