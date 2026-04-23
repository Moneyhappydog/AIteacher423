"""
刷榜评估与成果展示路由
"""
from flask import Blueprint, request, jsonify
import json
import os
from datetime import datetime
from config import Config

# 导入登录验证装饰器
from routes.auth import login_required

evaluation_bp = Blueprint('evaluation', __name__, url_prefix='/eval')
REPORTS_FILE = os.path.join(Config.BASE_DIR, 'data', 'experiment_reports.json')


def _load_reports() -> dict:
    if os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_reports(reports: dict):
    with open(REPORTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)


@evaluation_bp.route('/submit', methods=['POST'])
@login_required
def submit():
    """提交研究报告"""
    from flask import session
    data = request.json
    # 从 session 获取小组信息
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', f'第{group_id.replace("G","")}组'))

    course = data.get('course', 'emotion_computing')
    report = data.get('report', {})
    awards = data.get('awards', [])
    composite_score = data.get('composite_score', 0)

    reports = _load_reports()
    key = f"{course}_{group_id}"

    reports[key] = {
        'group_id': group_id,
        'group_name': data.get('group_name', f'第{group_id.replace("G","")}组'),
        'course': course,
        'report': report,
        'awards': awards,
        'composite_score': composite_score,
        'timestamp': datetime.now().isoformat()
    }

    _save_reports(reports)
    return jsonify({'success': True, 'key': key})


@evaluation_bp.route('/rankings', methods=['GET'])
def rankings():
    """获取最终排名"""
    course = request.args.get('course', 'emotion_computing')
    reports = _load_reports()

    course_reports = [
        v for v in reports.values()
        if v.get('course') == course
    ]
    course_reports.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

    return jsonify({
        'course': course,
        'rankings': [
            {
                'rank': i + 1,
                'group_id': r['group_id'],
                'group_name': r['group_name'],
                'composite_score': r.get('composite_score'),
                'awards': r.get('awards', [])
            }
            for i, r in enumerate(course_reports)
        ]
    })


@evaluation_bp.route('/report/<course>/<group_id>', methods=['GET'])
def get_report(course, group_id):
    """获取小组研究报告"""
    reports = _load_reports()
    key = f"{course}_{group_id}"
    report = reports.get(key, {})
    return jsonify(report)


@evaluation_bp.route('/award', methods=['GET'])
def award():
    """获取获奖名单"""
    course = request.args.get('course', 'emotion_computing')
    reports = _load_reports()

    course_reports = [v for v in reports.values() if v.get('course') == course]
    course_reports.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

    awards_map = {
        1: '刷榜冠军',
        2: '算法达人',
        3: '全能团队',
    }

    result = []
    for i, r in enumerate(course_reports[:5]):
        rank = i + 1
        result.append({
            'rank': rank,
            'group_id': r['group_id'],
            'group_name': r['group_name'],
            'composite_score': r.get('composite_score'),
            'awards': [awards_map.get(rank, '优秀团队')]
        })

    return jsonify({'course': course, 'awards': result})
