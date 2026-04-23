"""
模型评估路由
学生功能：
1. 选择模型和测试集进行评估
2. 查看评估进度
3. 查看评估报告
"""
import os
import json
import threading
from flask import Blueprint, request, jsonify, session, render_template, current_app

from routes.auth import login_required
from services.model_eval_service import get_model_eval_service
from services.model_import_service import get_model_import_service
from services.testset_service import get_testset_service

model_eval_bp = Blueprint('model_eval', __name__, url_prefix='/model_eval')


# ─────────────────────────────────────────────────────────────────────────────
# 页面路由
# ─────────────────────────────────────────────────────────────────────────────

@model_eval_bp.route('/')
@login_required
def index():
    """模型评估页面"""
    return render_template('model_eval.html')


# ─────────────────────────────────────────────────────────────────────────────
# 获取可用资源
# ─────────────────────────────────────────────────────────────────────────────

@model_eval_bp.route('/available')
@login_required
def get_available():
    """
    获取当前小组可用的模型和测试集
    """
    group_id = session.get('group_id')
    course = request.args.get('course', 'face')

    # 获取模型
    model_service = get_model_import_service()
    models = model_service.get_group_models(group_id, course)

    # 获取测试集
    testset_service = get_testset_service()
    testsets = testset_service.get_group_available_testsets(course)

    return jsonify({
        'success': True,
        'course': course,
        'models': models,
        'testsets': testsets
    })


@model_eval_bp.route('/my-models')
@login_required
def get_my_models():
    """获取当前小组的模型列表"""
    group_id = session.get('group_id')
    course = request.args.get('course')

    service = get_model_import_service()
    models = service.get_group_models(group_id, course)

    return jsonify({
        'success': True,
        'models': models
    })


@model_eval_bp.route('/testsets')
@login_required
def get_testsets():
    """获取可用的测试集列表"""
    course = request.args.get('course', 'face')

    service = get_testset_service()
    testsets = service.get_group_available_testsets(course)

    return jsonify({
        'success': True,
        'testsets': testsets
    })


# ─────────────────────────────────────────────────────────────────────────────
# 评估任务管理
# ─────────────────────────────────────────────────────────────────────────────

@model_eval_bp.route('/create', methods=['POST'])
@login_required
def create_task():
    """
    创建评估任务

    请求体：
    {
        "model_id": "xxx",
        "testset_id": "xxx",
        "course": "face"
    }
    """
    data = request.json
    group_id = session.get('group_id')

    model_id = data.get('model_id')
    testset_id = data.get('testset_id')
    course = data.get('course', 'face')

    if not model_id:
        return jsonify({'success': False, 'message': '请选择模型'}), 400
    if not testset_id:
        return jsonify({'success': False, 'message': '请选择测试集'}), 400

    service = get_model_eval_service()
    result = service.create_eval_task(model_id, testset_id, course, group_id)

    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@model_eval_bp.route('/start/<task_id>', methods=['POST'])
@login_required
def start_evaluation(task_id):
    """
    开始执行评估任务
    """
    service = get_model_eval_service()

    # 验证任务所有权
    task = service.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    group_id = session.get('group_id')
    if task.get('group_id') != group_id:
        return jsonify({'success': False, 'message': '无权操作此任务'}), 403

    if task.get('status') not in ('pending', 'failed'):
        return jsonify({'success': False, 'message': '任务已在执行中'}), 400

    # 后台线程执行评估，避免阻塞 HTTP；前端可轮询 /progress 查看进度
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            get_model_eval_service().run_evaluation(task_id)

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({'success': True, 'message': '评估已开始', 'task_id': task_id})


@model_eval_bp.route('/progress/<task_id>')
@login_required
def get_progress(task_id):
    """获取任务进度"""
    service = get_model_eval_service()

    task = service.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    # 验证权限
    group_id = session.get('group_id')
    if task.get('group_id') != group_id:
        return jsonify({'success': False, 'message': '无权访问'}), 403

    progress = service.get_task_progress(task_id)

    return jsonify({
        'success': True,
        'task': task,
        'progress': progress
    })


@model_eval_bp.route('/result/<task_id>')
@login_required
def get_result(task_id):
    """获取评估结果"""
    service = get_model_eval_service()

    task = service.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    # 验证权限
    group_id = session.get('group_id')
    if task.get('group_id') != group_id:
        return jsonify({'success': False, 'message': '无权访问'}), 403

    if task.get('status') != 'completed':
        return jsonify({
            'success': False,
            'status': task.get('status'),
            'message': '任务尚未完成'
        })

    report = service.get_task_report(task_id)

    return jsonify({
        'success': True,
        'task': task,
        'report': report
    })


