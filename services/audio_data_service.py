"""
音频情绪数据采集服务
处理学生采集的音频文件：存储、元数据管理。
声音情绪采集模块以人工标注为主，不在此处调用 HuBERT 等模型做自动预标注。
"""
import os
import json
import shutil
from datetime import datetime
from config import Config

# 与 HuBERT / train_labels.csv 一致的英文标签（文件名中使用）
AUDIO_LABELS_EN = {
    0: 'anger', 1: 'fear', 2: 'happy',
    3: 'neutral', 4: 'sad', 5: 'surprise'
}
AUDIO_LABELS_CN = {
    0: '生气', 1: '害怕', 2: '开心',
    3: '平静', 4: '难过', 5: '惊讶'
}
AUDIO_EMOJI = {
    0: '😠', 1: '😨', 2: '😊',
    3: '😐', 4: '😢', 5: '😮'
}

# 前端常用「生气」对应 angry，存储时统一为 anger
_EMOTION_ALIASES = {'angry': 'anger'}

AUDIO_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'audio_data')
PENDING_DATA_DIR = os.path.join(AUDIO_DATA_DIR, '_pending')
META_FILE = os.path.join(AUDIO_DATA_DIR, 'meta.json')

VALID_CANONICAL_EMOTIONS = {'anger', 'fear', 'happy', 'neutral', 'sad', 'surprise'}
# 解析文件名时同时接受 angry（历史/前端）
VALID_EMOTIONS_PARSE = VALID_CANONICAL_EMOTIONS | {'angry'}


def normalize_audio_emotion(label: str) -> str:
    if not label:
        return 'neutral'
    return _EMOTION_ALIASES.get(label, label)


def _ensure_dir(dir_path):
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def _ensure_group_dir(group_id):
    group_dir = os.path.join(AUDIO_DATA_DIR, group_id)
    _ensure_dir(group_dir)
    return group_dir


def _ensure_pending_dir(group_id):
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    _ensure_dir(pending_dir)
    return pending_dir


def _load_meta():
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "version": "2026-v1",
        "emotion_audio": {
            "total_files": 0,
            "by_label": {},
            "by_group": {},
            "last_updated": None
        }
    }


