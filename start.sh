#!/bin/bash
# EduPlatform 高并发启动脚本
# 使用 Gunicorn + eventlet 支持 WebSocket 和高并发

# 设置项目目录
PROJECT_DIR="D:/project_maogang/eduplatform"
cd "$PROJECT_DIR"

# 激活 conda 环境
source ~/anaconda3/etc/profile.d/conda.sh
conda activate base

# 启动 Gunicorn
exec gunicorn \
    --workers 4 \
    --worker-class eventlet \
    --worker-connections 1000 \
    --bind 0.0.0.0:5000 \
    --timeout 300 \
    --keep-alive 65 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile logs/gunicorn_access.log \
    --error-logfile logs/gunicorn_error.log \
    --log-level info \
    "app:create_app()"
