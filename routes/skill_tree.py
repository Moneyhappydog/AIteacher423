"""
技能树路由
"""
from flask import Blueprint, request, jsonify
import json
import os
from config import Config

# 导入登录验证装饰器
from routes.auth import login_required

skill_tree_bp = Blueprint('skill_tree', __name__, url_prefix='/skill')
SKILLS_DIR = Config.SKILLS_DIR

# 页面使用的 course 参数与磁盘文件名不一致时在此映射（避免加载到残缺 JSON）
_SKILLS_FILE_BY_COURSE = {
    'emotion_computing': 'emotion_skills.json',
    'eco_bottle': 'eco_skills.json',
}


def _skills_json_path(course: str) -> str:
    filename = _SKILLS_FILE_BY_COURSE.get(course, f'{course}_skills.json')
    return os.path.join(SKILLS_DIR, filename)


def _load_skills(course: str) -> dict:
    """加载技能树配置"""
    path = _skills_json_path(course)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_skills(course: str, data: dict):
    """保存技能树配置"""
    path = _skills_json_path(course)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@skill_tree_bp.route('/')
@login_required
def index():
    """技能树主页"""
    from flask import render_template
    return render_template('skill_tree.html')


@skill_tree_bp.route('/<course>', methods=['GET'])
@login_required
def get_skills(course):
    """获取指定课程的技能树"""
    skills = _load_skills(course)
    return jsonify(skills)


@skill_tree_bp.route('/', methods=['GET'])
def get_default():
    """获取情感计算技能树（默认）"""
    return get_skills('emotion')


@skill_tree_bp.route('/unlock', methods=['POST'])
@login_required
def unlock():
    """解锁技能"""
    data = request.json
    course = data.get('course', 'emotion_computing')
    skill_id = data.get('skill_id')
    lesson = data.get('lesson', 1)

    skills = _load_skills(course)

    # 更新当前课时
    if 'current_lesson' not in skills or lesson > skills['current_lesson']:
        skills['current_lesson'] = lesson

    # 更新已解锁技能
    if 'unlocked_skills' not in skills:
        skills['unlocked_skills'] = []

    if skill_id and skill_id not in skills['unlocked_skills']:
        skills['unlocked_skills'].append(skill_id)

    # 更新技能树中各技能的status
    for cat_key in ['data_skills', 'algorithm_skills', 'ai_skills']:
        if cat_key in skills.get('skill_tree', {}):
            for skill in skills['skill_tree'][cat_key]['skills']:
                if skill['id'] in skills.get('unlocked_skills', []):
                    skill['status'] = 'unlocked'
                elif skill['unlock_lesson'] <= lesson:
                    skill['status'] = 'available'
                else:
                    skill['status'] = 'locked'

    _save_skills(course, skills)
    return jsonify({'success': True, 'skills': skills})


@skill_tree_bp.route('/set_lesson', methods=['POST'])
@login_required
def set_lesson():
    """设置当前课时（批量解锁）"""
    data = request.json
    course = data.get('course', 'emotion_computing')
    lesson = data.get('lesson', 1)

    skills = _load_skills(course)
    skills['current_lesson'] = lesson

    # 根据课时解锁技能
    unlocked = []
    for cat_key in ['data_skills', 'algorithm_skills', 'ai_skills']:
        if cat_key in skills.get('skill_tree', {}):
            for skill in skills['skill_tree'][cat_key]['skills']:
                if skill['unlock_lesson'] <= lesson:
                    skill['status'] = 'unlocked'
                    if skill['id'] not in unlocked:
                        unlocked.append(skill['id'])
                else:
                    skill['status'] = 'locked'

    skills['unlocked_skills'] = unlocked
    _save_skills(course, skills)
    return jsonify({'success': True, 'unlocked_count': len(unlocked), 'skills': skills})
