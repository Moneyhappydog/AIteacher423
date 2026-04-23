"""启动脚本 - 运行 香港科技大学（广州）-编程猫青少年AI教育联合实验室教学平台

用法：
    # 开发模式（使用 Flask 内置服务器）
    python run.py

    # 生产模式（使用 Gunicorn + eventlet）
    gunicorn --workers 8 --worker-class eventlet --bind 0.0.0.0:5000 --chdir D:\project_maogang\eduplatform "app:create_app()"

    # 或使用启动脚本
    ./start.sh
"""
import os
import sys

# Suppress TF verbose output
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

from app import create_app

if __name__ == '__main__':
    # 开发模式：使用 Flask-SocketIO 运行
    from services.websocket_service import init_socketio
    app = create_app()
    socketio = init_socketio(app)
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('  [AI Platform] HKUST-GZ & Codemao AI Education Lab Platform started!')
    print(f'  URL: http://127.0.0.1:{port}')
    print('='*50 + '\n')
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