def _save_meta(meta):
    meta["emotion_audio"]["last_updated"] = datetime.now().isoformat()
    with open(META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _update_meta_count(meta, group_id, label, delta=1):
    if group_id not in meta['emotion_audio']['by_group']:
        meta['emotion_audio']['by_group'][group_id] = {'total': 0, 'by_label': {}}
    meta['emotion_audio']['by_group'][group_id]['total'] += delta

    if label not in meta['emotion_audio']['by_group'][group_id]['by_label']:
        meta['emotion_audio']['by_group'][group_id]['by_label'][label] = 0
    meta['emotion_audio']['by_group'][group_id]['by_label'][label] += delta

    if label not in meta['emotion_audio']['by_label']:
        meta['emotion_audio']['by_label'][label] = 0
    meta['emotion_audio']['by_label'][label] += delta
    meta['emotion_audio']['total_files'] += delta


def save_audio(group_id: str, member_id: str, audio_path: str,
               emotion: str, copy_file: bool = True) -> dict:
    """
    保存采集到的音频文件（情绪由学生在采集页手动选择）
    文件命名：{group_id}_{member_id}_{emotion}_{seq}.wav
    """
    emotion = normalize_audio_emotion(emotion)
    if emotion not in VALID_CANONICAL_EMOTIONS:
        return {'error': f'无效情绪标签: {emotion}'}

    group_dir = _ensure_group_dir(group_id)

    if not os.path.exists(audio_path):
        return {'error': f'源文件不存在: {audio_path}'}

    ext = os.path.splitext(audio_path)[1] or '.wav'

    existing_files = [
        f for f in os.listdir(group_dir)
        if f.startswith(f"{group_id}_{member_id}_{emotion}_") and f.endswith(ext)
    ]
    seq = len(existing_files) + 1

    file_name = f"{group_id}_{member_id}_{emotion}_{seq:03d}{ext}"
    dest_path = os.path.join(group_dir, file_name)

    try:
        if copy_file:
            shutil.copy2(audio_path, dest_path)
        else:
            shutil.move(audio_path, dest_path)
    except Exception as e:
        return {'error': f'文件保存失败: {e}'}

    meta = _load_meta()
    _update_meta_count(meta, group_id, emotion, 1)
    _save_meta(meta)

    return {
        'file_name': file_name,
        'file_path': f'/audio_data/files/{group_id}/{file_name}',
        'emotion': emotion,
        'timestamp': datetime.now().isoformat(),
        'seq': seq
    }


def save_audio_to_pending(group_id: str, member_id: str, audio_path: str,
                          emotion: str = 'pending') -> dict:
    """保存音频到待标注目录，命名：{group_id}_{member_id}_pending_{seq}.wav"""
    pending_dir = _ensure_pending_dir(group_id)

    if not os.path.exists(audio_path):
        return {'error': f'源文件不存在: {audio_path}'}

    ext = os.path.splitext(audio_path)[1] or '.wav'
    existing_files = [
        f for f in os.listdir(pending_dir)
        if f.startswith(f"{group_id}_{member_id}_pending_") and f.endswith(ext)
    ]
    seq = len(existing_files) + 1

    file_name = f"{group_id}_{member_id}_pending_{seq:03d}{ext}"
    dest_path = os.path.join(pending_dir, file_name)

    try:
        shutil.copy2(audio_path, dest_path)
    except Exception as e:
        return {'error': f'文件保存失败: {e}'}

    return {
        'file_name': file_name,
        'file_path': f'/audio_data/files/_pending/{group_id}/{file_name}',
        'emotion': emotion,
        'status': 'pending',
        'member_id': member_id,
        'timestamp': datetime.now().isoformat()
    }


def list_pending_audios(group_id: str) -> list:
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    if not os.path.exists(pending_dir):
        return []

    files = sorted([f for f in os.listdir(pending_dir) if f.endswith('.wav')])
    audios = []
    for f in files:
        parts = f.replace('.wav', '').split('_')
        emotion = 'pending'
        
        # 解析 member_id (第二个部分是 member_id，格式如 M01, M02 等)
        member_id = 'M01'
        if len(parts) >= 2:
            possible_member = parts[1]
            if possible_member.startswith('M') and len(possible_member) >= 3:
                member_id = possible_member
        
        for part in parts:
            if part in VALID_EMOTIONS_PARSE:
                emotion = normalize_audio_emotion(part)
                break

        audios.append({
            'file_name': f,
            'file_path': f'/audio_data/files/_pending/{group_id}/{f}',
            'emotion': emotion,
            'status': 'pending' if emotion == 'pending' else 'labeled',
            'member_id': member_id
        })

    return audios


def move_pending_to_confirmed(group_id: str, file_name: str,
                              confirmed_label: str, member_id: str = 'M01') -> dict:
    confirmed_label = normalize_audio_emotion(confirmed_label)
    if confirmed_label not in VALID_CANONICAL_EMOTIONS:
        return {'error': f'无效情绪标签: {confirmed_label}'}

    src_dir = os.path.join(PENDING_DATA_DIR, group_id)
    src_path = os.path.join(src_dir, file_name)

    if not os.path.exists(src_path):
        return {'error': '文件不存在'}

    dest_dir = _ensure_group_dir(group_id)
    ext = os.path.splitext(file_name)[1] or '.wav'

    existing_files = [
        f for f in os.listdir(dest_dir)
        if f.startswith(f"{group_id}_{member_id}_{confirmed_label}_") and f.endswith(ext)
    ]
    seq = len(existing_files) + 1

    new_file_name = f"{group_id}_{member_id}_{confirmed_label}_{seq:03d}{ext}"
    dest_path = os.path.join(dest_dir, new_file_name)

    try:
        shutil.move(src_path, dest_path)
    except Exception as e:
        return {'error': f'移动文件失败: {e}'}

    meta = _load_meta()
    _update_meta_count(meta, group_id, confirmed_label, 1)
    _save_meta(meta)

    return {
        'success': True,
        'old_name': file_name,
        'new_name': new_file_name,
        'new_path': f'/audio_data/files/{group_id}/{new_file_name}'
    }


def list_group_audios(group_id: str) -> list:
    """列出小组所有已标注音频（包含情绪标签和成员）"""
    group_dir = os.path.join(AUDIO_DATA_DIR, group_id)
    if not os.path.exists(group_dir):
        return []

    files = sorted([f for f in os.listdir(group_dir) if f.endswith('.wav')])
    audios = []
    for f in files:
        parts = f.replace('.wav', '').split('_')
        emotion = 'unknown'
        member_id = 'M01'
        for part in parts:
            if part in VALID_EMOTIONS_PARSE:
                emotion = normalize_audio_emotion(part)
                break
        if len(parts) >= 2 and parts[1].startswith('M'):
            member_id = parts[1]

        audios.append({
            'file_name': f,
            'file_path': f'/audio_data/files/{group_id}/{f}',
            'emotion': emotion,
            'member_id': member_id
        })

    return audios


def get_annotation_queue_from_pending(group_id: str, include_confirmed: bool = False) -> dict:
    pending_dir = os.path.join(PENDING_DATA_DIR, group_id)
    if not os.path.exists(pending_dir):
        return {'pending': [], 'pending_count': 0, 'confirmed_count': 0, 'total': 0}

    files = sorted([f for f in os.listdir(pending_dir) if f.endswith('.wav')])
    pending = []
    confirmed = []

    for f in files:
        parts = f.replace('.wav', '').split('_')
        emotion = 'pending'
        is_confirmed = False

        # 解析 member_id (第二个部分是 member_id，格式如 M01, M02 等)
        member_id = 'M01'
        if len(parts) >= 2:
            possible_member = parts[1]
            if possible_member.startswith('M') and len(possible_member) >= 3:
                member_id = possible_member

        for part in parts:
            if part in VALID_EMOTIONS_PARSE and part != 'pending':
                emotion = normalize_audio_emotion(part)
                is_confirmed = True
                break

        item = {
            'file_name': f,
            'file_path': f'/audio_data/files/_pending/{group_id}/{f}',
            'emotion': emotion,
            'is_confirmed': is_confirmed,
            'is_pending': not is_confirmed,
            'member_id': member_id
        }

        if is_confirmed:
            confirmed.append(item)
        else:
            pending.append(item)

    all_items = pending + confirmed if include_confirmed else pending

    return {
        'pending': all_items if include_confirmed else pending,
        'pending_count': len(pending),
        'confirmed_count': len(confirmed),
        'total': len(files)
    }


def save_annotation(group_id: str, file_name: str, confirmed_label: str,
                    annotator: str = 'student') -> dict:
    """将 pending 中的音频移到正式目录（人工确认标签）"""
    return move_pending_to_confirmed(group_id, file_name, confirmed_label)


def get_annotation_stats(group_id: str) -> dict:
    result = get_annotation_queue_from_pending(group_id)
    meta = _load_meta()
    group_stats = meta['emotion_audio']['by_group'].get(group_id, {})

    return {
        'group_id': group_id,
        'total': result['total'],
        'pending_count': result['pending_count'],
        'confirmed_count': result['confirmed_count'],
        'progress_pct': round(result['confirmed_count'] / result['total'] * 100, 1) if result['total'] > 0 else 0,
        'by_label': group_stats.get('by_label', {})
    }


def get_global_stats() -> dict:
    meta = _load_meta()
    return {
        'total_files': meta['emotion_audio']['total_files'],
        'by_label': meta['emotion_audio']['by_label'],
        'by_group': meta['emotion_audio']['by_group'],
        'last_updated': meta['emotion_audio'].get('last_updated')
    }


def contribute_to_test_set(group_id: str, file_name: str) -> dict:
    test_dir = _ensure_dir(os.path.join(AUDIO_DATA_DIR, '_test_set'))

    src = os.path.join(AUDIO_DATA_DIR, group_id, file_name)
    if not os.path.exists(src):
        return {'error': '源文件不存在'}

    dest = os.path.join(test_dir, f"{group_id}_{file_name}")
    shutil.copy2(src, dest)

    base = f'{group_id}_{file_name}'
    return {
        'success': True,
        'test_set_path': f'/audio_data/files/_test_set/{base}'
    }
