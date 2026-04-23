import os
from flask import Flask
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config.get('EMOTION_DATA_DIR', os.path.join(os.path.dirname(__file__), 'data', 'emotion_data')), exist_ok=True)

    # ── 初始化 Redis 缓存 ─────────────────────────────────────────────────────
    from utils import cache
    from utils import init_cache as redis_init_cache
    redis_init_cache(app, {
        'CACHE_TYPE': 'RedisCache',
        'CACHE_REDIS_URL': app.config['REDIS_URL'],
        'CACHE_DEFAULT_TIMEOUT': app.config.get('CACHE_DEFAULT_TIMEOUT', 300)
    })

    # ── 初始化数据库 ──────────────────────────────────────────────────────────
    from models.orm_models import db
    db.init_app(app)

    # ── 初始化 WebSocket（需在蓝图注册前初始化）─────────────────────────────────
    from services.websocket_service import init_socketio
    socketio = init_socketio(app)

    # ── 注册蓝图 ──────────────────────────────────────────────────────────────
    from routes.main import main_bp
    from routes.face_emotion import face_bp
    from routes.audio_emotion import audio_bp
    from routes.ecobottle import eco_bp
    from routes.emotion_computing import emotion_bp
    from routes.emotion_data import emotion_data_bp
    from routes.leaderboard import leaderboard_bp
    from routes.skill_tree import skill_tree_bp
    from routes.sensor_data import sensor_data_bp
    from routes.control import control_bp
    from routes.evaluation import evaluation_bp
    from routes.auth import auth_bp  # 认证蓝图
    from routes.ai_tutor import ai_tutor_bp  # AI助手蓝图
    from routes.editor import editor_bp  # Monaco编辑器蓝图
    from routes.admin import admin_bp  # 管理员控制台蓝图
    from routes.custom_model import custom_model_bp  # 自定义模型管理蓝图
    from routes.audio_data import audio_data_bp  # 音频数据采集蓝图
    from routes.export import export_bp  # 数据导出蓝图
    from routes.face_preprocess import face_preprocess_bp  # 人脸数据预处理蓝图
    from routes.audio_preprocess import audio_preprocess_bp  # 音频数据预处理蓝图
    from routes.testset import testset_bp  # 测试集管理蓝图
    from routes.model_import import model_import_bp  # 模型导入蓝图
    from routes.model_eval import model_eval_bp  # 模型评估蓝图

    app.register_blueprint(main_bp)
    app.register_blueprint(face_bp, url_prefix='/face')
    app.register_blueprint(audio_bp, url_prefix='/audio')
    app.register_blueprint(eco_bp, url_prefix='/eco')
    app.register_blueprint(emotion_bp, url_prefix='/emotion')
    app.register_blueprint(emotion_data_bp, url_prefix='/data')
    app.register_blueprint(leaderboard_bp, url_prefix='/leaderboard')
    app.register_blueprint(skill_tree_bp, url_prefix='/skill')
    app.register_blueprint(sensor_data_bp, url_prefix='/sensor')
    app.register_blueprint(control_bp, url_prefix='/control')
    app.register_blueprint(evaluation_bp, url_prefix='/eval')
    app.register_blueprint(auth_bp)   # /auth/*
    app.register_blueprint(ai_tutor_bp)  # /ai/*
    app.register_blueprint(editor_bp)  # /editor/*
    app.register_blueprint(admin_bp)   # /admin/*
    app.register_blueprint(custom_model_bp)  # /api/models/*
    app.register_blueprint(audio_data_bp)   # /audio_data/*
    app.register_blueprint(export_bp)   # /export/*
    app.register_blueprint(face_preprocess_bp, url_prefix='/face_preprocess')  # /face_preprocess/*
    app.register_blueprint(audio_preprocess_bp, url_prefix='/audio_preprocess')  # /audio_preprocess/*
    app.register_blueprint(testset_bp)  # /testset/*
    app.register_blueprint(model_import_bp)  # /model_import/*
    app.register_blueprint(model_eval_bp)  # /model_eval/*

    return app


if __name__ == '__main__':
    from services.websocket_service import init_socketio
    app = create_app()
    socketio = init_socketio(app)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
