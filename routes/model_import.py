"""
模型导入路由
学生功能：
1. 拖拽上传本地训练的模型
2. 查看已上传模型列表
3. 重命名/删除模型
"""
from flask import Blueprint, request, jsonify, session, send_file

from routes.auth import login_required
from services.model_import_service import get_model_import_service

model_import_bp = Blueprint('model_import', __name__, url_prefix='/model_import')


# ─────────────────────────────────────────────────────────────────────────────
# 页面路由
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/')
@login_required
def index():
    """模型导入页面"""
    from flask import render_template
    return render_template('model_import.html')


# ─────────────────────────────────────────────────────────────────────────────
# 模型上传
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    """
    上传模型文件

    表单数据：
    - file: 模型文件
    - course: 课程类型 (face/audio/emotion/eco)
    - model_name: 模型名称（可选）
    - description: 模型描述（可选）
    """
    group_id = session.get('group_id')

    if not request.files.get('file'):
        return jsonify({'success': False, 'message': '请选择模型文件'}), 400

    file = request.files['file']
    course = request.form.get('course', 'face')
    model_name = request.form.get('model_name', '')
    description = request.form.get('description', '')

    service = get_model_import_service()
    result = service.upload_model(
        file_obj=file,
        group_id=group_id,
        course=course,
        model_name=model_name,
        description=description
    )

    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@model_import_bp.route('/upload/validate', methods=['POST'])
@login_required
def validate_before_upload():
    """
    上传前验证模型文件

    请求：file (multipart)
    """
    if not request.files.get('file'):
        return jsonify({'valid': False, 'message': '请选择文件'}), 400

    file = request.files['file']
    filename = file.filename
    file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    service = get_model_import_service()

    # 检查格式
    if f'.{file_ext}' not in service.SUPPORTED_FORMATS:
        return jsonify({
            'valid': False,
            'message': f'不支持的格式：.{file_ext}。支持的格式：{", ".join(service.SUPPORTED_FORMATS.keys())}'
        })

    # 检查大小
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size > service.MAX_FILE_SIZE:
        return jsonify({
            'valid': False,
            'message': f'文件过大，最大支持 {service.MAX_FILE_SIZE // (1024*1024)}MB'
        })

    framework = service.SUPPORTED_FORMATS.get(f'.{file_ext}', 'unknown')

    return jsonify({
        'valid': True,
        'message': '文件格式正确',
        'info': {
            'filename': filename,
            'ext': file_ext,
            'framework': framework,
            'size': size,
            'size_formatted': service.format_file_size(size)
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# 模型列表
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/list')
@login_required
def list_models():
    """
    获取当前小组的模型列表

    Query参数：
    - course: 课程类型过滤（可选）
    """
    group_id = session.get('group_id')
    course = request.args.get('course')

    service = get_model_import_service()
    models = service.get_group_models(group_id, course)

    # 格式化输出
    for model in models:
        model['file_size_formatted'] = service.format_file_size(model.get('file_size', 0))
        model['framework_icon'] = service.get_framework_icon(model.get('framework', ''))

    return jsonify({
        'success': True,
        'models': models,
        'total': len(models)
    })


@model_import_bp.route('/all')
@login_required
def list_all_models():
    """
    获取所有小组的模型列表（管理员/教师用）

    Query参数：
    - course: 课程类型过滤
    - limit: 返回数量限制
    """
    from routes.auth import admin_or_teacher_required

    course = request.args.get('course')
    limit = request.args.get('limit', type=int)

    service = get_model_import_service()
    models = service.get_all_models(course, limit)

    for model in models:
        model['file_size_formatted'] = service.format_file_size(model.get('file_size', 0))
        model['framework_icon'] = service.get_framework_icon(model.get('framework', ''))

    return jsonify({
        'success': True,
        'models': models,
        'total': len(models)
    })


# ─────────────────────────────────────────────────────────────────────────────
# 模型管理
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/<model_id>')
@login_required
def get_model(model_id):
    """获取模型详情"""
    group_id = session.get('group_id')

    service = get_model_import_service()
    model = service.get_model(model_id)

    if not model:
        return jsonify({'success': False, 'message': '模型不存在'}), 404

    # 检查权限：只能查看自己的模型
    if model.get('group_id') != group_id:
        role = session.get('role')
        if role not in ('super_admin', 'teacher'):
            return jsonify({'success': False, 'message': '无权访问此模型'}), 403

    model['file_size_formatted'] = service.format_file_size(model.get('file_size', 0))
    model['framework_icon'] = service.get_framework_icon(model.get('framework', ''))

    return jsonify({
        'success': True,
        'model': model
    })


@model_import_bp.route('/<model_id>/rename', methods=['PUT'])
@login_required
def rename_model(model_id):
    """重命名模型"""
    group_id = session.get('group_id')
    data = request.json
    new_name = data.get('name', '').strip()

    if not new_name:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400

    service = get_model_import_service()
    model = service.get_model(model_id)

    if not model:
        return jsonify({'success': False, 'message': '模型不存在'}), 404

    # 检查权限
    if model.get('group_id') != group_id:
        return jsonify({'success': False, 'message': '无权修改此模型'}), 403

    result = service.rename_model(model_id, new_name)
    return jsonify(result)


@model_import_bp.route('/<model_id>', methods=['DELETE'])
@login_required
def delete_model(model_id):
    """删除模型"""
    group_id = session.get('group_id')
    role = session.get('role')

    service = get_model_import_service()
    model = service.get_model(model_id)

    if not model:
        return jsonify({'success': False, 'message': '模型不存在'}), 404

    # 检查权限：自己的模型 或 管理员/教师
    if model.get('group_id') != group_id and role not in ('super_admin', 'teacher'):
        return jsonify({'success': False, 'message': '无权删除此模型'}), 403

    result = service.delete_model(model_id)
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# 模型下载
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/<model_id>/download')
@login_required
def download_model(model_id):
    """下载模型文件"""
    group_id = session.get('group_id')
    role = session.get('role')

    service = get_model_import_service()
    model = service.get_model(model_id)

    if not model:
        return jsonify({'error': '模型不存在'}), 404

    # 检查权限
    if model.get('group_id') != group_id and role not in ('super_admin', 'teacher'):
        return jsonify({'error': '无权下载此模型'}), 403

    model_path = service.get_model_path(model_id)
    if not model_path or not __import__('os').path.exists(model_path):
        return jsonify({'error': '模型文件不存在'}), 404

    return send_file(
        model_path,
        as_attachment=True,
        download_name=model.get('original_filename', model_id)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 静态文件访问
# ─────────────────────────────────────────────────────────────────────────────

@model_import_bp.route('/file/<model_id>')
@login_required
def serve_model_file(model_id):
    """访问模型文件"""
    from flask import send_from_directory
    from config import Config

    group_id = session.get('group_id')
    role = session.get('role')

    service = get_model_import_service()
    model = service.get_model(model_id)

    if not model:
        return jsonify({'error': '模型不存在'}), 404

    # 检查权限
    if model.get('group_id') != group_id and role not in ('super_admin', 'teacher'):
        return jsonify({'error': '无权访问此模型'}), 403

    model_dir = Config.BASE_DIR
    return send_from_directory(
        model_dir,
        model.get('file_path', ''),
        as_attachment=False
    )
