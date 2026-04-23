"""
音频数据采集路由（声音情绪采集以人工标注为主，不做服务端自动预标注）
"""
from flask import Blueprint, request, jsonify, send_from_directory, session
import os
import uuid

from services.audio_data_service import (
    save_audio,
    save_audio_to_pending,
    list_pending_audios,
    list_group_audios,
    get_global_stats,
    contribute_to_test_set,
    get_annotation_queue_from_pending,
    move_pending_to_confirmed,
    get_annotation_stats,
    AUDIO_DATA_DIR,
    PENDING_DATA_DIR,
)
from services.audio_labels_service import (
    generate_group_audio_labels_csv,
    sync_audios_to_editor_workspace,
    get_group_audio_data_summary,
    get_test_set_stats,
)

from routes.auth import login_required, get_group_member_count_for_session

audio_data_bp = Blueprint('audio_data', __name__, url_prefix='/audio_data')


def _session_group_id():
    user_id = session.get('user_id')
    return session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')


def _ensure_group_access(group_id: str):
    """学生小组只能访问本组数据；教师/超管可查看任意小组。"""
    role = session.get('role', 'group')
    if role == 'group':
        gid = _session_group_id()
        if group_id != gid:
            return jsonify({'error': '无权访问其他小组数据'}), 403
    return None


@audio_data_bp.route('/collect/')
@login_required
def collect_page():
    from flask import render_template
    return render_template(
        'audio_data_collect.html',
        member_count=get_group_member_count_for_session(),
    )


@audio_data_bp.route('/annotated/')
@login_required
def annotated_page():
    from flask import render_template
    return render_template('audio_data_annotated.html')


