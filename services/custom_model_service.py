"""
自定义模型管理服务
管理学生小组训练的自定义模型：注册、加载、重命名、删除、推理
"""
import json
import os
import shutil
import uuid
from datetime import datetime
from config import Config

CUSTOM_MODELS_DIR = os.path.join(Config.BASE_DIR, 'data', 'custom_models')
os.makedirs(CUSTOM_MODELS_DIR, exist_ok=True)

MODELS_INDEX_FILE = os.path.join(CUSTOM_MODELS_DIR, 'models_index.json')


def _load_index() -> dict:
    """加载模型索引"""
    if os.path.exists(MODELS_INDEX_FILE):
        with open(MODELS_INDEX_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'version': '2026-v1',
        'models': [],
        'updated_at': datetime.now().isoformat()
    }


def _save_index(index: dict):
    """保存模型索引"""
    index['updated_at'] = datetime.now().isoformat()
    with open(MODELS_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _safe_group_id(group_id) -> str:
    """净化小组ID为目录名"""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(group_id))


# ── 模型注册 ──────────────────────────────────────────────────────────────────

def register_model(
    group_id: str,
    group_name: str,
    course: str,
    model_name: str,
    model_path: str,
    accuracy: float,
    framework: str = 'tensorflow',
    model_type: str = 'classification',
    config: dict = None
) -> dict:
    """
    注册一个新的自定义模型

    Args:
        group_id: 小组ID
        group_name: 小组名称
        course: 课程类型 (face/emotion/audio/eco)
        model_name: 模型名称（学生自定义）
        model_path: 模型文件路径（相对于小组工作目录）
        accuracy: 验证集准确率
        framework: 框架类型 (tensorflow/pytorch/sklearn)
        model_type: 模型类型 (classification/regression)
        config: 其他配置信息

    Returns:
        注册后的模型信息
    """
    index = _load_index()
    models = index.get('models', [])

    # 生成模型ID
    model_id = str(uuid.uuid4())[:8]

    # 构建模型记录
    model_record = {
        'id': model_id,
        'group_id': str(group_id),
        'group_name': str(group_name),
        'course': course,
        'model_name': model_name,
        'model_path': model_path,
        'accuracy': round(accuracy, 4),
        'framework': framework,
        'model_type': model_type,
        'config': config or {},
        'is_active': True,
        'is_default': False,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'usage_count': 0,
        'last_used_at': None
    }

    # 添加到列表
    models.append(model_record)

    # 排序：按准确率降序
    models.sort(key=lambda x: x.get('accuracy', 0), reverse=True)
    index['models'] = models
    _save_index(index)

    return model_record


def get_models(
    group_id: str = None,
    course: str = None,
    active_only: bool = True
) -> list:
    """
    获取模型列表

    Args:
        group_id: 筛选特定小组的模型
        course: 筛选特定课程的模型 (face/emotion/audio/eco)
        active_only: 只返回激活的模型

    Returns:
        模型列表
    """
    index = _load_index()
    models = index.get('models', [])

    if group_id:
        models = [m for m in models if str(m.get('group_id')) == str(group_id)]
    if course:
        models = [m for m in models if m.get('course') == course]
    if active_only:
        models = [m for m in models if m.get('is_active', True)]

    return models


def get_custom_models(course: str = None) -> list:
    """
    获取自定义模型列表（兼容性别名）

    Args:
        course: 筛选特定课程的模型 (face/emotion/audio/eco)

    Returns:
        模型列表
    """
    return get_models(course=course, active_only=True)


def get_model(model_id: str) -> dict:
    """获取指定模型详情"""
    index = _load_index()
    models = index.get('models', [])

    for model in models:
        if model.get('id') == model_id:
            return model
    return None


def get_model_by_name(group_id: str, model_name: str, course: str = None) -> dict:
    """通过名称和小组获取模型"""
    index = _load_index()
    models = index.get('models', [])

    for model in models:
        if (str(model.get('group_id')) == str(group_id) and
            model.get('model_name') == model_name and
            (course is None or model.get('course') == course)):
            return model
    return None


# ── 模型更新 ──────────────────────────────────────────────────────────────────

