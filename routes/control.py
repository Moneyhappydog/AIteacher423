"""
闭环控制路由
"""
from flask import Blueprint, request, jsonify
from services.control_service import (
    calculate_control_action,
    calculate_control_score,
    log_control_action,
    get_control_log
)
from config import Config

# 导入登录验证装饰器
from routes.auth import login_required

control_bp = Blueprint('control', __name__, url_prefix='/control')


@control_bp.route('/')
@login_required
def index():
    """控制面板页面"""
    from flask import render_template
    return render_template('control_panel.html')


@control_bp.route('/action', methods=['POST'])
@login_required
def action():
    """计算控制动作"""
    try:
        from flask import session
        data = request.json or {}

        # 从 session 获取小组信息
        user_id = session.get('user_id')
        group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')

        current_values = data.get('values', {})
        strategy = data.get('strategy', 'threshold')
        thresholds = data.get('thresholds')

        result = calculate_control_action(current_values, strategy, thresholds=thresholds)

        # 记录动作（写入失败不影响返回值）
        try:
            log_control_action(group_id, result)
        except Exception:
            pass

        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@control_bp.route('/score', methods=['POST'])
@login_required
def score():
    """计算控制得分"""
    try:
        data = request.json or {}
        values = data.get('values', {})
        thresholds = data.get('thresholds')
        result = calculate_control_score(values, thresholds=thresholds)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@control_bp.route('/log/<group_id>', methods=['GET'])
def log(group_id):
    """获取控制日志"""
    records = get_control_log(group_id)
    return jsonify({'group_id': group_id, 'records': records, 'total': len(records)})


@control_bp.route('/log', methods=['GET'])
def log_default():
    """获取控制日志（默认G01）"""
    group_id = request.args.get('group_id', 'G01')
    return log(group_id)


@control_bp.route('/thresholds', methods=['GET'])
def thresholds():
    """获取控制阈值"""
    return jsonify({
        'temp_min': Config.ECO_TEMP_MIN,
        'temp_max': Config.ECO_TEMP_MAX,
        'light_min': Config.ECO_LIGHT_MIN,
        'light_max': Config.ECO_LIGHT_MAX
    })
