"""
测试集管理路由
管理员功能：
1. 查看所有小组已标注数据
2. 创建测试集（收集/挑选数据）
3. 发布测试集
4. 外部导入测试集
5. 测试集导出
"""
import os
from flask import Blueprint, request, jsonify, send_file, session, render_template

from routes.auth import login_required, admin_or_teacher_required
from services.testset_service import get_testset_service

testset_bp = Blueprint('testset', __name__, url_prefix='/testset')


# ─────────────────────────────────────────────────────────────────────────────
# 管理员测试集管理页面
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/')
@admin_or_teacher_required
def admin_page():
    """管理员测试集管理页面"""
    return render_template('testset_admin.html')


@testset_bp.route('/admin/overview')
@admin_or_teacher_required
def admin_overview():
    """获取测试集总览统计"""
    service = get_testset_service()
    overview = service.get_overview()
    return jsonify({'success': True, 'data': overview})


# ─────────────────────────────────────────────────────────────────────────────
# 获取小组已标注数据
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/group_data')
@admin_or_teacher_required
def get_group_data():
    """
    获取所有小组的已标注数据
    用于管理员查看和选择要发布的数据
    """
    data_type = request.args.get('type', 'face')  # face 或 audio

    service = get_testset_service()
    group_data = service.get_all_group_annotated_data(data_type)

    return jsonify({
        'success': True,
        'data_type': data_type,
        'groups': group_data
    })


# ─────────────────────────────────────────────────────────────────────────────
# 测试集草稿管理
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/draft/create', methods=['POST'])
@admin_or_teacher_required
def create_draft():
    """
    创建测试集草稿

    请求体：
    {
        "type": "face",
        "name": "测试集名称",
        "select_all": true/false,
        "selected_files": [{"group_id": "G01", "filename": "xxx.jpg"}, ...]
    }
    """
    data = request.json

    data_type = data.get('type', 'face')
    name = data.get('name', f'测试集_{data_type}')
    select_all = data.get('select_all', False)
    selected_files = data.get('selected_files', [])

    service = get_testset_service()

    if select_all:
        # 全选：从所有小组获取所有文件
        all_data = service.get_all_group_annotated_data(data_type)
        selected_files = []
        for group_id, group_info in all_data.items():
            for f in group_info['files']:
                selected_files.append({
                    'group_id': group_id,
                    'filename': f['filename']
                })

    result = service.create_draft(data_type, name, selected_files)

    return jsonify(result)


@testset_bp.route('/admin/drafts')
@admin_or_teacher_required
def get_drafts():
    """获取所有测试集草稿"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    drafts = service.get_drafts(data_type)

    return jsonify({
        'success': True,
        'drafts': drafts
    })


@testset_bp.route('/admin/draft/<draft_id>')
@admin_or_teacher_required
def get_draft(draft_id):
    """获取指定草稿详情"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    files = service.get_draft_files(data_type, draft_id)

    return jsonify({
        'success': True,
        'draft_id': draft_id,
        'files': files
    })


@testset_bp.route('/admin/draft/<draft_id>', methods=['DELETE'])
@admin_or_teacher_required
def delete_draft(draft_id):
    """删除测试集草稿"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    result = service.delete_draft(data_type, draft_id)

    return jsonify(result)


@testset_bp.route('/admin/draft/<draft_id>/export')
@admin_or_teacher_required
def export_draft(draft_id):
    """导出草稿（包含标签文件）"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    zip_file = service.export_draft(data_type, draft_id)

    if zip_file is None:
        return jsonify({'error': '草稿不存在'}), 404

    return send_file(
        zip_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'testset_draft_{draft_id}.zip'
    )