@audio_data_bp.route('/collect/upload', methods=['POST'])
@login_required
def upload_audio():
    """上传音频：情绪由前端表单传入（学生手动选择），服务端不调用识别模型。"""
    if 'audio' not in request.files:
        return jsonify({'error': '未收到音频文件'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    user_id = session.get('user_id')
    group_id = _session_group_id()
    member_id = (request.form.get('member_id') or '').strip() or session.get(
        'member_id', f'M{user_id:02d}' if user_id else 'M01'
    )
    emotion = request.form.get('emotion', 'neutral')
    if emotion not in {'anger', 'fear', 'happy', 'neutral', 'sad', 'surprise', 'angry'}:
        return jsonify({'error': f'无效情绪标签: {emotion}'}), 400

    upload_dir = os.path.join(AUDIO_DATA_DIR, '_uploads')
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(audio_file.filename)[1] or '.wav'
    filename = f"upload_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)

    try:
        audio_file.save(filepath)
        result = save_audio(group_id, member_id, filepath, emotion, copy_file=True)
        return jsonify(result)
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


@audio_data_bp.route('/collect/upload_to_pending', methods=['POST'])
@login_required
def upload_to_pending():
    """上传到待标注目录（可选流程）"""
    if 'audio' not in request.files:
        return jsonify({'error': '未收到音频文件'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    user_id = session.get('user_id')
    group_id = _session_group_id()
    member_id = (request.form.get('member_id') or '').strip() or session.get(
        'member_id', f'M{user_id:02d}' if user_id else 'M01'
    )

    upload_dir = os.path.join(AUDIO_DATA_DIR, '_uploads')
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(audio_file.filename)[1] or '.wav'
    filename = f"upload_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)

    try:
        audio_file.save(filepath)
        result = save_audio_to_pending(group_id, member_id, filepath)
        return jsonify(result)
    finally:
        try:
            os.remove(filepath)
        except OSError:
            pass


@audio_data_bp.route('/collect/pending_list/<group_id>', methods=['GET'])
@login_required
def pending_list(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify({'audios': list_pending_audios(group_id)})


@audio_data_bp.route('/collect/list/<group_id>', methods=['GET'])
@login_required
def list_audios(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify({'audios': list_group_audios(group_id)})


@audio_data_bp.route('/collect/global_stats', methods=['GET'])
@login_required
def global_stats():
    return jsonify(get_global_stats())


@audio_data_bp.route('/collect/delete-sample', methods=['POST'])
@login_required
def delete_audio_sample():
    """
    删除小组已标注音频数据样本
    请求体: { type: 'audio', group_id: string, filename: string }
    """
    import csv

    data = request.get_json() or {}
    data_type = data.get('type', 'audio')
    group_id = data.get('group_id')
    filename = data.get('filename', '')

    if not group_id or not filename:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400

    # 构建音频数据目录路径
    base_dir = os.path.join(AUDIO_DATA_DIR, group_id)

    # 确保是文件名而非路径
    filename = os.path.basename(filename)
    file_path = os.path.join(base_dir, filename)

    deleted_files = []

    # 1. 删除音频文件
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            deleted_files.append(filename)
        except Exception as e:
            return jsonify({'success': False, 'message': f'删除文件失败: {str(e)}'}), 500

    # 2. 更新标签 CSV 文件
    csv_path = os.path.join(base_dir, 'test_labels.csv')
    if os.path.exists(csv_path):
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames

            original_count = len(rows)
            rows = [r for r in rows if r.get('filename', r.get('audio_name', '')) != filename]

            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        except Exception as e:
            print(f'更新标签CSV失败: {str(e)}')

    return jsonify({
        'success': True,
        'message': f'已删除音频 "{filename}"',
        'deleted_files': deleted_files
    })


@audio_data_bp.route('/collect/generate_csv/<group_id>', methods=['POST'])
@login_required
def generate_csv(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify(generate_group_audio_labels_csv(group_id))


@audio_data_bp.route('/collect/sync_to_editor/<group_id>', methods=['POST'])
@login_required
def sync_to_editor(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify(sync_audios_to_editor_workspace(group_id))


@audio_data_bp.route('/collect/summary/<group_id>', methods=['GET'])
@login_required
def data_summary(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify(get_group_audio_data_summary(group_id))


@audio_data_bp.route('/collect/test_set_stats', methods=['GET'])
@login_required
def test_set_stats():
    return jsonify(get_test_set_stats())


@audio_data_bp.route('/collect/contribute_test', methods=['POST'])
@login_required
def contribute_test():
    data = request.json or {}
    group_id = data.get('group_id') or _session_group_id()
    err = _ensure_group_access(group_id)
    if err:
        return err
    file_name = data.get('file_name', '')
    if not file_name:
        return jsonify({'error': '缺少 file_name'}), 400
    return jsonify(contribute_to_test_set(group_id, file_name))


@audio_data_bp.route('/files/<path:rel_path>')
def serve_audio(rel_path):
    """提供音频文件访问（播放器需要，不强制登录）"""
    return send_from_directory(AUDIO_DATA_DIR, rel_path)


@audio_data_bp.route('/annotation/')
@login_required
def annotation_page():
    from flask import render_template
    return render_template('audio_annotation.html')


@audio_data_bp.route('/annotation/queue/<group_id>', methods=['GET'])
@login_required
def annotation_queue(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    include_confirmed = request.args.get('include_confirmed', 'false').lower() == 'true'
    result = get_annotation_queue_from_pending(group_id, include_confirmed)
    return jsonify(result)


@audio_data_bp.route('/annotation/save', methods=['POST'])
@login_required
def annotation_save():
    data = request.json or {}
    user_id = session.get('user_id')
    req_gid = data.get('group_id')
    role = session.get('role', 'group')
    if role == 'group':
        group_id = _session_group_id()
        if req_gid and req_gid != group_id:
            return jsonify({'error': '无权访问其他小组数据'}), 403
    else:
        group_id = req_gid or _session_group_id()

    file_name = data.get('file_name', '')
    label = data.get('label', '')
    member_id = session.get('member_id', f'M{user_id:02d}' if user_id else 'M01')

    if not file_name or not label:
        return jsonify({'error': '参数不完整'}), 400

    result = move_pending_to_confirmed(group_id, file_name, label, member_id)
    return jsonify(result)


@audio_data_bp.route('/annotation/stats/<group_id>', methods=['GET'])
@login_required
def annotation_stats(group_id):
    err = _ensure_group_access(group_id)
    if err:
        return err
    return jsonify(get_annotation_stats(group_id))
