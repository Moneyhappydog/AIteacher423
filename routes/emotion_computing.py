"""
情感计算路由 - 新模块
支持多策略融合、可配置权重、双模型独立选择
"""
from flask import Blueprint, render_template, request, jsonify, current_app
from services.emotion_fusion_service import analyze_emotion, EmotionFusion
import base64
import os
import uuid

# 导入登录验证装饰器
from routes.auth import login_required

emotion_bp = Blueprint('emotion', __name__, template_folder='../templates')


@emotion_bp.route('/')
@login_required
def index():
    return render_template('emotion_computing.html')


@emotion_bp.route('/config', methods=['GET'])
@login_required
def get_config():
    """获取融合配置信息（策略列表、当前配置）"""
    return jsonify({
        'success': True,
        'strategies': EmotionFusion.get_available_strategies(),
        'current_config': {
            'face_weight': 0.6,
            'audio_weight': 0.4,
            'strategy': 'weighted_average',
            'strategy_name': '加权平均'
        }
    })


@emotion_bp.route('/fuse', methods=['POST'])
@login_required
def fuse():
    """
    融合分析接口
    接收: {
        'face_data': {'emotion': 'happy', 'scores': {...}},
        'audio_data': {'emotion': 'happy', 'scores': {...}},
        'face_weight': 0.6,        # 表情权重 (0.0 ~ 1.0)
        'audio_weight': 0.4,       # 声音权重 (可选，会自动计算为 1 - face_weight)
        'strategy': 'weighted_average'  # 融合策略
    }
    """
    try:
        data = request.json or {}
        face_data = data.get('face_data')
        audio_data = data.get('audio_data')

        # 获取权重参数
        face_weight = data.get('face_weight', 0.6)
        # 确保权重在有效范围内
        face_weight = max(0.0, min(1.0, float(face_weight)))

        # 获取策略参数
        strategy = data.get('strategy', 'weighted_average')

        # 直接使用已识别的结果进行融合
        face_result = face_data if face_data else None
        audio_result = audio_data if audio_data else None

        # 融合分析（使用可配置参数）
        result = analyze_emotion(face_result, audio_result,
                                 face_weight=face_weight, strategy=strategy)

        # 记录使用的配置
        result['used_config'] = {
            'face_weight': face_weight,
            'audio_weight': 1.0 - face_weight,
            'strategy': strategy
        }

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@emotion_bp.route('/predict_face', methods=['POST'])
@login_required
def predict_face():
    """仅表情识别"""
    try:
        data = request.json
        image_data = data.get('image')
        custom_model_id = data.get('face_model_id')  # 表情模型ID
        model_id = data.get('model_id')  # 兼容旧参数

        # 优先使用 face_model_id
        if not custom_model_id:
            custom_model_id = model_id

        if not image_data:
            return jsonify({'success': False, 'error': '没有图片数据'})

        # 如果有自定义模型ID，尝试使用自定义模型
        if custom_model_id:
            try:
                from services.custom_model_service import infer_with_model
                result = infer_with_model(custom_model_id, {'image': image_data})
                if 'error' not in result:
                    return jsonify({
                        'success': True,
                        'emotion': ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral'][result.get('emotion_idx', 6)],
                        'emotion_cn': result.get('emotion', '平静'),
                        'scores': result.get('all_scores', {}),
                        'model_source': 'custom',
                        'model_id': custom_model_id,
                        'model_name': result.get('model_name')
                    })
            except Exception as e:
                print(f'自定义模型推理失败: {e}')

        # 使用系统默认模型
        face_model = current_app.config['FACE_EMOTION_MODEL']
        dlib_model = current_app.config['DLIB_LANDMARKS_MODEL']

        from services.face_service import predict_frame
        result = predict_frame(image_data, face_model, dlib_model)

        # 转换为前端期望的格式
        if result.get('faces') and len(result['faces']) > 0:
            face = result['faces'][0]
            scores_dict = {}
            label_en = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
            for i, score in enumerate(face['scores']):
                scores_dict[label_en[i]] = float(score)

            return jsonify({
                'success': True,
                'emotion': face['emotion_en'],
                'emotion_cn': face['emotion_cn'],
                'scores': scores_dict,
                'image': result.get('image'),
                'model_source': 'system',
                'model_name': 'FER2013 Mini-XCEPTION'
            })
        else:
            return jsonify({'success': False, 'error': '未检测到人脸'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@emotion_bp.route('/predict_audio', methods=['POST'])
@login_required
def predict_audio():
    """仅声音识别"""
    try:
        audio_file = request.files.get('audio')
        custom_model_id = request.form.get('audio_model_id')  # 声音情绪模型ID
        model_id = request.form.get('model_id')  # 兼容旧参数

        # 优先使用 audio_model_id
        if not custom_model_id:
            custom_model_id = model_id

        if not audio_file:
            return jsonify({'success': False, 'error': '没有音频文件'})

        # Save uploaded file temporarily
        upload_dir = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)

        filename = f"audio_{uuid.uuid4().hex}.webm"
        filepath = os.path.join(upload_dir, filename)

        try:
            audio_file.save(filepath)

            # 如果有自定义模型ID，尝试使用自定义模型
            if custom_model_id:
                try:
                    from services.custom_model_service import infer_with_model
                    import json
                    # 读取音频文件并转为 base64
                    with open(filepath, 'rb') as f:
                        audio_b64 = base64.b64encode(f.read()).decode('utf-8')
                    result = infer_with_model(custom_model_id, {'audio': audio_b64})
                    if 'error' not in result:
                        # 音频模型的情绪标签映射（6类）
                        emotion_labels = ['anger', 'fear', 'happy', 'neutral', 'sad', 'surprise']
                        emotion_idx = result.get('emotion_idx', 3)
                        emotion = emotion_labels[emotion_idx] if 0 <= emotion_idx < 6 else 'neutral'
                        emotion_cn_map = {
                            'anger': '生气', 'fear': '害怕', 'happy': '开心',
                            'neutral': '平静', 'sad': '难过', 'surprise': '惊讶'
                        }
                        return jsonify({
                            'success': True,
                            'emotion': emotion,
                            'emotion_cn': result.get('emotion', emotion_cn_map.get(emotion, '平静')),
                            'scores': result.get('all_scores', {}),
                            'model_source': 'custom',
                            'model_id': custom_model_id,
                            'model_name': result.get('model_name')
                        })
                except Exception as e:
                    print(f'自定义音频模型推理失败: {e}')

            # 使用系统默认模型
            model_dir = current_app.config['AUDIO_MODEL_DIR']
            from services.audio_service import predict_audio as audio_predict
            raw_result = audio_predict(filepath, model_dir)

            # 转换为前端期望的格式
            if 'error' in raw_result:
                return jsonify({'success': False, 'error': raw_result['error']})

            return jsonify({
                'success': True,
                'emotion': raw_result['emotion_en'],
                'emotion_cn': raw_result['emotion_cn'],
                'scores': raw_result['scores'],
                'model_source': 'system',
                'model_name': 'HuBERT Speech Emotion'
            })
        finally:
            try:
                os.remove(filepath)
            except Exception:
                pass

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@emotion_bp.route('/models', methods=['GET'])
@login_required
def get_models():
    """获取可用的表情和声音情绪模型列表"""
    try:
        from services.custom_model_service import get_custom_models

        # 获取表情模型
        face_models = get_custom_models('face')

        # 获取声音情绪模型
        audio_models = get_custom_models('audio')

        return jsonify({
            'success': True,
            'face_models': face_models,
            'audio_models': audio_models
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
