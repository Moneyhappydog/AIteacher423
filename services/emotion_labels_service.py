"""
小组标注数据管理服务
将"数据采集"模块采集并标注好的图片生成训练所需的CSV文件
"""
import os
import csv
import json
from datetime import datetime
from config import Config
from services.emotion_data_service import (
    EMOTION_DATA_DIR,
    _ensure_group_dir,
    list_group_images
)


def generate_group_labels_csv(group_id: str) -> dict:
    """
    为指定小组生成训练标签CSV文件
    返回格式：{success, csv_path, total_images, label_distribution}
    """
    group_dir = _ensure_group_dir(group_id)
    csv_path = os.path.join(group_dir, 'train_labels.csv')

    # 情绪标签到数字的映射
    EMOTION_TO_IDX = {
        'angry': 0, 'disgust': 1, 'fear': 2,
        'happy': 3, 'sad': 4, 'surprise': 5, 'neutral': 6
    }

    label_counts = {}

    try:
        # 遍历小组目录下的所有图片文件
        image_files = [f for f in os.listdir(group_dir)
                       if f.endswith('.jpg') and not f.startswith('.')]

        rows = []
        for filename in sorted(image_files):
            # 从文件名解析情绪标签
            # 格式：{group_id}_{member_id}_{emotion}_{seq}.jpg
            parts = filename.replace('.jpg', '').split('_')
            emotion = None
            for part in parts:
                if part in EMOTION_TO_IDX:
                    emotion = part
                    break

            if emotion and emotion != 'pending':
                label_idx = EMOTION_TO_IDX.get(emotion, 6)
                rows.append({
                    'filename': filename,
                    'label': emotion,
                    'label_idx': label_idx
                })

                label_counts[emotion] = label_counts.get(emotion, 0) + 1

        # 写入CSV
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['filename', 'label', 'label_idx'])
            writer.write_header()
            writer.writerows(rows)

        return {
            'success': True,
            'csv_path': csv_path,
            'relative_csv_path': f'/data/editor_workspaces/{group_id}/face/train_labels.csv',
            'total_images': len(rows),
            'label_distribution': label_counts,
            'generated_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'csv_path': None
        }


def generate_all_groups_csv():
    """为所有有数据的小组生成CSV"""
    results = {}
    emotion_face_dir = EMOTION_DATA_DIR

    if not os.path.exists(emotion_face_dir):
        return results

    for group_folder in os.listdir(emotion_face_dir):
        group_path = os.path.join(emotion_face_dir, group_folder)
        if os.path.isdir(group_path) and not group_folder.startswith('_'):
            result = generate_group_labels_csv(group_folder)
            results[group_folder] = result

    return results


def list_group_images(group_id: str) -> list:
    """列出小组目录下所有已标注的图片"""
    group_dir = _ensure_group_dir(group_id)

    EMOTION_TO_IDX = {
        'angry': 0, 'disgust': 1, 'fear': 2,
        'happy': 3, 'sad': 4, 'surprise': 5, 'neutral': 6
    }

    images = []
    try:
        for filename in os.listdir(group_dir):
            if not filename.endswith('.jpg'):
                continue

            # 解析情绪标签
            parts = filename.replace('.jpg', '').split('_')
            emotion = None
            for part in parts:
                if part in EMOTION_TO_IDX:
                    emotion = part
                    break

            if emotion and emotion != 'pending':
                images.append({
                    'filename': filename,
                    'emotion': emotion,
                    'label_idx': EMOTION_TO_IDX.get(emotion, 6),
                    'relative_path': f'/data/editor_workspaces/{group_id}/face/images/{filename}'
                })
    except Exception:
        pass

    return images


def sync_images_to_editor_workspace(group_id: str) -> dict:
    """
    将小组采集的标注图片同步到代码编辑器工作空间
    这样学生可以在编辑器中直接访问自己的数据
    """
    from config import Config

    # 编辑器工作空间路径
    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    group_dir = _safe_group_id(group_id)

    # 表情识别数据目录
    emotion_data_dir = _ensure_group_dir(group_id)

    # 目标目录
    target_images_dir = os.path.join(workspace_root, group_dir, 'face', 'images')
    os.makedirs(target_images_dir, exist_ok=True)

    copied_count = 0
    errors = []

    try:
        # 遍历原始图片并复制
        for filename in os.listdir(emotion_data_dir):
            if not filename.endswith('.jpg'):
                continue

            src_path = os.path.join(emotion_data_dir, filename)
            dst_path = os.path.join(target_images_dir, filename)

            try:
                import shutil
                shutil.copy2(src_path, dst_path)
                copied_count += 1
            except Exception as e:
                errors.append(f'{filename}: {str(e)}')

        # 生成CSV文件
        csv_result = generate_group_labels_csv(group_id)

        # 同时在目标目录生成CSV
        target_csv_path = os.path.join(workspace_root, group_dir, 'face', 'train_labels.csv')
        csv_result['editor_csv_path'] = target_csv_path

        return {
            'success': True,
            'group_id': group_id,
            'images_copied': copied_count,
            'csv_generated': csv_result.get('success', False),
            'csv_path': csv_result.get('csv_path'),
            'editor_csv_path': target_csv_path,
            'total_images': csv_result.get('total_images', 0),
            'label_distribution': csv_result.get('label_distribution', {}),
            'errors': errors if errors else None
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def _safe_group_id(group_id) -> str:
    """净化小组ID为目录名"""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(group_id))


def get_group_data_summary(group_id: str) -> dict:
    """获取小组数据的汇总信息"""
    # 检查原始数据
    emotion_data_dir = _ensure_group_dir(group_id)
    raw_count = 0
    label_stats = {}

    try:
        for filename in os.listdir(emotion_data_dir):
            if filename.endswith('.jpg') and not filename.startswith('.'):
                raw_count += 1
                # 统计各情绪数量
                parts = filename.replace('.jpg', '').split('_')
                for part in parts:
                    if part in ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']:
                        label_stats[part] = label_stats.get(part, 0) + 1
    except Exception:
        pass

    # 检查编辑器工作空间
    workspace_root = Config.EDITOR_WORKSPACE_ROOT
    group_safe_id = _safe_group_id(group_id)
    editor_face_dir = os.path.join(workspace_root, group_safe_id, 'face', 'images')
    editor_count = 0
    editor_csv_exists = False

    if os.path.exists(editor_face_dir):
        for filename in os.listdir(editor_face_dir):
            if filename.endswith('.jpg'):
                editor_count += 1

    editor_csv_path = os.path.join(workspace_root, group_safe_id, 'face', 'train_labels.csv')
    editor_csv_exists = os.path.exists(editor_csv_path)

    return {
        'group_id': group_id,
        'raw_data': {
            'total_images': raw_count,
            'by_emotion': label_stats,
            'source_dir': emotion_data_dir
        },
        'editor_workspace': {
            'images_count': editor_count,
            'images_dir': editor_face_dir,
            'csv_exists': editor_csv_exists,
            'csv_path': editor_csv_path if editor_csv_exists else None
        }
    }
