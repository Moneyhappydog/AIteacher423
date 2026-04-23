"""
WebSocket 实时推送服务
统一管理排行榜等数据的实时推送
"""
import os
from flask_socketio import SocketIO, emit, join_room, leave_room

# 全局 SocketIO 实例（在 app.py 初始化时赋值）
socketio: SocketIO = None


def init_socketio(app):
    """
    初始化 SocketIO 并注册事件处理器
    应在 app.py 的 create_app() 中调用

    注意：使用 Redis 作为消息队列，支持多 worker 环境
    """
    global socketio

    # Redis 连接配置
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='eventlet',  # 使用 eventlet 支持 WebSocket
        message_queue=redis_url,  # Redis 消息队列，支持多 worker
        channel='eduplatform-socketio',
        ping_timeout=60,
        ping_interval=25,
        logger=False,
        engineio_logger=False
    )

    register_socket_events(socketio)
    return socketio


def get_socketio() -> SocketIO:
    """获取全局 SocketIO 实例"""
    return socketio


def register_socket_events(sio: SocketIO):
    """注册所有 WebSocket 事件"""

    @sio.on('connect')
    def on_connect():
        emit('connected', {'status': 'ok'})

    @sio.on('disconnect')
    def on_disconnect():
        pass

    # ── 排行榜订阅 ──────────────────────────────────────────────
    @sio.on('subscribe_leaderboard')
    def on_subscribe_leaderboard(data):
        """
        客户端订阅指定课程排行榜的实时更新
        data: { course: 'emotion_face' | 'emotion_audio' | ... }
        """
        course = data.get('course', 'emotion_face')
        room = f'leaderboard_{course}'
        join_room(room)
        emit('subscribed', {'course': course, 'room': room})

    @sio.on('unsubscribe_leaderboard')
    def on_unsubscribe_leaderboard(data):
        """客户端取消订阅"""
        course = data.get('course', 'emotion_face')
        room = f'leaderboard_{course}'
        leave_room(room)
        emit('unsubscribed', {'course': course})

    # ── 全部排行榜订阅 ──────────────────────────────────────────
    @sio.on('subscribe_all_boards')
    def on_subscribe_all():
        """订阅所有排行榜更新"""
        join_room('all_boards')
        emit('subscribed_all', {'room': 'all_boards'})

    @sio.on('unsubscribe_all_boards')
    def on_unsubscribe_all():
        leave_room('all_boards')
        emit('unsubscribed_all', {})


# ── 推送函数（供其他 service 调用）─────────────────────────────────

def broadcast_leaderboard_update(course: str, board_data: dict):
    """
    广播指定课程排行榜的更新事件
    在 leaderboard_service 的 submit_score 等函数中调用
    """
    if socketio is None:
        return

    # 构建推送 payload（精简数据）
    records = board_data.get('records', [])
    top5 = sorted(records, key=lambda x: x.get('rank', 99))[:5]
    top3 = sorted(records, key=lambda x: x.get('rank', 99))[:3]

    payload = {
        'course': course,
        'top5': top5,
        'top3': top3,
        'total_records': len(records),
        'updated_at': board_data.get('updated_at'),
        'updated_by': board_data.get('last_updated_by')
    }

    # 推送到该课程专属房间
    socketio.emit('leaderboard_update', payload, room=f'leaderboard_{course}')
    # 同时推送到全房间
    socketio.emit('leaderboard_update', payload, room='all_boards')


def broadcast_mini_leaderboard(course: str, top5_data: dict):
    """
    广播迷你排行榜更新（用于 face_emotion / audio_emotion 页面内嵌小版）
    """
    if socketio is None:
        return
    payload = {
        'course': course,
        'records': top5_data.get('records', []),
        'updated_at': top5_data.get('updated_at')
    }
    socketio.emit('mini_leaderboard_update', payload, room=f'leaderboard_{course}')


def broadcast_skill_update(group_id: str, skill_data: dict):
    """
    广播技能树更新
    """
    if socketio is None:
        return
    socketio.emit('skill_update', skill_data, room=f'group_{group_id}')
    socketio.emit('skill_update', skill_data, room='all_groups')
