"""
表情数据采集路由
"""
from flask import Blueprint, request, jsonify, send_from_directory
import os

from services.emotion_data_service import (
    auto_label_image,
    save_image,
    save_image_to_pending,
    list_pending_images,
    list_group_images,
    get_global_stats,
    contribute_to_test_set,
    get_annotation_queue,
    get_annotation_queue_from_pending,
    save_annotation,
    move_pending_to_confirmed,
    mark_review_needed,
    get_annotation_stats,
    batch_confirm_label,
    confirm_label,
)
from config import Config

# 导入登录验证装饰器
from routes.auth import login_required, get_group_member_count_for_session

emotion_data_bp = Blueprint('emotion_data', __name__, url_prefix='/data')


@emotion_data_bp.route('/collect/')
@login_required
def collect_page():
    """表情数据采集页面"""
    from flask import render_template
    return render_template(
        'face_data_collect.html',
        member_count=get_group_member_count_for_session(),
    )


@emotion_data_bp.route('/annotated/')
@login_required
def annotated_page():
    """表情已标注数据浏览与导出"""
    from flask import render_template
    return render_template('face_data_annotated.html')


@emotion_data_bp.route('/collect/auto_label', methods=['POST'])
@login_required
def auto_label():
    """批量自动预标注"""
    data = request.json
    images = data.get('images', [])
    results = []
    for img in images:
        result = auto_label_image(img)
        results.append(result)
    return jsonify({'results': results})


@emotion_data_bp.route('/collect/upload', methods=['POST'])
@login_required
def upload_single():
    """上传单张采集图片"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    member_id = session.get('member_id', f'M{user_id:02d}' if user_id else 'M01')
    image_b64 = data.get('image', '')
    emotion = data.get('emotion', 'neutral')

    if not image_b64:
        return jsonify({'error': '图片数据为空'}), 400

    # 自动标注
    auto_label_result = auto_label_image(image_b64)

    # 保存图片
    result = save_image(group_id, member_id, image_b64, emotion, auto_label_result)
    return jsonify(result)


@emotion_data_bp.route('/collect/batch_upload', methods=['POST'])
@login_required
def batch_upload():
    """批量上传多张图片"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    member_id = session.get('member_id', f'M{user_id:02d}' if user_id else 'M01')
    images = data.get('images', [])  # [{image, emotion}, ...]

    results = []
    for item in images:
        image_b64 = item.get('image', '')
        emotion = item.get('emotion', 'neutral')
        if image_b64:
            auto_label_result = auto_label_image(image_b64)
            result = save_image(group_id, member_id, image_b64, emotion, auto_label_result)
            results.append(result)

    return jsonify({'saved': len(results), 'results': results})


@emotion_data_bp.route('/collect/upload_to_pending', methods=['POST'])
@login_required
def upload_to_pending():
    """
    上传图片到待标注临时目录（pending目录）
    """
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    member_id = (data.get('member_id') or '').strip() or session.get(
        'member_id', f'M{user_id:02d}' if user_id else 'M01'
    )
    image_b64 = data.get('image', '')
    emotion = data.get('emotion', 'pending')  # 默认情绪为pending，表示待标注

    if not image_b64:
        return jsonify({'error': '图片数据为空'}), 400

    # 保存到pending临时目录
    result = save_image_to_pending(group_id, member_id, image_b64, emotion)
    return jsonify(result)


@emotion_data_bp.route('/collect/pending_list/<group_id>', methods=['GET'])
@login_required
def pending_list(group_id):
    """获取小组待标注队列（从pending目录）"""
    images = list_pending_images(group_id)
    return jsonify({'group_id': group_id, 'images': images, 'total': len(images)})


@emotion_data_bp.route('/collect/batch_save', methods=['POST'])
@login_required
def batch_save_pending():
    """
    批量保存暂存的待标注图片
    """
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    member_id = session.get('member_id', f'M{user_id:02d}' if user_id else 'M01')
    images = data.get('images', [])  # [{image, emotion}, ...]

    results = []
    for item in images:
        image_b64 = item.get('image', '')
        emotion = item.get('emotion', 'neutral')
        if image_b64:
            result = save_image(group_id, member_id, image_b64, emotion)
            results.append(result)

    return jsonify({'saved': len(results), 'results': results})


@emotion_data_bp.route('/collect/confirm_label', methods=['POST'])
@login_required
def label_confirm():
    """确认/修改标注"""
    data = request.json
    group_id = data.get('group_id', 'G01')
    file_name = data.get('file_name', '')
    confirmed_label = data.get('label', '')

    if not file_name or not confirmed_label:
        return jsonify({'error': '参数不完整'}), 400

    result = confirm_label(group_id, file_name, confirmed_label)
    return jsonify(result)


