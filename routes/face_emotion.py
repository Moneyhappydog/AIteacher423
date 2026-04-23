from flask import Blueprint, render_template, request, jsonify, current_app, session
from services.face_service import predict_frame
import logging

# 导入登录验证装饰器
from routes.auth import login_required

logger = logging.getLogger(__name__)

face_bp = Blueprint('face', __name__)


@face_bp.route('/')
@login_required
def index():
    return render_template('face_emotion.html')


@face_bp.route('/predict', methods=['POST'])
@login_required
def predict():
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'error': '未收到图像数据'}), 400

    # 检查是否使用自定义模型
    custom_model_id = data.get('model_id')
    model_source = 'system'

    if custom_model_id:
        # 使用自定义模型进行推理
        try:
            from services.custom_model_service import infer_with_model
            logger.info(f"使用自定义模型推理: model_id={custom_model_id}")
            result = infer_with_model(custom_model_id, {'image': data['image']})
            logger.info(f"推理结果: {result}")

            if 'error' in result:
                logger.error(f"自定义模型推理错误: {result['error']}")
                return jsonify({'error': result['error']}), 400

            # 包装结果以匹配前端期望的格式
            return jsonify({
                'image': data.get('image'),  # 返回原图，不做标注
                'faces': [{
                    'box': [0, 0, 100, 100],  # 模拟框
                    'emotion_idx': result.get('emotion_idx', 0),
                    'emotion_cn': result.get('emotion', '未知'),
                    'emotion_en': ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral'][result.get('emotion_idx', 6)],
                    'scores': [result['all_scores'].get(k, 0) for k in ['生气', '厌恶', '害怕', '开心', '难过', '惊讶', '平静']]
                }],
                'face_count': 1,
                'model_source': 'custom',
                'model_name': result.get('model_name'),
                'model_accuracy': result.get('accuracy')
            })
        except Exception as e:
            logger.error(f"自定义模型推理异常: {str(e)}", exc_info=True)
            return jsonify({'error': f'自定义模型推理失败: {str(e)}'}), 500

    # 使用系统默认模型
    face_model = current_app.config['FACE_EMOTION_MODEL']
    dlib_model = current_app.config['DLIB_LANDMARKS_MODEL']

    result = predict_frame(data['image'], face_model, dlib_model)
    result['model_source'] = 'system'
    return jsonify(result)