def update_model(model_id: str, updates: dict) -> dict:
    """
    更新模型信息

    Args:
        model_id: 模型ID
        updates: 要更新的字段

    Returns:
        更新后的模型信息
    """
    index = _load_index()
    models = index.get('models', [])

    for i, model in enumerate(models):
        if model.get('id') == model_id:
            # 允许更新的字段
            allowed_fields = ['model_name', 'is_active', 'is_default', 'accuracy', 'config']
            for key, value in updates.items():
                if key in allowed_fields:
                    models[i][key] = value

            models[i]['updated_at'] = datetime.now().isoformat()
            index['models'] = models
            _save_index(index)
            return models[i]

    return None


def rename_model(model_id: str, new_name: str) -> dict:
    """重命名模型"""
    return update_model(model_id, {'model_name': new_name})


def set_default_model(model_id: str, group_id: str = None, course: str = None) -> dict:
    """
    设置默认模型（同一小组同一课程的模型只能有一个默认）

    Args:
        model_id: 要设为默认的模型ID
        group_id: 小组ID（用于取消同组其他模型的默认状态）
        course: 课程类型

    Returns:
        更新后的模型信息
    """
    index = _load_index()
    models = index.get('models', [])

    # 先取消同组同课程的其他默认
    if group_id and course:
        for i, m in enumerate(models):
            if (str(m.get('group_id')) == str(group_id) and
                m.get('course') == course and
                m.get('id') != model_id):
                models[i]['is_default'] = False

    # 设置新的默认
    for i, m in enumerate(models):
        if m.get('id') == model_id:
            models[i]['is_default'] = True
            models[i]['updated_at'] = datetime.now().isoformat()
            index['models'] = models
            _save_index(index)
            return models[i]

    return None


def delete_model(model_id: str, delete_file: bool = True) -> bool:
    """
    删除模型

    Args:
        model_id: 模型ID
        delete_file: 是否删除物理文件

    Returns:
        是否删除成功
    """
    index = _load_index()
    models = index.get('models', [])

    for i, model in enumerate(models):
        if model.get('id') == model_id:
            # 删除物理文件
            if delete_file and model.get('model_path'):
                try:
                    full_path = os.path.join(Config.EDITOR_WORKSPACE_ROOT, model.get('model_path'))
                    if os.path.exists(full_path):
                        os.remove(full_path)
                except Exception:
                    pass

            # 从索引中移除
            models.pop(i)
            index['models'] = models
            _save_index(index)
            return True

    return False


# ── 模型使用统计 ──────────────────────────────────────────────────────────────

def record_model_usage(model_id: str) -> dict:
    """记录模型被使用"""
    index = _load_index()
    models = index.get('models', [])

    for i, model in enumerate(models):
        if model.get('id') == model_id:
            models[i]['usage_count'] = models[i].get('usage_count', 0) + 1
            models[i]['last_used_at'] = datetime.now().isoformat()
            index['models'] = models
            _save_index(index)
            return models[i]

    return None


def get_group_best_model(group_id: str, course: str) -> dict:
    """获取小组在指定课程的最佳模型"""
    models = get_models(group_id=group_id, course=course)
    if not models:
        return None

    # 按准确率排序，返回最高的
    best = max(models, key=lambda x: x.get('accuracy', 0))
    return best


def get_class_top_models(course: str, limit: int = 10) -> list:
    """获取班级在指定课程的最佳模型"""
    index = _load_index()
    models = index.get('models', [])

    # 筛选指定课程
    course_models = [m for m in models if m.get('course') == course]

    # 按准确率排序
    course_models.sort(key=lambda x: x.get('accuracy', 0), reverse=True)

    return course_models[:limit]


# ── 推理接口 ─────────────────────────────────────────────────────────────────