# ─────────────────────────────────────────────────────────────────────────────
# 发布测试集
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/publish', methods=['POST'])
@admin_or_teacher_required
def publish_testset():
    """
    发布测试集

    请求体：
    {
        "type": "face",
        "draft_id": "xxx",
        "name": "测试集名称",
        "publish_to_groups": true/false
    }
    """
    data = request.json

    data_type = data.get('type', 'face')
    draft_id = data.get('draft_id')
    testset_name = data.get('name', f'测试集_{data_type}')
    publish_to_groups = data.get('publish_to_groups', False)

    if not draft_id:
        return jsonify({'success': False, 'message': '请提供草稿ID'}), 400

    service = get_testset_service()
    result = service.publish_draft(data_type, draft_id, testset_name, publish_to_groups)

    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# 外部导入测试集
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/import', methods=['POST'])
@admin_or_teacher_required
def import_testset():
    """
    导入外部数据作为测试集

    表单数据：
    - type: face 或 audio
    - name: 测试集名称
    - publish_to_groups: true/false
    - files: 上传的文件列表
    """
    data_type = request.form.get('type', 'face')
    testset_name = data.form.get('name', f'外部测试集_{data_type}')
    publish_to_groups = data.form.get('publish_to_groups', 'false').lower() == 'true'

    files = request.files.getlist('files')

    if not files:
        return jsonify({'success': False, 'message': '请上传文件'}), 400

    uploaded_files = []
    for f in files:
        uploaded_files.append((f.filename, f))

    service = get_testset_service()
    result = service.import_external_data(
        data_type, uploaded_files, testset_name, publish_to_groups
    )

    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# 已发布测试集管理
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/published')
@admin_or_teacher_required
def get_published():
    """获取所有已发布的测试集"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    testsets = service.get_published_testsets(data_type)

    return jsonify({
        'success': True,
        'testsets': testsets
    })


@testset_bp.route('/admin/testset/<testset_id>')
@admin_or_teacher_required
def get_testset(testset_id):
    """获取测试集详情（包含标签信息）"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    files = service.get_testset_files(data_type, testset_id, include_labels=True)

    return jsonify({
        'success': True,
        'testset_id': testset_id,
        'files': files
    })


@testset_bp.route('/admin/testset/<testset_id>/preview')
@admin_or_teacher_required
def preview_testset(testset_id):
    """预览测试集样本（包含标签）"""
    data_type = request.args.get('type', 'face')
    sample_count = request.args.get('count', 5, type=int)

    service = get_testset_service()
    samples = service.preview_testset_sample(data_type, testset_id, sample_count)

    return jsonify({
        'success': True,
        'samples': samples
    })


@testset_bp.route('/admin/testset/<testset_id>', methods=['DELETE'])
@admin_or_teacher_required
def delete_testset(testset_id):
    """删除测试集"""
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    result = service.delete_testset(data_type, testset_id)

    return jsonify(result)


@testset_bp.route('/admin/testset/<testset_id>/export')
@admin_or_teacher_required
def export_testset(testset_id):
    """
    导出测试集
    管理员导出的版本包含标签文件
    """
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    zip_file = service.export_testset(data_type, testset_id, include_labels=True)

    if zip_file is None:
        return jsonify({'error': '测试集不存在'}), 404

    return send_file(
        zip_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'testset_{testset_id}.zip'
    )


# ─────────────────────────────────────────────────────────────────────────────
# 小组端接口（学生可见）
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/available')
@login_required
def get_available_testsets():
    """
    获取小组可用的测试集（不含标签）
    学生可以使用这些测试集来评估自己的模型
    """
    data_type = request.args.get('type', 'face')

    service = get_testset_service()
    testsets = service.get_group_available_testsets(data_type)

    return jsonify({
        'success': True,
        'data_type': data_type,
        'testsets': testsets
    })


@testset_bp.route('/sample')
@login_required
def get_testset_sample():
    """
    获取测试集样本（不含标签）
    学生获取数据后使用自己的模型进行预测
    """
    data_type = request.args.get('type', 'face')
    testset_id = request.args.get('testset_id')
    sample_count = request.args.get('count', 10, type=int)

    if not testset_id:
        return jsonify({'success': False, 'message': '请提供测试集ID'}), 400

    service = get_testset_service()
    samples = service.get_group_testset_sample(data_type, testset_id, sample_count)

    return jsonify({
        'success': True,
        'testset_id': testset_id,
        'samples': samples
    })


@testset_bp.route('/info')
@login_required
def get_testset_info():
    """获取测试集基本信息（不含标签）"""
    data_type = request.args.get('type', 'face')
    testset_id = request.args.get('testset_id')

    if not testset_id:
        return jsonify({'success': False, 'message': '请提供测试集ID'}), 400

    service = get_testset_service()
    testsets = service.get_group_available_testsets(data_type)

    for t in testsets:
        if t['testset_id'] == testset_id:
            return jsonify({
                'success': True,
                'testset': t
            })

    return jsonify({'success': False, 'message': '测试集不存在或未发布给您'}), 404


