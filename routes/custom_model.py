"""
自定义模型管理 API
提供模型的注册、查询、更新、删除、推理等接口
"""
import os
import re
from flask import Blueprint, jsonify, request, session

from services.model_import_service import get_model_import_service
from services.custom_model_service import (
    register_model,
    get_models,
    get_model,
    get_model_by_name,
    update_model,
    rename_model,
    set_default_model,
    delete_model,
    record_model_usage,
    get_group_best_model,
    get_class_top_models,
    submit_to_leaderboard,
    infer_with_model,
    get_model_full_path,
)
from routes.auth import login_required

custom_model_bp = Blueprint('custom_model', __name__, url_prefix='/api/models')


def _normalize_imported_model(m: dict) -> dict:
    """
    将 model_import_service 返回的模型格式标准化为前端期望的格式。
    model_import_service 返回 {model_id, model_name, ...}
    前端期望 {id, model_name, ...}
    """
    return {
        'id': m.get('model_id'),
        'model_name': m.get('model_name'),
        'group_id': m.get('group_id'),
        'course': m.get('course'),
        'framework': m.get('framework'),
        'framework_icon': m.get('framework_icon'),
        'accuracy': m.get('accuracy'),
        'is_active': m.get('is_active', True),
        'is_default': False,
        'uploaded_at': m.get('uploaded_at'),
        'file_size': m.get('file_size'),
        'file_size_formatted': m.get('file_size_formatted'),
        'source': 'imported',  # 标识来源
        'original_metadata': m,  # 保留原始元数据供推理使用
    }


def _get_group_info():
    """
    获取当前用户的 group_id 和 group_name。

    登录时 session 已统一设置：
    - 小组账号：group_id = 小组代码（如 'G001'），group_name = 小组名
    - 教师/管理员：group_id = 'user_{user_id}'，group_name = 显示名
    返回 dict: {group_id, group_name}
    """
    gid = session.get('group_id')
    # 防御：如果 group_id 未设置（理论上不会发生），安全回退
    if not gid:
        uid = session.get('user_id')
        role = session.get('role')
        if role == 'group' and uid:
            gid = str(uid)
        elif uid:
            gid = f"user_{uid}"
        else:
            gid = 'guest'
    return {
        'group_id': gid,
        'group_name': session.get('group_name') or session.get('username') or '未知用户'
    }


# ── 模型注册 ──────────────────────────────────────────────────────────────────