def get_model_full_path(model_record: dict) -> str:
    """获取模型的完整路径"""
    import logging
    logger = logging.getLogger(__name__)

    if not model_record or not model_record.get('file_path') and not model_record.get('model_path'):
        logger.warning("模型记录为空或没有 file_path/model_path")
        return None

    # 兼容两种字段名：file_path (model_import_service) 和 model_path (custom_model_service)
    model_path = model_record.get('file_path') or model_record.get('model_path', '')

    # 统一路径分隔符（Windows 和 Linux 兼容）
    model_path = model_path.replace('\\', '/')
    logger.info(f"查找模型路径: {model_path}")

    # 优先检查 custom_model_service 的路径
    custom_path = os.path.join(Config.EDITOR_WORKSPACE_ROOT, model_path)
    if os.path.exists(custom_path):
        logger.info(f"在 custom 路径找到模型: {custom_path}")
        return custom_path

    # 再检查 model_import_service 的路径（导入的模型）
    import_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'uploaded_models')
    import_path = os.path.join(import_base, model_path)
    if os.path.exists(import_path):
        logger.info(f"在 import 路径找到模型: {import_path}")
        return import_path

    # 尝试直接作为绝对路径
    if os.path.exists(model_path):
        logger.info(f"作为绝对路径找到模型: {model_path}")
        return model_path

    logger.warning(f"模型文件不存在: custom_path={custom_path}, import_path={import_path}")
    return None


def infer_with_model(model_id: str, data: dict) -> dict:
    """
    使用自定义模型进行推理

    Args:
        model_id: 模型ID
        data: 推理数据

    Returns:
        推理结果
    """
    import logging
    logger = logging.getLogger(__name__)

    # 先从 custom_model_service 查找
    model = get_model(model_id)

    # 如果没找到，尝试从 model_import_service 查找
    if not model:
        try:
            from services.model_import_service import ModelImportService
            import_service = ModelImportService()
            model = import_service.get_model(model_id)
            if model:
                logger.info(f"从 model_import_service 找到模型: {model_id}")
        except Exception as e:
            logger.warning(f"从 model_import_service 查找模型失败: {e}")

    if not model:
        logger.error(f"模型不存在: {model_id}")
        return {'error': '模型不存在'}

    if not model.get('is_active'):
        return {'error': '模型已停用'}

    # 记录使用
    record_model_usage(model_id)

    # 根据框架选择推理方式
    framework = model.get('framework', 'tensorflow')
    logger.info(f"模型框架: {framework}, 模型ID: {model_id}")

    if framework == 'tensorflow':
        return _infer_tensorflow(model, data)
    elif framework == 'pytorch':
        return _infer_pytorch(model, data)
    elif framework == 'onnx':
        return _infer_onnx(model, data)
    else:
        return {'error': f'不支持的框架: {framework}'}


def _infer_tensorflow(model: dict, data: dict) -> dict:
    """TensorFlow/Keras 模型推理"""
    model_path = get_model_full_path(model)
    if not model_path or not os.path.exists(model_path):
        return {'error': '模型文件不存在'}

    try:
        from tensorflow.keras.models import load_model
        import numpy as np

        keras_model = load_model(model_path, compile=False)

        # 根据课程类型处理输入
        course = model.get('course', 'face')

        if course == 'face':
            # 表情识别
            image_b64 = data.get('image', '')
            return _infer_face_image(keras_model, image_b64, model)

        elif course == 'audio':
            # 声音情绪
            audio_path = data.get('audio_path')
            if not audio_path:
                return {'error': '缺少音频文件路径'}
            return _infer_audio_keras(keras_model, audio_path, model)

        elif course == 'eco':
            # 生态瓶预测
            features = data.get('features', [])
            return _infer_eco_features(keras_model, features, model)

        else:
            return {'error': f'未知课程类型: {course}'}

    except Exception as e:
        return {'error': f'推理失败: {str(e)}'}


