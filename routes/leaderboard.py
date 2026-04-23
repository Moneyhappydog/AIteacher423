"""
排行榜路由
"""
from flask import Blueprint, request, jsonify
from functools import wraps

# 导入登录验证装饰器
from routes.auth import login_required

from services.leaderboard_service import (
    get_leaderboard,
    get_all_leaderboards,
    submit_score,
    get_group_record,
    get_class_stats,
    eco_submit_score,
    eco_control_submit
)

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')


@leaderboard_bp.route('/')
@login_required
def index():
    """排行榜主页"""
    from flask import render_template
    return render_template('leaderboard.html')


@leaderboard_bp.route('/face', methods=['GET'])
def face_leaderboard():
    """表情识别排行榜"""
    board = get_leaderboard('emotion_face')
    return jsonify(board)


@leaderboard_bp.route('/audio', methods=['GET'])
def audio_leaderboard():
    """声音识别排行榜"""
    board = get_leaderboard('emotion_audio')
    return jsonify(board)


@leaderboard_bp.route('/fusion', methods=['GET'])
def fusion_leaderboard():
    """多模态融合排行榜"""
    board = get_leaderboard('emotion_fusion')
    return jsonify(board)


@leaderboard_bp.route('/<course>', methods=['GET'])
def get_board(course):
    """获取指定课程排行榜"""
    board = get_leaderboard(course)
    return jsonify(board)


@leaderboard_bp.route('/all', methods=['GET'])
def all_boards():
    """获取所有排行榜概览"""
    boards = get_all_leaderboards()
    return jsonify(boards)


@leaderboard_bp.route('/submit', methods=['POST'])
@login_required
def submit():
    """提交刷榜成绩"""
    from flask import session
    data = request.json
    course = data.get('course', 'emotion_face')

    # 从 session 获取当前登录用户的小组信息，不允许伪造
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', f'第{group_id.replace("G","")}组'))

    accuracy = float(data.get('accuracy', 0))
    correct = int(data.get('correct', 0))
    total = int(data.get('total', 0))
    time_cost_minutes = int(data.get('time_cost_minutes', 0))
    config = data.get('config', {})
    innovation_score = data.get('innovation_score')

    result = submit_score(
        course=course,
        group_id=group_id,
        group_name=group_name,
        accuracy=accuracy,
        correct=correct,
        total=total,
        time_cost_minutes=time_cost_minutes,
        config=config,
        innovation_score=innovation_score
    )
    return jsonify(result)


@leaderboard_bp.route('/eco/submit', methods=['POST'])
@login_required
def eco_submit():
    """生态瓶预测榜单提交"""
    from flask import session
    data = request.json

    # 从 session 获取当前登录用户的小组信息
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', '第1组'))

    result = eco_submit_score(
        group_id=group_id,
        group_name=group_name,
        mae_temperature=float(data.get('mae_temperature', 0)),
        mae_light=float(data.get('mae_light', 0)),
        mae_battery=float(data.get('mae_battery', 0)),
        training_time_seconds=int(data.get('training_time_seconds', 0)),
        config=data.get('config', {})
    )
    return jsonify(result)


@leaderboard_bp.route('/eco/control/submit', methods=['POST'])
@login_required
def eco_control():
    """生态瓶控制榜提交"""
    from flask import session
    data = request.json

    # 从 session 获取当前登录用户的小组信息
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', '第1组'))

    result = eco_control_submit(
        group_id=group_id,
        group_name=group_name,
        temp_score=float(data.get('temp_score', 0)),
        light_score=float(data.get('light_score', 0)),
        energy_score=float(data.get('energy_score', 0)),
        total_seconds=int(data.get('total_seconds', 0)),
        strategy=data.get('strategy', 'threshold')
    )
    return jsonify(result)


@leaderboard_bp.route('/group/<group_id>', methods=['GET'])
def group_record(group_id):
    """获取指定小组所有榜单记录"""
    courses = ['emotion_face', 'emotion_audio', 'emotion_fusion',
               'eco_collect', 'eco_discovery', 'eco_prediction', 'eco_control']
    result = {}
    for course in courses:
        rec = get_group_record(course, group_id)
        if rec:
            result[course] = rec
    return jsonify(result)


@leaderboard_bp.route('/stats', methods=['GET'])
def stats():
    """获取班级数据统计"""
    course = request.args.get('course')
    if course:
        return jsonify(get_class_stats(course))
    return jsonify(get_class_stats())


@leaderboard_bp.route('/mini', methods=['GET'])
def mini():
    """获取排行榜迷你版（用于嵌入各页面）"""
    course = request.args.get('course', 'emotion_face')
    board = get_leaderboard(course)
    records = board.get('records', [])[:5]  # 只返回前5名
    return jsonify({
        'course': course,
        'records': records,
        'updated_at': board.get('updated_at')
    })