@custom_model_bp.route('/register', methods=['POST'])
@login_required
def api_register_model():
    """
    注册新的自定义模型

    Request JSON:
    {
        "course": "face",           # 课程类型 (face/emotion/audio/eco)
        "model_name": "我的表情模型", # 模型名称（学生自定义）
        "model_path": "models/face.h5", # 模型文件路径
        "accuracy": 0.8523,         # 验证集准确率
        "framework": "tensorflow",  # 框架类型 (tensorflow/pytorch/sklearn)
        "model_type": "classification",
        "config": {}
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求数据不能为空'}), 400

    course = data.get('course')
    model_name = data.get('model_name')
    model_path = data.get('model_path')

    if not course or not model_name or not model_path:
        return jsonify({'error': '课程类型、模型名称和模型路径不能为空'}), 400

    # 验证课程类型
    valid_courses = ['face', 'emotion', 'audio', 'eco']
    if course not in valid_courses:
        return jsonify({'error': f'无效的课程类型，支持: {valid_courses}'}), 400

    # 获取小组信息
    group_info = _get_group_info()

    # 检查模型名称是否已存在
    existing = get_model_by_name(group_info['group_id'], model_name, course)
    if existing:
        # 更新已有模型
        updated = update_model(existing['id'], {
            'accuracy': data.get('accuracy', existing['accuracy']),
            'model_path': model_path,
            'config': data.get('config', {})
        })
        return jsonify({
            'success': True,
            'message': f'模型 "{model_name}" 已更新',
            'model': updated,
            'is_update': True
        })

    # 注册新模型
    model = register_model(
        group_id=group_info['group_id'],
        group_name=group_info['group_name'],
        course=course,
        model_name=model_name,
        model_path=model_path,
        accuracy=data.get('accuracy', 0),
        framework=data.get('framework', 'tensorflow'),
        model_type=data.get('model_type', 'classification'),
        config=data.get('config', {})
    )

    # 自动提交到排行榜
    leaderboard_result = None
    if model.get('accuracy', 0) > 0:
        try:
            leaderboard_result = submit_to_leaderboard(
                group_id=group_info['group_id'],
                group_name=group_info['group_name'],
                course=course,
                accuracy=model['accuracy'],
                model_id=model['id'],
                model_name=model_name
            )
        except Exception:
            pass

    return jsonify({
        'success': True,
        'message': f'模型 "{model_name}" 注册成功',
        'model': model,
        'leaderboard': leaderboard_result
    })


# ── 模型查询 ──────────────────────────────────────────────────────────────────

@custom_model_bp.route('/list', methods=['GET'])
@login_required
def api_list_models():
    """
    获取模型列表（合并导入模型和自定义训练模型）

    Query params:
    - course: 筛选指定课程
    - group_id: 筛选指定小组（管理员可用）
    - source: 筛选来源，可选 'imported' / 'custom'，默认全部
    """
    try:
        group_info = _get_group_info()
        course = request.args.get('course')
        group_id = request.args.get('group_id')
        source_filter = request.args.get('source')

        # 权限检查：
        # - 小组账号（role='group'）：只能查看自己小组的模型
        # - 教师/管理员：可以查看所有模型（当指定 group_id 时）或自己相关的模型
        role = session.get('role')
        if role == 'group':
            # 小组账号强制只能查看自己小组的模型
            group_id = group_info['group_id']
        elif role in ('super_admin', 'teacher'):
            # 教师/管理员可以查看所有模型（group_id 由 query 参数指定）
            # 如果没有指定 group_id，则查看自己个人的模型
            if not group_id:
                group_id = group_info['group_id']
        else:
            # 未知角色，使用自己的 group_id
            if not group_id:
                group_id = group_info['group_id']

        all_models = []

        # 1. 从 model_import_service 获取用户导入的模型
        if not source_filter or source_filter == 'imported':
            import_service = get_model_import_service()
            imported = import_service.get_group_models(group_id, course)
            all_models.extend(_normalize_imported_model(m) for m in imported)

        # 2. 从 custom_model_service 获取自定义训练模型
        if not source_filter or source_filter == 'custom':
            custom = get_models(
                group_id=group_id,
                course=course,
                active_only=request.args.get('include_inactive') != 'true'
            )
            for m in custom:
                m['source'] = 'custom'
                m['id'] = m.get('id')
                all_models.append(m)

        return jsonify({
            'success': True,
            'count': len(all_models),
            'models': all_models
        })
    except Exception as e:
        import logging
        logging.error(f"api_list_models error: {e}", exc_info=True)
        return jsonify({'error': f'获取模型列表失败: {str(e)}'}), 500


@custom_model_bp.route('/detail/<model_id>', methods=['GET'])
@login_required
def api_get_model(model_id: str):
    """获取模型详情"""
    # 先尝试从 custom_model_service 获取
    model = get_model(model_id)
    if model:
        model['source'] = 'custom'
        return jsonify({
            'success': True,
            'model': model
        })

    # 再尝试从 model_import_service 获取
    import_service = get_model_import_service()
    imported = import_service.get_model(model_id)
    if imported:
        return jsonify({
            'success': True,
            'model': _normalize_imported_model(imported)
        })

    return jsonify({'error': '模型不存在'}), 404


@custom_model_bp.route('/best', methods=['GET'])
@login_required
def api_get_best_model():
    """获取当前小组在指定课程的最佳模型（合并导入模型和训练模型）"""
    group_info = _get_group_info()
    course = request.args.get('course', 'face')

    all_models = []

    # 从 custom_model_service 获取训练模型
    custom_best = get_group_best_model(group_info['group_id'], course)
    if custom_best:
        custom_best['source'] = 'custom'
        all_models.append(custom_best)

    # 从 model_import_service 获取导入模型
    import_service = get_model_import_service()
    imported_models = import_service.get_group_models(group_info['group_id'], course)
    for m in imported_models:
        if m.get('accuracy') is not None:
            all_models.append(_normalize_imported_model(m))

    if not all_models:
        return jsonify({
            'success': True,
            'model': None,
            'message': '暂无训练模型'
        })

    # 按准确率排序
    best = max(all_models, key=lambda x: x.get('accuracy') or 0)
    return jsonify({
        'success': True,
        'model': best
    })


@custom_model_bp.route('/top', methods=['GET'])
@login_required
def api_get_top_models():
    """获取班级最佳模型排行"""
    course = request.args.get('course', 'face')
    limit = min(int(request.args.get('limit', 10)), 50)

    top_models = get_class_top_models(course, limit)

    return jsonify({
        'success': True,
        'course': course,
        'count': len(top_models),
        'models': top_models
    })


# ── 模型更新 ──────────────────────────────────────────────────────────────────

@custom_model_bp.route('/rename/<model_id>', methods=['PUT'])
@login_required
def api_rename_model(model_id: str):
    """重命名模型"""
    group_info = _get_group_info()

    # 先尝试 custom_model_service
    model = get_model(model_id)
    if model:
        if str(model['group_id']) != str(group_info['group_id']):
            return jsonify({'error': '无权操作此模型'}), 403

        data = request.get_json()
        new_name = data.get('model_name', '').strip()
        if not new_name:
            return jsonify({'error': '模型名称不能为空'}), 400

        updated = rename_model(model_id, new_name)
        return jsonify({
            'success': True,
            'message': f'模型已重命名为 "{new_name}"',
            'model': updated
        })

    # 再尝试 model_import_service
    import_service = get_model_import_service()
    imported = import_service.get_model(model_id)
    if imported:
        if str(imported.get('group_id')) != str(group_info['group_id']):
            return jsonify({'error': '无权操作此模型'}), 403

        data = request.get_json()
        new_name = data.get('model_name', '').strip()
        if not new_name:
            return jsonify({'error': '模型名称不能为空'}), 400

        import_service.rename_model(model_id, new_name)
        return jsonify({
            'success': True,
            'message': f'模型已重命名为 "{new_name}"'
        })

    return jsonify({'error': '模型不存在'}), 404


@custom_model_bp.route('/default/<model_id>', methods=['PUT'])
@login_required
def api_set_default(model_id: str):
    """设置默认模型"""
    model = get_model(model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404

    # 验证权限
    group_info = _get_group_info()
    if str(model['group_id']) != str(group_info['group_id']):
        return jsonify({'error': '无权操作此模型'}), 403

    updated = set_default_model(model_id, group_info['group_id'], model['course'])
    return jsonify({
        'success': True,
        'message': f'已设为默认模型',
        'model': updated
    })


@custom_model_bp.route('/toggle/<model_id>', methods=['PUT'])
@login_required
def api_toggle_model(model_id: str):
    """启用/停用模型"""
    model = get_model(model_id)
    if not model:
        return jsonify({'error': '模型不存在'}), 404

    # 验证权限
    group_info = _get_group_info()
    if str(model['group_id']) != str(group_info['group_id']):
        return jsonify({'error': '无权操作此模型'}), 403

    new_status = not model.get('is_active', True)
    updated = update_model(model_id, {'is_active': new_status})

    status_text = '启用' if new_status else '停用'
    return jsonify({
        'success': True,
        'message': f'模型已{status_text}',
        'model': updated
    })


# ── 模型删除 ──────────────────────────────────────────────────────────────────

@custom_model_bp.route('/delete/<model_id>', methods=['DELETE'])
@login_required
def api_delete_model(model_id: str):
    """删除模型"""
    group_info = _get_group_info()
    role = session.get('role')

    # 先尝试 custom_model_service
    model = get_model(model_id)
    if model:
        # 只有模型所有者或 super_admin 才能删除
        if str(model['group_id']) != str(group_info['group_id']):
            if role != 'super_admin':
                return jsonify({'error': '无权操作此模型'}), 403

        deleted = delete_model(model_id)
        if deleted:
            return jsonify({
                'success': True,
                'message': f'模型 "{model["model_name"]}" 已删除'
            })
        return jsonify({'error': '删除失败'}), 500

    # 再尝试 model_import_service
    import_service = get_model_import_service()
    imported = import_service.get_model(model_id)
    if imported:
        if str(imported.get('group_id')) != str(group_info['group_id']):
            if role != 'super_admin':
                return jsonify({'error': '无权操作此模型'}), 403

        result = import_service.delete_model(model_id)
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': result.get('message', '模型已删除')
            })
        return jsonify({'error': result.get('message', '删除失败')}), 500

    return jsonify({'error': '模型不存在'}), 404


# ── 模型推理 ──────────────────────────────────────────────────────────────────

@custom_model_bp.route('/infer/<model_id>', methods=['POST'])
@login_required
def api_infer(model_id: str):
    """使用模型进行推理（支持导入模型和自定义训练模型）"""
    # 先尝试 custom_model_service
    model = get_model(model_id)
    if model:
        model['source'] = 'custom'
        if not model.get('is_active'):
            return jsonify({'error': '模型已停用'}), 403
        result = infer_with_model(model_id, request.get_json() or {})
        return jsonify(result)

    # 再尝试 model_import_service
    import_service = get_model_import_service()
    imported = import_service.get_model(model_id)
    if imported:
        if not imported.get('is_active', True):
            return jsonify({'error': '模型已停用'}), 403

        model_path = import_service.get_model_path(model_id)
        if not model_path or not os.path.exists(model_path):
            return jsonify({'error': '模型文件不存在'}), 404

        result = _infer_imported_model(imported, model_path, request.get_json() or {})
        return jsonify(result)

    return jsonify({'error': '模型不存在'}), 404


def _infer_imported_model(model: dict, model_path: str, data: dict) -> dict:
    """对导入的模型进行推理"""
    framework = model.get('framework', 'tensorflow')
    course = model.get('course', 'face')

    if framework == 'tensorflow':
        return _infer_imported_tensorflow(model, model_path, data, course)
    elif framework == 'pytorch':
        return _infer_imported_pytorch(model, model_path, data, course)
    elif framework == 'sklearn':
        return _infer_imported_sklearn(model, model_path, data, course)
    else:
        return {'error': f'不支持的框架: {framework}'}


def _infer_imported_tensorflow(model: dict, model_path: str, data: dict, course: str) -> dict:
    """TensorFlow/Keras 导入模型推理"""
    try:
        from tensorflow.keras.models import load_model
        import numpy as np

        keras_model = load_model(model_path, compile=False)

        if course == 'face':
            image_b64 = data.get('image', '')
            return _infer_face_from_imported(keras_model, model, image_b64)
        elif course == 'eco':
            features = data.get('features', [])
            X = np.array(features)
            if len(X.shape) == 1:
                X = np.expand_dims(X, axis=0)
            preds = keras_model.predict(X, verbose=0)
            return {
                'success': True,
                'model_id': model.get('model_id'),
                'model_name': model.get('model_name'),
                'accuracy': model.get('accuracy'),
                'predictions': preds.tolist()
            }
        else:
            return {'error': f'课程 {course} 暂不支持推理'}
    except Exception as e:
        return {'error': f'推理失败: {str(e)}'}


def _infer_face_from_imported(keras_model, model: dict, image_b64: str) -> dict:
    """表情图像推理"""
    try:
        import base64
        import cv2
        import numpy as np

        if not image_b64:
            return {'error': '请提供图片数据'}

        img_data = base64.b64decode(image_b64.split(',')[-1])
        nparr = np.frombuffer(img_data, np.uint8)
        gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        if gray is None:
            return {'error': '无法解析图像'}

        target_size = (48, 48)
        face_resized = cv2.resize(gray, target_size)
        face_arr = face_resized.astype('float32') / 255.0
        face_arr = np.expand_dims(face_arr, axis=0)
        face_arr = np.expand_dims(face_arr, axis=-1)

        preds = keras_model.predict(face_arr, verbose=0)[0]
        emotion_idx = int(np.argmax(preds))
        confidence = float(preds[emotion_idx])

        emotion_labels = {
            0: '生气', 1: '厌恶', 2: '恐惧', 3: '开心', 4: '悲伤', 5: '惊讶', 6: '中性'
        }
        from config import Config
        emotion_labels_cn = getattr(Config, 'EMOTION_LABELS_CN', emotion_labels)
        emotion_label = emotion_labels_cn.get(emotion_idx, emotion_labels.get(emotion_idx, '未知'))

        scores = {emotion_labels_cn.get(i, emotion_labels.get(i, f'emotion_{i}')): float(preds[i])
                  for i in range(len(preds))}

        return {
            'success': True,
            'model_id': model.get('model_id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'emotion_idx': emotion_idx,
            'emotion': emotion_label,
            'confidence': confidence,
            'all_scores': scores
        }
    except Exception as e:
        return {'error': f'表情识别失败: {str(e)}'}


def _infer_imported_pytorch(model: dict, model_path: str, data: dict, course: str) -> dict:
    """PyTorch 导入模型推理"""
    try:
        import torch
        pytorch_model = torch.load(model_path, map_location='cpu')
        pytorch_model.eval()
        return {'error': 'PyTorch 推理暂未实现'}
    except Exception as e:
        return {'error': f'PyTorch 推理失败: {str(e)}'}


def _infer_imported_sklearn(model: dict, model_path: str, data: dict, course: str) -> dict:
    """sklearn 导入模型推理"""
    try:
        import pickle
        import numpy as np
        with open(model_path, 'rb') as f:
            sklearn_model = pickle.load(f)

        if course == 'eco':
            features = data.get('features', [])
            X = np.array(features)
            if len(X.shape) == 1:
                X = X.reshape(1, -1)
            preds = sklearn_model.predict(X)
            return {
                'success': True,
                'model_id': model.get('model_id'),
                'model_name': model.get('model_name'),
                'predictions': preds.tolist() if hasattr(preds, 'tolist') else [float(preds)]
            }
        else:
            return {'error': f'课程 {course} 暂不支持推理'}
    except Exception as e:
        return {'error': f'sklearn 推理失败: {str(e)}'}


# ── 批量导入训练结果 ──────────────────────────────────────────────────────────

@custom_model_bp.route('/import', methods=['POST'])
@login_required
def api_import_models():
    """
    批量导入模型（用于训练完成后自动调用）

    Request JSON:
    {
        "models": [
            {
                "course": "face",
                "model_name": "CNN模型_v1",
                "model_path": "G01/face/models/face_cnn.h5",
                "accuracy": 0.8532
            }
        ]
    }
    """
    data = request.get_json()
    models_data = data.get('models', [])

    if not models_data:
        return jsonify({'error': '没有模型数据'}), 400

    group_info = _get_group_info()
    results = []

    for m in models_data:
        try:
            # 注册或更新模型
            existing = get_model_by_name(
                group_info['group_id'],
                m.get('model_name'),
                m.get('course')
            )

            if existing:
                updated = update_model(existing['id'], {
                    'accuracy': m.get('accuracy', existing['accuracy']),
                    'model_path': m.get('model_path')
                })
                results.append({'name': m['model_name'], 'action': 'updated', 'model': updated})
            else:
                model = register_model(
                    group_id=group_info['group_id'],
                    group_name=group_info['group_name'],
                    course=m.get('course'),
                    model_name=m.get('model_name'),
                    model_path=m.get('model_path'),
                    accuracy=m.get('accuracy', 0),
                    framework=m.get('framework', 'tensorflow'),
                    config=m.get('config', {})
                )

                # 自动提交到排行榜
                if model.get('accuracy', 0) > 0.5:
                    try:
                        submit_to_leaderboard(
                            group_id=group_info['group_id'],
                            group_name=group_info['group_name'],
                            course=m.get('course'),
                            accuracy=model['accuracy'],
                            model_id=model['id'],
                            model_name=model['model_name']
                        )
                    except Exception:
                        pass

                results.append({'name': m['model_name'], 'action': 'registered', 'model': model})

        except Exception as e:
            results.append({'name': m.get('model_name', 'unknown'), 'action': 'failed', 'error': str(e)})

    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })


# ── 获取模型路径（供内部使用）────────────────────────────────────────────────

@custom_model_bp.route('/path/<model_id>', methods=['GET'])
@login_required
def api_get_model_path(model_id: str):
    """获取模型的完整路径"""
    # 先尝试 custom_model_service
    model = get_model(model_id)
    if model:
        full_path = get_model_full_path(model)
        return jsonify({
            'success': True,
            'model_id': model_id,
            'model_name': model['model_name'],
            'model_path': model['model_path'],
            'full_path': full_path,
            'exists': os.path.exists(full_path) if full_path else False
        })

    # 再尝试 model_import_service
    import_service = get_model_import_service()
    imported = import_service.get_model(model_id)
    if imported:
        full_path = import_service.get_model_path(model_id)
        return jsonify({
            'success': True,
            'model_id': model_id,
            'model_name': imported.get('model_name'),
            'model_path': imported.get('file_path'),
            'full_path': full_path,
            'exists': os.path.exists(full_path) if full_path else False
        })

    return jsonify({'error': '模型不存在'}), 404
