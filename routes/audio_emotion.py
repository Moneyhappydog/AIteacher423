import os
import uuid
from flask import Blueprint, render_template, request, jsonify, current_app
from services.audio_service import predict_audio

# 导入登录验证装饰器
from routes.auth import login_required

audio_bp = Blueprint('audio', __name__)


@audio_bp.route('/')
@login_required
def index():
    return render_template('audio_emotion.html')


@audio_bp.route('/predict', methods=['POST'])
@login_required
def predict():
    if 'audio' not in request.files:
        return jsonify({'error': '未收到音频文件'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    # 检查是否使用自定义模型
    custom_model_id = request.form.get('model_id')

    # Save uploaded file temporarily
    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)

    ext = '.wav'
    filename = f"audio_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)

    try:
        audio_file.save(filepath)
        model_dir = current_app.config['AUDIO_MODEL_DIR']

        # 如果有自定义模型ID，尝试使用自定义模型
        if custom_model_id:
            try:
                from services.custom_model_service import infer_with_model
                result = infer_with_model(custom_model_id, {'audio_path': filepath})
                if 'error' not in result:
                    return jsonify({
                        'success': True,
                        'emotion': result.get('emotion', 'neutral'),
                        'emotion_cn': result.get('emotion_cn', '平静'),
                        'emoji': result.get('emoji', '😐'),
                        'scores': result.get('scores', {}),
                        'model_source': 'custom',
                        'model_name': result.get('model_name')
                    })
                else:
                    # 自定义模型推理失败，返回错误信息
                    return jsonify({'success': False, 'error': result.get('error', '自定义模型推理失败')}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': f'自定义模型推理失败: {str(e)}'}), 500

        # 使用系统默认模型
        result = predict_audio(filepath, model_dir)

        # 统一返回格式
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})

        return jsonify({
            'success': True,
            'emotion': result['emotion_en'],
            'emotion_cn': result['emotion_cn'],
            'emoji': result.get('emoji', ''),
            'scores': result['scores'],
            'model_source': 'system'
        })
    finally:
        try:
            os.remove(filepath)
        except Exception:
            pass

    return jsonify(result)