def _infer_audio_keras(keras_model, audio_path: str, model: dict) -> dict:
    """Keras 声音情绪推理"""
    try:
        import numpy as np
        import librosa

        if not audio_path or not os.path.exists(audio_path):
            return {'error': '音频文件不存在'}

        # 情绪标签映射
        AUDIO_EMOJI = {'anger': '😠', 'fear': '😨', 'happy': '😊',
                       'neutral': '😐', 'sad': '😢', 'surprise': '😮'}
        AUDIO_LABELS_CN = {'anger': '生气', 'fear': '恐惧', 'happy': '开心',
                          'neutral': '平静', 'sad': '难过', 'surprise': '惊讶'}

        # 训练代码中的参数
        SAMPLE_RATE = 16000
        N_MFCC = 40
        N_FFT = 400
        HOP_LENGTH = 160
        MAX_LEN = 100

        # 加载音频
        y, sr = librosa.load(audio_path, sr=SAMPLE_RATE, duration=3.0)

        # 提取 MFCC 特征
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC,
                                     n_fft=N_FFT, hop_length=HOP_LENGTH)

        # 对齐到固定长度
        if mfcc.shape[1] < MAX_LEN:
            mfcc = np.pad(mfcc, ((0, 0), (0, MAX_LEN - mfcc.shape[1])), mode='constant')
        else:
            mfcc = mfcc[:, :MAX_LEN]

        # 归一化并转置
        mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)
        features = mfcc.T.astype('float32')[np.newaxis, :, :]

        # 推理
        preds = keras_model.predict(features, verbose=0)[0]
        emotion_idx = int(np.argmax(preds))
        confidence = float(preds[emotion_idx])

        emotion_labels = ['anger', 'fear', 'happy', 'neutral', 'sad', 'surprise']
        emotion_en = emotion_labels[emotion_idx] if emotion_idx < len(emotion_labels) else 'neutral'

        scores = {emotion_labels[i]: float(preds[i]) for i in range(len(preds))}

        return {
            'success': True,
            'model_id': model.get('id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'emotion': emotion_en,
            'emotion_cn': AUDIO_LABELS_CN.get(emotion_en, '平静'),
            'emoji': AUDIO_EMOJI.get(emotion_en, '😐'),
            'confidence': confidence,
            'scores': scores
        }

    except Exception as e:
        return {'error': f'Keras 声音推理失败: {str(e)}'}


def _infer_pytorch(model: dict, data: dict) -> dict:
    """PyTorch 模型推理"""
    model_path = get_model_full_path(model)
    if not model_path or not os.path.exists(model_path):
        return {'error': '模型文件不存在'}

    try:
        import torch

        # 加载模型
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        pytorch_model = torch.load(model_path, map_location=device)
        pytorch_model.eval()

        # 处理输入...
        return {'error': 'PyTorch 推理暂未实现'}

    except Exception as e:
        return {'error': f'PyTorch 推理失败: {str(e)}'}


def _infer_onnx(model: dict, data: dict) -> dict:
    """ONNX 模型推理"""
    import logging
    logger = logging.getLogger(__name__)

    model_path = get_model_full_path(model)
    if not model_path or not os.path.exists(model_path):
        return {'error': '模型文件不存在'}

    try:
        import onnxruntime as ort
        import numpy as np

        # 创建推理会话
        sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

        # 记录模型输入信息
        for inp in sess.get_inputs():
            logger.info(f"模型输入: name={inp.name}, shape={inp.shape}, type={inp.type}")
        for out in sess.get_outputs():
            logger.info(f"模型输出: name={out.name}, shape={out.shape}, type={out.type}")

        # 根据课程类型处理输入
        course = model.get('course', 'face')

        if course == 'face':
            # 表情识别
            image_b64 = data.get('image', '')
            return _infer_face_image_onnx(sess, image_b64, model)
        elif course == 'audio':
            # 声音情绪
            audio_path = data.get('audio_path')
            return _infer_audio_onnx(sess, audio_path, model)
        else:
            return {'error': f'未知课程类型: {course}'}

    except ImportError:
        return {'error': '请安装 onnxruntime: pip install onnxruntime'}
    except Exception as e:
        return {'error': f'ONNX 推理失败: {str(e)}'}


def _infer_face_image_onnx(sess, image_b64: str, model: dict) -> dict:
    """ONNX 表情图像推理"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        import base64
        import cv2
        import numpy as np
        from config import Config

        # 解码图像
        img_data = base64.b64decode(image_b64.split(',')[-1])
        nparr = np.frombuffer(img_data, np.uint8)
        gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        if gray is None:
            return {'error': '无法解析图像'}

        # 调整大小为模型输入尺寸
        target_size = (48, 48)
        face_resized = cv2.resize(gray, target_size)
        face_arr = face_resized.astype('float32') / 255.0

        # 获取模型输入信息
        input_name = sess.get_inputs()[0].name
        input_shape = sess.get_inputs()[0].shape
        output_name = sess.get_outputs()[0].name

        logger.info(f"表情模型输入形状: {input_shape}")

        # 判断输入格式：NHWC (TensorFlow) vs NCHW (ONNX default)
        # Keras/TensorFlow: (batch, height, width, channels) = (1, 48, 48, 1)
        # ONNX default: (batch, channels, height, width) = (1, 1, 48, 48)
        face_arr = np.expand_dims(face_arr, axis=0)  # (1, 48, 48)

        if len(input_shape) == 4 and input_shape[1] == 1:
            # NCHW 格式: (batch, channels=1, height, width)
            face_arr = np.transpose(face_arr, (0, 2, 1))  # (1, 48, 48) -> (1, 48, 48) - 已经是正确格式
            face_arr = np.expand_dims(face_arr, axis=1)  # (1, 1, 48, 48)
        else:
            # NHWC 格式: (batch, height, width, channels)
            face_arr = np.expand_dims(face_arr, axis=-1)  # (1, 48, 48, 1)

        # 推理
        preds = sess.run([output_name], {input_name: face_arr})[0]
        if len(preds.shape) > 1:
            preds = preds[0]
        emotion_idx = int(np.argmax(preds))
        confidence = float(preds[emotion_idx])

        # 情绪标签（7类：生气、厌恶、恐惧、开心、平静、难过、惊讶）
        emotion_labels = Config.EMOTION_LABELS_CN
        emotion_label = emotion_labels.get(emotion_idx, '未知')

        # 返回详细结果
        scores = {emotion_labels.get(i, f'emotion_{i}'): float(preds[i])
                  for i in range(len(preds))}

        return {
            'success': True,
            'model_id': model.get('id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'emotion_idx': emotion_idx,
            'emotion': emotion_label,
            'confidence': confidence,
            'all_scores': scores
        }

    except Exception as e:
        return {'error': f'ONNX 表情推理失败: {str(e)}'}


def _infer_audio_onnx(sess, audio_path: str, model: dict) -> dict:
    """ONNX 声音情绪推理"""
    try:
        import numpy as np
        import librosa

        if not audio_path or not os.path.exists(audio_path):
            return {'error': '音频文件不存在'}

        # 训练代码中的参数（必须与 train_audio.py 一致）
        SAMPLE_RATE = 16000
        N_MFCC = 40
        N_FFT = 400
        HOP_LENGTH = 160
        MAX_LEN = 100

        # 加载音频
        y, sr = librosa.load(audio_path, sr=SAMPLE_RATE, duration=3.0)

        # 提取 MFCC 特征（与训练代码完全一致）
        mfcc = librosa.feature.mfcc(
            y=y,
            sr=sr,
            n_mfcc=N_MFCC,
            n_fft=N_FFT,
            hop_length=HOP_LENGTH
        )

        # 对齐到固定长度
        if mfcc.shape[1] < MAX_LEN:
            pad_width = MAX_LEN - mfcc.shape[1]
            mfcc = np.pad(mfcc, ((0, 0), (0, pad_width)), mode='constant')
        else:
            mfcc = mfcc[:, :MAX_LEN]

        # 归一化
        mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)

        # 转置得到 (time_steps, n_mfcc) = (100, 40)
        features = mfcc.T.astype('float32')

        # 添加 batch 维度
        features = features[np.newaxis, :, :]  # (1, 100, 40)

        # 获取模型输入信息
        input_name = sess.get_inputs()[0].name
        input_shape = sess.get_inputs()[0].shape
        output_name = sess.get_outputs()[0].name

        # 推理
        preds = sess.run([output_name], {input_name: features})[0]
        if len(preds.shape) > 1:
            preds = preds[0]
        emotion_idx = int(np.argmax(preds))
        confidence = float(preds[emotion_idx])

        # 情绪标签（与训练代码一致：生气、恐惧、开心、平静、难过、惊讶）
        emotion_labels = ['anger', 'fear', 'happy', 'neutral', 'sad', 'surprise']
        emotion_cn_map = {'anger': '生气', 'fear': '恐惧', 'happy': '开心',
                          'neutral': '平静', 'sad': '难过', 'surprise': '惊讶'}
        emotion_emoji_map = {'anger': '😠', 'fear': '😨', 'happy': '😊',
                            'neutral': '😐', 'sad': '😢', 'surprise': '😮'}
        emotion_en = emotion_labels[emotion_idx] if emotion_idx < len(emotion_labels) else 'neutral'
        emotion_cn = emotion_cn_map.get(emotion_en, '平静')

        # 返回详细结果
        scores = {emotion_labels[i]: float(preds[i]) for i in range(len(preds))}

        return {
            'success': True,
            'model_id': model.get('id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'emotion': emotion_en,
            'emotion_cn': emotion_cn,
            'emoji': emotion_emoji_map.get(emotion_en, '😐'),
            'confidence': confidence,
            'scores': scores
        }

    except ImportError:
        return {'error': '请安装 librosa: pip install librosa'}
    except Exception as e:
        return {'error': f'ONNX 声音推理失败: {str(e)}'}


def _infer_face_image(keras_model, image_b64: str, model: dict) -> dict:
    """表情图像推理"""
    try:
        import base64
        import cv2
        import numpy as np

        from config import Config

        # 解码图像
        img_data = base64.b64decode(image_b64.split(',')[-1])
        nparr = np.frombuffer(img_data, np.uint8)
        gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        if gray is None:
            return {'error': '无法解析图像'}

        # 调整大小为模型输入尺寸
        target_size = (48, 48)  # FER2013 默认尺寸
        face_resized = cv2.resize(gray, target_size)
        face_arr = face_resized.astype('float32') / 255.0
        face_arr = np.expand_dims(face_arr, axis=0)
        face_arr = np.expand_dims(face_arr, axis=-1)

        # 推理
        preds = keras_model.predict(face_arr, verbose=0)[0]
        emotion_idx = int(np.argmax(preds))
        confidence = float(preds[emotion_idx])

        # 情绪标签
        emotion_labels = Config.EMOTION_LABELS_CN
        emotion_label = emotion_labels.get(emotion_idx, '未知')

        # 返回详细结果
        scores = {emotion_labels.get(i, f'emotion_{i}'): float(preds[i])
                  for i in range(len(preds))}

        return {
            'success': True,
            'model_id': model.get('id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'emotion_idx': emotion_idx,
            'emotion': emotion_label,
            'confidence': confidence,
            'all_scores': scores
        }

    except Exception as e:
        return {'error': f'表情识别失败: {str(e)}'}


def _infer_eco_features(keras_model, features: list, model: dict) -> dict:
    """生态瓶特征推理"""
    try:
        import numpy as np

        # 转换为 numpy 数组
        X = np.array(features)
        if len(X.shape) == 1:
            X = np.expand_dims(X, axis=0)

        # 推理
        preds = keras_model.predict(X, verbose=0)

        return {
            'success': True,
            'model_id': model.get('id'),
            'model_name': model.get('model_name'),
            'accuracy': model.get('accuracy'),
            'predictions': preds.tolist()
        }

    except Exception as e:
        return {'error': f'生态预测失败: {str(e)}'}


# ── 排行榜对接 ────────────────────────────────────────────────────────────────

def submit_to_leaderboard(
    group_id: str,
    group_name: str,
    course: str,
    accuracy: float,
    model_id: str = None,
    model_name: str = None
) -> dict:
    """
    将自定义模型提交到排行榜

    Args:
        group_id: 小组ID
        group_name: 小组名称
        course: 课程类型
        accuracy: 准确率
        model_id: 模型ID（可选）
        model_name: 模型名称（可选）

    Returns:
        排行榜提交结果
    """
    from services.leaderboard_service import submit_score

    # 课程映射
    course_map = {
        'face': 'emotion_face',
        'emotion': 'emotion_fusion',
        'audio': 'emotion_audio',
        'eco': 'eco_prediction'
    }

    leaderboard_course = course_map.get(course, course)

    # 提交到排行榜
    result = submit_score(
        course=leaderboard_course,
        group_id=group_id,
        group_name=group_name,
        accuracy=accuracy,
        correct=int(accuracy * 50),  # 假设测试集50条
        total=50,
        time_cost_minutes=5,
        config={'model_id': model_id, 'model_name': model_name}
    )

    return result
