"""
表情数据采集服务
处理学生采集的表情图片：存储、自动标注、标注管理
"""
import base64
import json
import os
import uuid
from datetime import datetime
from config import Config

# 情绪标签映射（7类，与 face_service.py 保持一致）
EMOTION_LABELS_EN = {
    0: 'angry', 1: 'disgust', 2: 'fear',
    3: 'happy', 4: 'sad', 5: 'surprise', 6: 'neutral'
}
EMOTION_LABELS_CN = {
    0: '生气', 1: '厌恶', 2: '害怕',
    3: '开心', 4: '难过', 5: '惊讶', 6: '平静'
}

EMOTION_EMOJI = {
    0: '😠', 1: '🤢', 2: '😨',
    3: '😊', 4: '😢', 5: '😮', 6: '😐'
}

# 数据目录
EMOTION_DATA_DIR = Config.EMOTION_DATA_DIR
# 待标注临时目录
PENDING_DATA_DIR = os.path.join(EMOTION_DATA_DIR, '_pending')
META_FILE = os.path.join(EMOTION_DATA_DIR, 'meta.json')


def _ensure_pending_dir(group_id):
    """确保待标注目录存在"""
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    os.makedirs(pending_dir, exist_ok=True)
    return pending_dir


def _load_meta():
    """加载元数据文件"""
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "version": "2026-v1",
        "emotion_face": {
            "total_images": 0,
            "by_label": {},
            "by_group": {},
            "last_updated": None
        }
    }