@emotion_data_bp.route('/collect/contribute', methods=['POST'])
@login_required
def contribute():
    """贡献数据到全局测试集"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    file_name = data.get('file_name', '')

    result = contribute_to_test_set(group_id, file_name)
    return jsonify(result)


@emotion_data_bp.route('/collect/list/<group_id>', methods=['GET'])
@login_required
def list_images(group_id):
    """获取小组已采集数据列表"""
    images = list_group_images(group_id)
    return jsonify({'group_id': group_id, 'images': images, 'total': len(images)})


@emotion_data_bp.route('/collect/list', methods=['GET'])
@login_required
def list_images_default():
    """获取当前小组数据列表（默认G01）"""
    from flask import session
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    images = list_group_images(group_id)
    return jsonify({'group_id': group_id, 'images': images, 'total': len(images)})


@emotion_data_bp.route('/collect/global_stats', methods=['GET'])
@login_required
def global_stats():
    """获取全班数据统计"""
    stats = get_global_stats()
    return jsonify(stats)


@emotion_data_bp.route('/collect/delete-sample', methods=['POST'])
@login_required
def delete_sample():
    """
    删除小组已标注数据样本
    请求体: { type: 'face', group_id: string, filename: string }
    """
    import csv

    data = request.get_json() or {}
    data_type = data.get('type', 'face')
    group_id = data.get('group_id')
    filename = data.get('filename', '')

    if not group_id or not filename:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400

    # 构建源数据目录路径
    if data_type == 'face':
        base_dir = os.path.join(Config.EMOTION_DATA_DIR, group_id)
    else:
        base_dir = os.path.join(Config.AUDIO_DATA_DIR, group_id)

    # 确保是文件名而非路径
    filename = os.path.basename(filename)
    file_path = os.path.join(base_dir, filename)

    deleted_files = []

    # 1. 删除图片/音频文件
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
            rows = [r for r in rows if r.get('filename', r.get('image_name', '')) != filename]
            deleted_csv_records = original_count - len(rows)

            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        except Exception as e:
            print(f'更新标签CSV失败: {str(e)}')

    return jsonify({
        'success': True,
        'message': f'已删除数据 "{filename}"',
        'deleted_files': deleted_files
    })


@emotion_data_bp.route('/emotion_data/<path:filename>')
def serve_image(filename):
    """提供表情图片访问"""
    return send_from_directory(Config.EMOTION_DATA_DIR, filename)


@emotion_data_bp.route('/emotion_data/pending/<group_id>/<filename>')
def serve_pending_image(group_id, filename):
    """提供待标注图片访问"""
    pending_full_path = os.path.join(Config.EMOTION_DATA_DIR, '_pending', group_id)
    return send_from_directory(pending_full_path, filename)


# ============================================================
# 标注工作台 API
# ============================================================

@emotion_data_bp.route('/annotation/')
@login_required
def annotation_page():
    """表情数据标注工作台页面"""
    from flask import render_template
    return render_template('emotion_annotation.html')


@emotion_data_bp.route('/annotation/queue/<group_id>', methods=['GET'])
@login_required
def annotation_queue(group_id):
    """获取小组待标注队列（从pending目录）"""
    include_confirmed = request.args.get('include_confirmed', 'false').lower() == 'true'
    result = get_annotation_queue_from_pending(group_id, include_confirmed)
    return jsonify(result)


@emotion_data_bp.route('/annotation/save', methods=['POST'])
@login_required
def annotation_save():
    """
    保存正式标注（将pending图片移动到正式目录）
    """
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    file_name = data.get('file_name', '')
    confirmed_label = data.get('label', '')
    member_id = session.get('member_id', f'M{user_id:02d}' if user_id else 'M01')

    if not file_name or not confirmed_label:
        return jsonify({'error': '参数不完整'}), 400

    # 移动文件到正式目录
    result = move_pending_to_confirmed(group_id, file_name, confirmed_label, member_id)
    return jsonify(result)


@emotion_data_bp.route('/annotation/mark_review', methods=['POST'])
@login_required
def annotation_mark_review():
    """标记需要教师审核"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    file_name = data.get('file_name', '')

    if not file_name:
        return jsonify({'error': '缺少文件名'}), 400

    result = mark_review_needed(group_id, file_name)
    return jsonify(result)


@emotion_data_bp.route('/annotation/stats/<group_id>', methods=['GET'])
@login_required
def annotation_stats(group_id):
    """获取小组标注统计"""
    stats = get_annotation_stats(group_id)
    return jsonify(stats)


@emotion_data_bp.route('/annotation/batch_confirm', methods=['POST'])
@login_required
def annotation_batch_confirm():
    """批量确认标注"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    file_names = data.get('file_names', [])
    confirmed_label = data.get('label', '')

    if not file_names or not confirmed_label:
        return jsonify({'error': '参数不完整'}), 400

    result = batch_confirm_label(group_id, file_names, confirmed_label)
    return jsonify(result)