# ─────────────────────────────────────────────────────────────────────────────
# 静态文件访问（管理员）
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/file/<data_type>/<testset_id>/<path:filename>')
@admin_or_teacher_required
def serve_admin_file(data_type, testset_id, filename):
    """
    管理员访问测试集文件（包括标签文件）
    路径：/testset/admin/file/face/testset_xxx/test_labels.csv
    """
    from config import Config

    # 安全检查：只允许访问已发布的测试集目录
    safe_types = ['face', 'audio']
    if data_type not in safe_types:
        return 'Invalid type', 400

    # 构建文件路径
    file_path = os.path.join(
        Config.BASE_DIR, 'data', 'test_sets', data_type,
        '_published', testset_id, filename
    )

    # 安全检查：确保路径在允许的目录内
    base_dir = os.path.join(Config.BASE_DIR, 'data', 'test_sets')
    if not os.path.abspath(file_path).startswith(os.path.abspath(base_dir)):
        return 'Access denied', 403

    if not os.path.exists(file_path):
        return 'File not found', 404

    # 根据文件类型返回
    if filename.endswith('.csv'):
        return send_file(file_path, mimetype='text/csv')
    elif filename.endswith(('.jpg', '.jpeg', '.png')):
        return send_file(file_path, mimetype='image/jpeg')
    elif filename.endswith('.wav'):
        return send_file(file_path, mimetype='audio/wav')
    else:
        return send_file(file_path)


# ─────────────────────────────────────────────────────────────────────────────
# 静态文件访问（小组 - 无标签）
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/file/<data_type>/<testset_id>/<path:filename>')
@login_required
def serve_group_file(data_type, testset_id, filename):
    """
    小组访问测试集文件（不含标签）
    路径：/testset/file/face/testset_xxx/G01_xxx.jpg
    """
    from config import Config

    safe_types = ['face', 'audio']
    if data_type not in safe_types:
        return 'Invalid type', 400

    # 优先访问 data 子目录（无标签版本）
    data_path = os.path.join(
        Config.BASE_DIR, 'data', 'test_sets', data_type,
        '_published', testset_id, 'data', filename
    )

    # 如果不存在，尝试主目录
    if not os.path.exists(data_path):
        data_path = os.path.join(
            Config.BASE_DIR, 'data', 'test_sets', data_type,
            '_published', testset_id, filename
        )

    # 安全检查
    base_dir = os.path.join(Config.BASE_DIR, 'data', 'test_sets')
    if not os.path.abspath(data_path).startswith(os.path.abspath(base_dir)):
        return 'Access denied', 403

    # 不允许访问标签文件
    if filename.endswith('.csv') or filename.startswith('_'):
        return 'Access denied', 403

    if not os.path.exists(data_path):
        return 'File not found', 404

    if filename.endswith(('.jpg', '.jpeg', '.png')):
        return send_file(data_path, mimetype='image/jpeg')
    elif filename.endswith('.wav'):
        return send_file(data_path, mimetype='audio/wav')
    else:
        return send_file(data_path)


# ─────────────────────────────────────────────────────────────────────────────
# 删除单个数据样本
# ─────────────────────────────────────────────────────────────────────────────

@testset_bp.route('/admin/delete-sample', methods=['POST'])
@admin_or_teacher_required
def delete_sample():
    """
    删除单个数据样本，同时删除源文件和标签CSV中的记录
    请求体: { type: 'face'|'audio', group_id: int, filename: string }
    """
    from config import Config
    import csv
    import shutil

    data = request.get_json() or {}
    data_type = data.get('type', 'face')
    group_id = data.get('group_id')
    filename = data.get('filename', '')

    if not group_id or not filename:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400

    safe_types = ['face', 'audio']
    if data_type not in safe_types:
        return jsonify({'success': False, 'message': '无效的数据类型'}), 400

    # 构建源数据目录路径
    if data_type == 'face':
        base_dir = os.path.join(Config.BASE_DIR, 'data', 'emotion_data', str(group_id))
    else:
        base_dir = os.path.join(Config.BASE_DIR, 'data', 'audio_data', str(group_id))

    # 文件路径
    file_path = os.path.join(base_dir, filename)

    # 安全检查：确保文件在允许的目录内
    abs_base = os.path.abspath(Config.BASE_DIR)
    abs_file = os.path.abspath(file_path)
    if not abs_file.startswith(abs_base):
        return jsonify({'success': False, 'message': '非法文件路径'}), 403

    deleted_files = []
    deleted_csv_records = 0

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
            # 读取现有数据
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames

            # 过滤掉要删除的记录
            original_count = len(rows)
            rows = [r for r in rows if r.get('filename', r.get('image_name', '')) != filename]
            deleted_csv_records = original_count - len(rows)

            # 写回文件
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        except Exception as e:
            # CSV 更新失败，但文件已删除，记录错误但不回滚
            print(f'更新标签CSV失败: {str(e)}')

    return jsonify({
        'success': True,
        'message': f'已删除数据 "{filename}"',
        'deleted_files': deleted_files,
        'deleted_csv_records': deleted_csv_records
    })