def _save_meta(meta):
    """保存元数据文件"""
    meta["emotion_face"]["last_updated"] = datetime.now().isoformat()
    with open(META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _ensure_group_dir(group_id):
    """确保小组目录存在"""
    group_dir = os.path.join(EMOTION_DATA_DIR, group_id)
    os.makedirs(group_dir, exist_ok=True)
    return group_dir


def auto_label_image(image_b64: str) -> dict:
    """
    使用 face_service 对图片进行自动预标注
    返回：{emotion_idx, emotion_cn, emotion_en, confidence, emoji}
    """
    try:
        from services.face_service import predict_frame
        result = predict_frame(
            image_b64,
            Config.FACE_EMOTION_MODEL,
            Config.DLIB_LANDMARKS_MODEL
        )
        if 'faces' in result and len(result['faces']) > 0:
            face = result['faces'][0]
            idx = face['emotion_idx']
            scores = face.get('scores', [])
            confidence = float(scores[idx]) if scores and idx >= 0 else 0.0
            return {
                'emotion_idx': idx,
                'emotion_cn': EMOTION_LABELS_CN.get(idx, '未知'),
                'emotion_en': EMOTION_LABELS_EN.get(idx, 'unknown'),
                'confidence': confidence,
                'emoji': EMOTION_EMOJI.get(idx, '❓'),
                'has_face': True
            }
        return {'emotion_idx': -1, 'emotion_cn': '未检测到人脸', 'emotion_en': 'no_face',
                'confidence': 0.0, 'emoji': '❓', 'has_face': False}
    except Exception as e:
        return {'emotion_idx': -1, 'emotion_cn': '标注失败', 'emotion_en': 'error',
                'confidence': 0.0, 'emoji': '❓', 'has_face': False, 'error': str(e)}


def save_image(group_id: str, member_id: str, image_b64: str,
               emotion: str, auto_label: dict = None) -> dict:
    """
    保存采集到的表情图片
    文件命名：{group_id}_{member_id}_{emotion}_{seq}.jpg
    返回：{file_name, file_path, auto_label, timestamp}
    """
    group_dir = _ensure_group_dir(group_id)

    # 统计该情绪的序号
    existing_files = [f for f in os.listdir(group_dir)
                      if f.startswith(f"{group_id}_{member_id}_{emotion}_")
                      and f.endswith('.jpg')]
    seq = len(existing_files) + 1

    # 生成文件名
    file_name = f"{group_id}_{member_id}_{emotion}_{seq:03d}.jpg"
    file_path = os.path.join(group_dir, file_name)

    # 解码并保存图片
    try:
        img_data = base64.b64decode(image_b64.split(',')[-1])
        with open(file_path, 'wb') as f:
            f.write(img_data)
    except Exception as e:
        return {'error': f'图片保存失败: {e}'}

    # 更新元数据
    meta = _load_meta()
    if group_id not in meta['emotion_face']['by_group']:
        meta['emotion_face']['by_group'][group_id] = {'total': 0, 'by_label': {}}
    meta['emotion_face']['by_group'][group_id]['total'] += 1
    if emotion not in meta['emotion_face']['by_group'][group_id]['by_label']:
        meta['emotion_face']['by_group'][group_id]['by_label'][emotion] = 0
    meta['emotion_face']['by_group'][group_id]['by_label'][emotion] += 1

    if emotion not in meta['emotion_face']['by_label']:
        meta['emotion_face']['by_label'][emotion] = 0
    meta['emotion_face']['by_label'][emotion] += 1
    meta['emotion_face']['total_images'] += 1
    _save_meta(meta)

    return {
        'file_name': file_name,
        'file_path': f'/data/emotion_data/{group_id}/{file_name}',
        'auto_label': auto_label,
        'timestamp': datetime.now().isoformat(),
        'seq': seq
    }


def save_image_to_pending(group_id: str, member_id: str, image_b64: str,
                          emotion: str = 'pending') -> dict:
    """
    保存图片到待标注临时目录
    文件命名：{group_id}_{member_id}_pending_{uuid}.jpg
    返回：{file_name, file_path, timestamp}
    """
    pending_dir = _ensure_pending_dir(group_id)

    # 生成唯一文件名
    unique_id = uuid.uuid4().hex[:12]
    file_name = f"{group_id}_{member_id}_pending_{unique_id}.jpg"
    file_path = os.path.join(pending_dir, file_name)

    # 解码并保存图片
    try:
        img_data = base64.b64decode(image_b64.split(',')[-1])
        with open(file_path, 'wb') as f:
            f.write(img_data)
    except Exception as e:
        return {'error': f'图片保存失败: {e}'}

    return {
        'file_name': file_name,
        'file_path': f'/data/emotion_data/_pending/{group_id}/{file_name}',
        'emotion': emotion,
        'status': 'pending',
        'member_id': member_id,
        'timestamp': datetime.now().isoformat()
    }


def list_pending_images(group_id: str) -> list:
    """
    列出小组待标注队列（从pending目录）
    """
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    if not os.path.exists(pending_dir):
        return []

    files = sorted([f for f in os.listdir(pending_dir) if f.endswith('.jpg')])

    # 有效情绪标签
    VALID_EMOTIONS = {'happy', 'sad', 'angry', 'surprise', 'fear', 'disgust', 'neutral'}

    images = []
    for f in files:
        # 从文件名解析: {group_id}_{member_id}_{status}_{uuid}.jpg
        parts = f.replace('.jpg', '').split('_')
        is_pending = 'pending' in parts[2:] if len(parts) > 2 else True

        # 解析 member_id (第二个部分是 member_id，格式如 M01, M02 等)
        member_id = 'M01'
        if len(parts) >= 2:
            possible_member = parts[1]
            if possible_member.startswith('M') and len(possible_member) >= 3:
                member_id = possible_member

        item = {
            'file_name': f,
            'file_path': f'/data/emotion_data/_pending/{group_id}/{f}',
            'status': 'pending' if is_pending else 'labeled',
            'is_pending': is_pending,
            'member_id': member_id
        }

        # 尝试解析情绪标签（如果文件名已更新）
        for part in parts:
            if part in VALID_EMOTIONS:
                item['emotion'] = part
                item['is_pending'] = False
                break
        else:
            item['emotion'] = 'pending'

        images.append(item)

    return images


def move_pending_to_confirmed(group_id: str, file_name: str,
                               confirmed_label: str, member_id: str = 'M01') -> dict:
    """
    将待标注图片移动到正式目录，并重命名为正确的情绪标签
    """
    # 源文件路径（pending目录）
    src_dir = os.path.join(PENDING_DATA_DIR, group_id)
    src_path = os.path.join(src_dir, file_name)

    if not os.path.exists(src_path):
        return {'error': '文件不存在'}

    # 目标目录（正式目录）
    dest_dir = _ensure_group_dir(group_id)

    # 统计该情绪的序号
    existing_files = [f for f in os.listdir(dest_dir)
                      if f.startswith(f"{group_id}_{member_id}_{confirmed_label}_")
                      and f.endswith('.jpg')]
    seq = len(existing_files) + 1

    # 生成新文件名
    new_file_name = f"{group_id}_{member_id}_{confirmed_label}_{seq:03d}.jpg"
    dest_path = os.path.join(dest_dir, new_file_name)

    # 移动文件（使用复制+删除，兼容跨目录移动）
    try:
        import shutil
        shutil.copy2(src_path, dest_path)
        os.remove(src_path)
    except Exception as e:
        return {'error': f'移动文件失败: {e}'}

    # 更新元数据
    meta = _load_meta()
    if group_id not in meta['emotion_face']['by_group']:
        meta['emotion_face']['by_group'][group_id] = {'total': 0, 'by_label': {}}

    meta['emotion_face']['by_group'][group_id]['total'] += 1
    if confirmed_label not in meta['emotion_face']['by_group'][group_id]['by_label']:
        meta['emotion_face']['by_group'][group_id]['by_label'][confirmed_label] = 0
    meta['emotion_face']['by_group'][group_id]['by_label'][confirmed_label] += 1

    if confirmed_label not in meta['emotion_face']['by_label']:
        meta['emotion_face']['by_label'][confirmed_label] = 0
    meta['emotion_face']['by_label'][confirmed_label] += 1
    meta['emotion_face']['total_images'] += 1
    _save_meta(meta)

    return {
        'success': True,
        'old_name': file_name,
        'new_name': new_file_name,
        'new_path': f'/data/emotion_data/{group_id}/{new_file_name}'
    }


def confirm_label(group_id: str, file_name: str, confirmed_label: str) -> dict:
    """
    学生确认或修改标注（用于pending目录的图片）
    """
    file_path = os.path.join(PENDING_DATA_DIR, group_id, file_name)
    if not os.path.exists(file_path):
        return {'error': '文件不存在'}

    # 重命名文件（更新情绪标签）
    old_name = file_name
    parts = file_name.replace('.jpg', '').split('_')
    if len(parts) >= 4:
        member_id = parts[1]
        unique_id = parts[-1]  # uuid
        new_name = f"{group_id}_{member_id}_{confirmed_label}_{unique_id}.jpg"
    else:
        new_name = f"{group_id}_M01_{confirmed_label}_001.jpg"

    new_path = os.path.join(PENDING_DATA_DIR, group_id, new_name)
    if old_name != new_name:
        os.rename(file_path, new_path)

    return {'success': True, 'old_name': old_name, 'new_name': new_name}


def list_group_images(group_id: str) -> list:
    """列出小组所有已标注图片（包含情绪标签）"""
    group_dir = os.path.join(EMOTION_DATA_DIR, group_id)
    if not os.path.exists(group_dir):
        return []
    files = sorted([f for f in os.listdir(group_dir) if f.endswith('.jpg')])
    result = []
    for f in files:
        # 命名: {group_id}_{member_id}_{emotion}_{seq}.jpg
        parts = f.replace('.jpg', '').split('_')
        emotion = 'unknown'
        member_id = 'M01'
        if len(parts) >= 3:
            emotion = parts[2] if parts[2] != 'unknown' else 'unknown'
            member_id = parts[1] if parts[1].startswith('M') else 'M01'
        result.append({
            'file_name': f,
            'file_path': f'/data/emotion_data/{group_id}/{f}',
            'emotion': emotion,
            'member_id': member_id
        })
    return result


def get_global_stats() -> dict:
    """获取全班数据统计"""
    meta = _load_meta()
    return {
        'total_images': meta['emotion_face']['total_images'],
        'by_label': meta['emotion_face']['by_label'],
        'by_group': meta['emotion_face']['by_group'],
        'last_updated': meta['emotion_face'].get('last_updated')
    }


def contribute_to_test_set(group_id: str, file_name: str) -> dict:
    """
    将图片贡献到全局测试集
    """
    test_dir = os.path.join(EMOTION_DATA_DIR, '_test_set')
    os.makedirs(test_dir, exist_ok=True)

    src = os.path.join(EMOTION_DATA_DIR, group_id, file_name)
    if not os.path.exists(src):
        return {'error': '源文件不存在'}

    dest = os.path.join(test_dir, f"{group_id}_{file_name}")
    import shutil
    shutil.copy2(src, dest)

    return {'success': True, 'test_set_path': f'/data/emotion_data/_test_set/{group_id}_{file_name}'}


# ============================================================
# 标注工作台专用接口（从pending目录）
# ============================================================

def get_annotation_queue_from_pending(group_id: str, include_confirmed: bool = False) -> dict:
    """
    获取小组待标注队列（从pending目录）
    返回: {pending: [...], pending_count, confirmed_count, total}
    """
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    if not os.path.exists(pending_dir):
        return {'pending': [], 'pending_count': 0, 'confirmed_count': 0, 'total': 0}

    files = sorted([f for f in os.listdir(pending_dir) if f.endswith('.jpg')])

    pending = []
    confirmed = []
    # 有效情绪标签
    VALID_EMOTIONS = {'happy', 'sad', 'angry', 'surprise', 'fear', 'disgust', 'neutral'}

    for f in files:
        # 从文件名解析: {group_id}_{member_id}_{status}_{uuid}.jpg
        parts = f.replace('.jpg', '').split('_')
        if len(parts) >= 4:
            # 查找是pending还是有效情绪
            emotion_in_filename = None
            for part in parts[2:]:
                if part in VALID_EMOTIONS:
                    emotion_in_filename = part
                    break

            is_confirmed = emotion_in_filename is not None
            
            # 解析 member_id (第二个部分是 member_id，格式如 M01, M02 等)
            member_id = 'M01'
            if len(parts) >= 2:
                possible_member = parts[1]
                if possible_member.startswith('M') and len(possible_member) >= 3:
                    member_id = possible_member
            
            item = {
                'file_name': f,
                'file_path': f'/data/emotion_data/_pending/{group_id}/{f}',
                'emotion': emotion_in_filename or 'pending',
                'seq': parts[-1],
                'is_confirmed': is_confirmed,
                'is_pending': not is_confirmed,
                'member_id': member_id
            }

            if is_confirmed:
                confirmed.append(item)
            else:
                pending.append(item)
        else:
            unk_item = {
                'file_name': f,
                'file_path': f'/data/emotion_data/_pending/{group_id}/{f}',
                'emotion': 'pending',
                'seq': '000',
                'is_confirmed': False,
                'is_pending': True,
                'member_id': 'M01'
            }
            pending.append(unk_item)

    if include_confirmed:
        all_items = pending + confirmed
    else:
        all_items = pending

    return {
        'pending': pending if not include_confirmed else all_items,
        'pending_count': len(pending),
        'confirmed_count': len(confirmed),
        'total': len(files)
    }


def get_annotation_queue(group_id: str, include_confirmed: bool = False) -> dict:
    """
    获取小组待标注队列（兼容旧接口，从正式目录读取）
    返回: {pending: [...], pending_count, confirmed_count, total}
    """
    group_dir = os.path.join(EMOTION_DATA_DIR, group_id)
    if not os.path.exists(group_dir):
        return {'pending': [], 'pending_count': 0, 'confirmed_count': 0, 'total': 0}

    files = sorted([f for f in os.listdir(group_dir) if f.endswith('.jpg')])

    pending = []
    confirmed = []
    # 有效情绪标签（学生已确认的标注）
    VALID_EMOTIONS = {'happy', 'sad', 'angry', 'surprise', 'fear', 'disgust', 'neutral'}
    for f in files:
        # 从文件名解析: {group_id}_{member_id}_{emotion}_{seq}.jpg
        parts = f.replace('.jpg', '').split('_')
        if len(parts) >= 4:
            emotion = parts[2]
            # 如果是有效情绪标签，说明学生已确认；否则视为待标注
            is_confirmed = emotion in VALID_EMOTIONS
            item = {
                'file_name': f,
                'file_path': f'/data/emotion_data/{group_id}/{f}',
                'emotion': emotion,
                'seq': parts[3] if len(parts) > 3 else '000',
                'is_confirmed': is_confirmed
            }
            if is_confirmed:
                confirmed.append(item)
            else:
                pending.append(item)
        else:
            unk_item = {
                'file_name': f,
                'file_path': f'/data/emotion_data/{group_id}/{f}',
                'emotion': 'unknown',
                'seq': '000',
                'is_confirmed': False
            }
            pending.append(unk_item)

    if include_confirmed:
        all_items = pending + confirmed
    else:
        all_items = pending

    # 每条记录附上当前自动标注（如果有）
    for item in all_items:
        item['auto_label'] = None  # 前端上传时已标注，此处可省略重复调用

    return {
        'pending': pending if not include_confirmed else all_items,
        'pending_count': len(pending),
        'confirmed_count': len(confirmed),
        'total': len(files)
    }


def save_annotation(group_id: str, file_name: str, confirmed_label: str,
                    annotator: str = 'student') -> dict:
    """
    保存学生/教师的正式标注
    - 重命名文件为正确的情绪标签
    - 记录标注历史到 meta.json
    """
    file_path = os.path.join(EMOTION_DATA_DIR, group_id, file_name)
    if not os.path.exists(file_path):
        return {'error': '文件不存在'}

    # 解析文件名
    parts = file_name.replace('.jpg', '').split('_')
    if len(parts) < 4:
        return {'error': '文件名格式不正确'}

    member_id = parts[1]
    seq = parts[3]
    old_emotion = parts[2]

    # 构建新文件名
    new_file_name = f"{group_id}_{member_id}_{confirmed_label}_{seq}.jpg"
    new_path = os.path.join(EMOTION_DATA_DIR, group_id, new_file_name)

    # 重命名
    if file_path != new_path:
        os.rename(file_path, new_path)

    # 更新 meta
    meta = _load_meta()
    if group_id not in meta['emotion_face']['by_group']:
        meta['emotion_face']['by_group'][group_id] = {'total': 0, 'by_label': {}}

    # 旧情绪计数 -1
    if old_emotion in meta['emotion_face']['by_group'][group_id]['by_label']:
        meta['emotion_face']['by_group'][group_id]['by_label'][old_emotion] -= 1

    # 新情绪计数 +1
    if confirmed_label not in meta['emotion_face']['by_group'][group_id]['by_label']:
        meta['emotion_face']['by_group'][group_id]['by_label'][confirmed_label] = 0
    meta['emotion_face']['by_group'][group_id]['by_label'][confirmed_label] += 1

    _save_meta(meta)

    return {
        'success': True,
        'file_name': new_file_name,
        'old_emotion': old_emotion,
        'confirmed_label': confirmed_label,
        'annotator': annotator
    }


def mark_review_needed(group_id: str, file_name: str) -> dict:
    """
    标记图片需要教师审核
    """
    file_path = os.path.join(EMOTION_DATA_DIR, group_id, file_name)
    if not os.path.exists(file_path):
        return {'error': '文件不存在'}

    parts = file_name.replace('.jpg', '').split('_')
    if len(parts) < 4:
        return {'error': '文件名格式不正确'}

    member_id = parts[1]
    seq = parts[3]
    new_file_name = f"{group_id}_{member_id}_review_{seq}.jpg"
    new_path = os.path.join(EMOTION_DATA_DIR, group_id, new_file_name)

    if file_path != new_path:
        os.rename(file_path, new_path)

    return {'success': True, 'file_name': new_file_name, 'status': 'review_needed'}


def get_annotation_stats(group_id: str) -> dict:
    """
    获取小组标注进度统计
    """
    result = get_annotation_queue(group_id)
    by_label = {}
    for item in result.get('pending', []) + (list_group_images(group_id) if False else []):
        emotion = item.get('emotion', 'unknown')
        by_label[emotion] = by_label.get(emotion, 0) + 1

    meta = _load_meta()
    group_stats = meta['emotion_face']['by_group'].get(group_id, {})
    return {
        'group_id': group_id,
        'total': result['total'],
        'pending_count': result['pending_count'],
        'confirmed_count': result['confirmed_count'],
        'progress_pct': round(result['confirmed_count'] / result['total'] * 100, 1) if result['total'] > 0 else 0,
        'by_label': group_stats.get('by_label', {})
    }


def batch_confirm_label(group_id: str, file_names: list, confirmed_label: str) -> dict:
    """
    批量确认标注（用于快速审核）
    """
    results = []
    for fn in file_names:
        res = save_annotation(group_id, fn, confirmed_label, 'batch')
        results.append(res)
    success = sum(1 for r in results if r.get('success'))
    return {'total': len(file_names), 'success': success, 'results': results}
