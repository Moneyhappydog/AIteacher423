"""
音频标签数据管理服务
将学生采集的音频文件生成训练所需的CSV文件，并与代码编辑器工作空间同步
"""
import os
import csv
import re
from datetime import datetime
from config import Config
from services.audio_data_service import (
    AUDIO_DATA_DIR,
    _ensure_group_dir,
    list_group_audios
)


AUDIO_EMOTION_TO_IDX = {
    'anger': 0, 'fear': 1, 'happy': 2,
    'neutral': 3, 'sad': 4, 'surprise': 5,
    'angry': 0,  # 与采集页「生气」一致，写入 CSV 时仍用 anger 索引
}


def generate_group_audio_labels_csv(group_id: str) -> dict:
    """
    为指定小组生成音频训练标签CSV文件
    返回格式：{success, csv_path, total_files, label_distribution}
    """
    group_dir = _ensure_group_dir(group_id)
    csv_path = os.path.join(group_dir, 'train_labels.csv')
    
    label_counts = {}
    
    try:
        audio_files = [
            f for f in os.listdir(group_dir)
            if f.endswith('.wav') and not f.startswith('.')
        ]
        
        rows = []
        for filename in sorted(audio_files):
            emotion = None
            parts = filename.replace('.wav', '').split('_')
            for part in parts:
                if part in AUDIO_EMOTION_TO_IDX:
                    emotion = part
                    break
            
            if emotion and emotion != 'pending':
                label_idx = AUDIO_EMOTION_TO_IDX.get(emotion, 3)
                canon = 'anger' if emotion == 'angry' else emotion
                rows.append({
                    'filename': filename,
                    'emotion': canon,
                    'emotion_idx': label_idx
                })
                label_counts[canon] = label_counts.get(canon, 0) + 1
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['filename', 'emotion', 'emotion_idx'])
            writer.write_header()
            writer.writerows(rows)
        
        return {
            'success': True,
            'csv_path': csv_path,
            'relative_csv_path': f'/data/editor_workspaces/{group_id}/audio/train_labels.csv',
            'total_files': len(rows),
            'label_distribution': label_counts,
            'generated_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'csv_path': None
        }


def generate_all_groups_audio_csv():
    """为所有有数据的小组生成音频标签CSV"""
    results = {}
    
    if not os.path.exists(AUDIO_DATA_DIR):
        return results
    
    for group_folder in os.listdir(AUDIO_DATA_DIR):
        group_path = os.path.join(AUDIO_DATA_DIR, group_folder)
        if os.path.isdir(group_path) and not group_folder.startswith('_'):
            result = generate_group_audio_labels_csv(group_folder)
            results[group_folder] = result
    
    return results


def sync_audios_to_editor_workspace(group_id: str) -> dict:
    """
    将小组采集的音频文件同步到代码编辑器工作空间
    同步内容：
    - 音频文件到 data/editor_workspaces/{group_id}/audio/audios/
    - train_labels.csv 标签文件
    """
    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    group_safe_id = _safe_group_id(group_id)
    audio_data_dir = _ensure_group_dir(group_id)
    
    target_audios_dir = os.path.join(workspace_root, group_safe_id, 'audio', 'audios')
    os.makedirs(target_audios_dir, exist_ok=True)
    
    copied_count = 0
    errors = []
    
    try:
        for filename in os.listdir(audio_data_dir):
            if not filename.endswith('.wav'):
                continue
            
            src_path = os.path.join(audio_data_dir, filename)
            dst_path = os.path.join(target_audios_dir, filename)
            
            try:
                import shutil
                shutil.copy2(src_path, dst_path)
                copied_count += 1
            except Exception as e:
                errors.append(f'{filename}: {str(e)}')
        
        csv_result = generate_group_audio_labels_csv(group_id)
        
        target_csv_path = os.path.join(workspace_root, group_safe_id, 'audio', 'train_labels.csv')
        csv_result['editor_csv_path'] = target_csv_path
        
        return {
            'success': True,
            'group_id': group_id,
            'audios_copied': copied_count,
            'csv_generated': csv_result.get('success', False),
            'csv_path': csv_result.get('csv_path'),
            'editor_csv_path': target_csv_path,
            'total_files': csv_result.get('total_files', 0),
            'label_distribution': csv_result.get('label_distribution', {}),
            'errors': errors if errors else None
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def _safe_group_id(group_id: str) -> str:
    """净化小组ID为目录名"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(group_id))


def get_group_audio_data_summary(group_id: str) -> dict:
    """获取小组音频数据的汇总信息"""
    audio_data_dir = _ensure_group_dir(group_id)
    raw_count = 0
    label_stats = {}
    
    try:
        for filename in os.listdir(audio_data_dir):
            if filename.endswith('.wav') and not filename.startswith('.'):
                raw_count += 1
                parts = filename.replace('.wav', '').split('_')
                for part in parts:
                    if part in AUDIO_EMOTION_TO_IDX:
                        label_stats[part] = label_stats.get(part, 0) + 1
    except Exception:
        pass
    
    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    group_safe_id = _safe_group_id(group_id)
    editor_audio_dir = os.path.join(workspace_root, group_safe_id, 'audio', 'audios')
    editor_count = 0
    editor_csv_exists = False
    
    if os.path.exists(editor_audio_dir):
        for filename in os.listdir(editor_audio_dir):
            if filename.endswith('.wav'):
                editor_count += 1
    
    editor_csv_path = os.path.join(workspace_root, group_safe_id, 'audio', 'train_labels.csv')
    editor_csv_exists = os.path.exists(editor_csv_path)
    
    return {
        'group_id': group_id,
        'raw_data': {
            'total_files': raw_count,
            'by_emotion': label_stats,
            'source_dir': audio_data_dir
        },
        'editor_workspace': {
            'audios_count': editor_count,
            'audios_dir': editor_audio_dir,
            'csv_exists': editor_csv_exists,
            'csv_path': editor_csv_path if editor_csv_exists else None
        }
    }


def get_test_set_stats() -> dict:
    """获取测试集统计信息"""
    test_dir = os.path.join(AUDIO_DATA_DIR, '_test_set')
    if not os.path.exists(test_dir):
        return {
            'total_files': 0,
            'by_group': {},
            'by_label': {},
            'test_dir': test_dir
        }
    
    files = [f for f in os.listdir(test_dir) if f.endswith('.wav')]
    by_group = {}
    by_label = {}
    
    for f in files:
        parts = f.replace('.wav', '').split('_')
        group_id = parts[0] if parts else 'unknown'
        emotion = 'unknown'
        for part in parts:
            if part in AUDIO_EMOTION_TO_IDX:
                emotion = part
                break
        
        by_group[group_id] = by_group.get(group_id, 0) + 1
        by_label[emotion] = by_label.get(emotion, 0) + 1
    
    return {
        'total_files': len(files),
        'by_group': by_group,
        'by_label': by_label,
        'test_dir': test_dir
    }
