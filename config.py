import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'eduplatform-maogang-secret-2026')
    BASE_DIR = BASE_DIR
    MODELS_DIR = os.path.join(BASE_DIR, 'models')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

    # ── MySQL 数据库配置 ──────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'SQLALCHEMY_DATABASE_URI',
        'mysql+pymysql://root:hkustmao%40com888F@localhost:3306/maogang?charset=utf8mb4'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # ── Redis 缓存配置（高并发优化）─────────────────────────────────────────────
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # ── Flask-Caching 配置 ──
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300  # 缓存 5 分钟

    # ── 数据库连接池配置 ──
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_size': 10,           # 增加连接池大小
        'max_overflow': 20,         # 增加额外连接数
    }

    # ── Session 配置（基于 Flask 签名 Cookie）──────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = 86400 * 7  # 7 天有效期

    # Face emotion model paths
    FACE_EMOTION_MODEL = os.path.join(
        MODELS_DIR, 'trained_models_face', 'fer2013_mini_XCEPTION.119-0.65.hdf5'
    )
    DLIB_LANDMARKS_MODEL = os.path.join(
        MODELS_DIR, 'shape_predictor_68_face_landmarks',
        'shape_predictor_68_face_landmarks.dat'
    )

    # Audio emotion model path (local HuBERT)
    AUDIO_MODEL_DIR = os.path.join(
        MODELS_DIR, 'hubert-base-ch-speech-emotion-recognition'
    )

    # Data directories
    EMOTION_DATA_DIR = os.path.join(BASE_DIR, 'data', 'emotion_data')
    SENSOR_DATA_DIR = os.path.join(BASE_DIR, 'data', 'sensor')
    LEADERBOARD_DIR = os.path.join(BASE_DIR, 'data', 'leaderboard')
    SKILLS_DIR = os.path.join(BASE_DIR, 'data', 'skills')
    CONTROL_DIR = os.path.join(BASE_DIR, 'data', 'control')

    # AI 代码编辑器：各小组沙箱工作目录根（实际路径为 根目录/{小组安全ID}/）
    # 可通过环境变量 EDITOR_WORKSPACE_ROOT 覆盖（部署到服务器时改路径）
    EDITOR_WORKSPACE_ROOT = os.environ.get('EDITOR_WORKSPACE_ROOT') or os.path.join(
        BASE_DIR, 'data', 'editor_workspaces'
    )

    # AI助手配置
    LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')

    # 传感器通道（模拟模式）
    SENSOR_UPLOAD_INTERVAL = 30  # 秒
    SENSOR_CHANNELS = ['temperature', 'humidity', 'light', 'oxygen', 'solar_power']

    # 生态瓶控制阈值
    ECO_TEMP_MIN, ECO_TEMP_MAX = 22, 28  # 摄氏度
    ECO_LIGHT_MIN, ECO_LIGHT_MAX = 100, 500  # lux

    # FER2013 emotion labels
    EMOTION_LABELS_EN = {
        0: 'angry', 1: 'disgust', 2: 'fear',
        3: 'happy', 4: 'sad', 5: 'surprise', 6: 'neutral'
    }
    EMOTION_LABELS_CN = {
        0: '生气', 1: '厌恶', 2: '害怕',
        3: '开心', 4: '难过', 5: '惊讶', 6: '平静'
    }
    EMOTION_EMOJI = {
        0: '😠', 1: '🤢', 2: '😨',
        3: '😊', 4: '😢', 5: '😮', 6: '😐'
    }

    # HuBERT emotion labels
    AUDIO_LABELS_EN = {
        0: 'anger', 1: 'fear', 2: 'happy',
        3: 'neutral', 4: 'sad', 5: 'surprise'
    }
    AUDIO_LABELS_CN = {
        0: '生气', 1: '害怕', 2: '开心',
        3: '平静', 4: '难过', 5: '惊讶'
    }
    AUDIO_EMOJI = {
        0: '😠', 1: '😨', 2: '😊',
        3: '😐', 4: '😢', 5: '😮'
    }

    # ── AI 代码编辑器运行环境 ─────────────────────────────────────────────────────
    # 指定编辑器执行代码时使用的 Python 解释器路径。
    #   - Windows 本地开发：留空或设为 sys.executable（即 conda activate 后的 Python）
    #   - Linux 服务器：可设为 conda 环境路径或 /usr/bin/python3
    #   - 也可通过环境变量 EDITOR_PYTHON_CMD 覆盖
    #   - 若均未设置，回退到 PATH 中的 'python'
    @staticmethod
    def get_editor_python_cmd():
        # 优先级：环境变量 > sys.executable（自动检测当前conda环境） > 'python'
        env_val = os.environ.get('EDITOR_PYTHON_CMD', '').strip()
        if env_val:
            return env_val
        try:
            import sys as _sys
            # sys.executable 即当前 Flask 进程运行的 Python 解释器路径
            if _sys.executable and os.path.isfile(_sys.executable):
                return _sys.executable
        except Exception:
            pass
        return 'python'
