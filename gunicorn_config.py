"""
Gunicorn 配置文件 - 高并发优化配置
适用于 香港科技大学（广州）-编程猫青少年AI教育联合实验室教学平台

服务器配置: Ubuntu 16GB RAM, 4核CPU

优化场景: 30用户同时上传、下载、AI推理

⚠️ 重要说明:
- AI 推理任务建议异步化（Celery/RQ）
- 当前配置为临时优化，长期建议分离 AI 服务

用法:
    gunicorn -c gunicorn_config.py wsgi:app
"""
import os
import multiprocessing

# ==================== 性能计算 ====================
# 服务器配置
CPU_CORES = multiprocessing.cpu_count()  # 4 核
RAM_GB = 16  # GB

# 计算建议值
# 每个 worker 约占用 300-500MB 内存（加载模型后）
# 建议保留 4GB 给系统，剩余 12GB 给 workers
RECOMMENDED_WORKERS = max(2, CPU_CORES * 2)  # 4 核 * 2 = 8 workers

# ==================== 服务配置 ====================
bind = "0.0.0.0:5000"

# ⚠️ 使用 eventlet - Flask-SocketIO 原生支持 WebSocket
# 注意: eventlet 只支持单 worker，但协程可处理高并发
workers = 1
worker_class = "eventlet"
worker_connections = 1000

# eventlet 猴子补丁（必须最早执行）
import eventlet
eventlet.monkey_patch()

# ==================== 日志配置 ====================
timeout = 300          # 请求超时 5 分钟
graceful_timeout = 30  # 优雅重启超时
keepalive = 5          # keep-alive 时间

# ⚠️ 新增：worker 启动超时
# AI 模型加载可能较慢，需要足够超时时间
worker_tmp_dir = "/dev/shm"  # 使用内存文件系统加速临时文件

# ==================== 内存管理 ====================
# ⚠️ 新增：防止内存泄漏导致服务器崩溃
max_requests = 200              # worker 处理多少请求后重启
max_requests_jitter = 30        # 随机抖动，避免同时重启
preload_app = True               # 预加载应用，共享内存

# ==================== 日志配置 ====================
accesslog = "-"         # 输出到 stdout
errorlog = "-"          # 输出到 stderr
loglevel = "info"       # 日志级别
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ==================== 进程钩子 ====================
def on_starting(server):
    """服务启动时执行"""
    print("=" * 60)
    print("  [AI Platform] 启动中...")
    print(f"  Workers: {server.app.cfg.workers}")
    print(f"  Worker Class: {server.app.cfg.worker_class}")
    print(f"  Timeout: {server.app.cfg.timeout}s")
    print("=" * 60)

def post_fork(server, worker):
    """Worker 进程创建后执行"""
    # 抑制 TensorFlow 日志
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
    
    # ⚠️ 新增：限制 TensorFlow 线程数，避免多 worker 争抢 CPU
    try:
        import tensorflow as tf
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.threading.set_intra_op_parallelism_threads(1)
    except ImportError:
        pass

def worker_exit(server, worker):
    """Worker 进程退出时执行"""
    pass


# ==================== 长期优化建议 ====================
"""
【架构优化建议】

当前问题：
- AI 推理是 CPU 密集型，会阻塞其他请求
- 单服务器处理所有请求，扩展性差

建议方案：

1. 【短期】异步任务队列（推荐）
   - 使用 Celery + Redis
   - AI 推理作为后台任务
   - 用户提交请求后立即返回，任务完成后通知

   架构示例：
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │  Web    │────▶│  Redis  │────▶│  Worker │
   │ Server  │     │  Queue  │     │ (AI推理)│
   └─────────┘     └─────────┘     └─────────┘
        │                             │
        └────────── WebSocket ◀────────┘
                   (通知结果)

2. 【中期】服务分离
   - Web 服务：处理上传/下载/用户交互
   - AI 服务：专门处理推理任务
   - 使用 Nginx 反向代理分发请求

3. 【长期】Kubernetes 容器化
   - Web 服务：多副本自动扩缩容
   - AI 服务：GPU 独立部署
   - 数据库：云数据库

4. 【Nginx 优化】（已部署的情况下）
   - 启用 gzip 压缩
   - 设置合理的 client_max_body_size
   - 启用静态文件缓存
"""
