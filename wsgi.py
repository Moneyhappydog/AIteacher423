"""
WSGI 入口文件 - 用于 Gunicorn + Gevent 部署 Flask-SocketIO 应用

用法:
    gunicorn -c gunicorn_config.py wsgi:app
"""
import os

# 设置环境变量（必须在导入 app 之前）
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

from app import create_app
from services.websocket_service import init_socketio

# 创建 Flask 应用
app = create_app()

# 初始化 SocketIO
socketio = init_socketio(app)