@model_eval_bp.route('/history')
@login_required
def get_history():
    """获取评估历史"""
    group_id = session.get('group_id')
    course = request.args.get('course')
    limit = request.args.get('limit', 20, type=int)

    service = get_model_eval_service()
    tasks = service.get_group_tasks(group_id, course, limit)

    # 简化返回
    history = []
    for task in tasks:
        history.append({
            'task_id': task['task_id'],
            'model_name': task['model_name'],
            'testset_name': task['testset_name'],
            'course': task['course'],
            'status': task['status'],
            'accuracy': task.get('metrics', {}).get('accuracy') if task.get('metrics') else None,
            'created_at': task['created_at'],
            'completed_at': task.get('completed_at')
        })

    return jsonify({
        'success': True,
        'history': history
    })


# ─────────────────────────────────────────────────────────────────────────────
# 排行榜集成
# ─────────────────────────────────────────────────────────────────────────────

@model_eval_bp.route('/leaderboard/<course>')
@login_required
def get_leaderboard(course):
    """
    获取评估排行榜

    注意：排行榜按 course 类型完全隔离，face 和 audio 各自有独立的数据文件
    course 参数格式：'face' 或 'audio'（前端会自动拼接 '_eval' 后缀）
    """
    from services.leaderboard_service import get_leaderboard_service

    # 确定 leaderboard_type
    if course.endswith('_eval'):
        leaderboard_type = course
    else:
        leaderboard_type = f'{course}_eval'

    service = get_leaderboard_service()
    board_data = service.get_leaderboard(leaderboard_type)

    # 返回 records 数组，前端 JS 期望 data.leaderboard 是数组
    return jsonify({
        'success': True,
        'course': course,
        'leaderboard': board_data.get('records', []),
        'updated_at': board_data.get('updated_at')
    })


@model_eval_bp.route('/leaderboard/submit', methods=['POST'])
@login_required
def submit_to_leaderboard():
    """
    手动提交评估结果到排行榜

    注意：此接口确保评估结果写入对应课程类型的排行榜，
    不会影响其他课程类型的排行榜数据
    """
    from flask import session
    from services.model_eval_service import get_model_eval_service
    from models.orm_models import db, LeaderboardRecord

    data = request.json
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'success': False, 'message': '缺少 task_id'}), 400

    service = get_model_eval_service()
    task = service.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    if task.get('status') != 'completed':
        return jsonify({'success': False, 'message': '任务未完成，无法提交'}), 400

    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', f'第{group_id.replace("G","")}组'))

    from services.leaderboard_service import submit_eval_score
    metrics = task.get('metrics') or {}

    # 提交到排行榜 - 传入原始 course，函数内部会转换为正确的 leaderboard_type
    result = submit_eval_score(
        course=task['course'],  # face 或 audio
        group_id=group_id,
        group_name=group_name,
        model_id=task['model_id'],
        model_name=task['model_name'],
        accuracy=metrics.get('accuracy', 0),
        testset_id=task.get('testset_id'),
        metrics=metrics
    )

    # 同时写入数据库（用于管理后台统计）
    try:
        # 确定 leaderboard_type
        course = task['course']
        leaderboard_type = f'{course}_eval'

        # 确保 group_id 是整数
        if isinstance(group_id, str) and group_id.startswith('G'):
            group_id_int = int(group_id[1:]) if group_id[1:].isdigit() else 0
        else:
            group_id_int = int(group_id) if str(group_id).isdigit() else 0

        db_record = LeaderboardRecord(
            group_id=group_id_int,
            course=leaderboard_type,  # face_eval 或 audio_eval
            accuracy=round(metrics.get('accuracy', 0), 4),
            correct_count=int(metrics.get('correct', 0)) if metrics.get('correct') else 0,
            total_count=int(metrics.get('total_samples', 0)) if metrics.get('total_samples') else 0,
            time_cost_seconds=0,
            model_file=task['model_id'],
            model_config={'model_name': task['model_name'], 'testset_id': task.get('testset_id')},
            composite_score=round(metrics.get('accuracy', 0) * 100, 2),
            innovation_score=70,
            is_public=True
        )
        db.session.add(db_record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import logging
        logging.warning(f"排行榜记录写入数据库失败: {e}")

    return jsonify({
        'success': True,
        'message': f'提交成功！排名：第{result["rank"]}名',
        'rank': result['rank'],
        'accuracy': result.get('accuracy'),
        'total_teams': result.get('total_teams')
    })


# ─────────────────────────────────────────────────────────────────────────────
# 管理员接口
# ─────────────────────────────────────────────────────────────────────────────

@model_eval_bp.route('/admin/all')
@login_required
def get_all_tasks():
    """获取所有评估任务（管理员/教师用）"""
    from routes.auth import admin_or_teacher_required

    course = request.args.get('course')
    limit = request.args.get('limit', 50, type=int)

    # 管理员可以查看所有任务
    tasks = []
    service = get_model_eval_service()
    eval_dir = service.EVAL_RESULTS_DIR

    if os.path.exists(eval_dir):
        for task_id in os.listdir(eval_dir):
            task = service.get_task(task_id)
            if task:
                if course and task.get('course') != course:
                    continue
                tasks.append(task)

    tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    tasks = tasks[:limit]

    return jsonify({
        'success': True,
        'tasks': tasks,
        'total': len(tasks)
    })
