"""
routes/ai_tutor.py — AI学习助手 API 路由

提供：
- POST /ai/ask         — 问答接口
- POST /ai/code_review — 代码审查接口
- GET  /ai/guide       — 学习引导接口
- GET  /ai/mode       — 查询当前可用模式
"""

from flask import Blueprint, request, jsonify, render_template
from services.ai_tutor_service import (
    get_answer,
    code_review,
    get_learning_guide,
    local_answer,
    call_llm_api,
)
from routes.auth import login_required, get_current_user

ai_tutor_bp = Blueprint('ai_tutor', __name__, url_prefix='/ai')


@ai_tutor_bp.route('/')
@login_required
def page():
    """AI学习助手独立页面"""
    return render_template('ai_tutor.html')


@ai_tutor_bp.route('/ask', methods=['POST'])
@login_required
def ask():
    """
    问答接口。

    请求体：
        {
            "question": str,       # 用户问题（必填）
            "context": dict,       # 额外上下文（可选）：course, lesson, skills
            "prefer_llm": bool,    # 是否优先使用 LLM API（默认 False）
        }

    响应：
        {
            "success": True,
            "answer": str,
            "source": "local" | "llm_api" | "fallback",
            "model": str | None,
            "tokens_used": int,
            "latency_ms": int,
            "mode": "qa" | "code_review" | "suggestion",
        }
    """
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()

    if not question:
        return jsonify({'success': False, 'error': '问题不能为空'}), 400
    if len(question) > 500:
        return jsonify({'success': False, 'error': '问题长度不能超过500字'}), 400

    context = data.get('context') or {}
    prefer_llm = bool(data.get('prefer_llm', False))

    # 尝试接入当前用户信息
    user = get_current_user()
    if user:
        context.setdefault('user', user.username)
        if user.group:
            context.setdefault('course', user.group.course)

    result = get_answer(question, context=context, prefer_llm=prefer_llm)

    return jsonify({
        'success': True,
        'answer': result['answer'],
        'source': result['source'],
        'model': result.get('model'),
        'tokens_used': result.get('tokens_used', 0),
        'latency_ms': result.get('latency_ms', 0),
        'mode': result.get('mode', 'qa'),
    })


@ai_tutor_bp.route('/code_review', methods=['POST'])
@login_required
def do_code_review():
    """
    代码审查接口。

    请求体：
        {
            "code": str,       # 待审查代码
            "language": str,   # 语言类型（默认 python）
        }
    """
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    language = data.get('language', 'python')

    if not code:
        return jsonify({'success': False, 'error': '代码不能为空'}), 400

    result = code_review(code, language=language)

    return jsonify({
        'success': True,
        **result,
    })


@ai_tutor_bp.route('/guide', methods=['GET'])
@login_required
def learning_guide():
    """
    学习引导接口。根据课程和课时返回个性化学习建议。

    Query 参数：
        course: str,   # emotion | ecobottle
        lesson: int,   # 1-4
    """
    course = request.args.get('course')
    lesson = request.args.get('lesson', type=int)

    guide = get_learning_guide(course=course, lesson=lesson)

    return jsonify({
        'success': True,
        'guide': guide,
        'course': course,
        'lesson': lesson,
    })


@ai_tutor_bp.route('/mode', methods=['GET'])
def get_mode_info():
    """
    查询当前 AI 助手可用模式。
    """
    api_key = __import__('config', fromlist=['Config']).Config.LLM_API_KEY
    has_llm = bool(api_key and api_key.strip())

    return jsonify({
        'success': True,
        'llm_available': has_llm,
        'model': __import__('config', fromlist=['Config']).Config.LLM_MODEL if has_llm else None,
        'base_url': __import__('config', fromlist=['Config']).Config.LLM_BASE_URL if has_llm else None,
        'modes': {
            'qa': True,
            'code_review': has_llm,
            'suggestion': has_llm,
            'learning_guide': True,
        },
    })


@ai_tutor_bp.route('/quick_answer', methods=['GET'])
def quick_answer():
    """
    快捷问答（用于悬浮助手前端轮询），返回预设问答库条目列表。
    """
    from services.ai_tutor_service import LOCAL_QA
    items = [
        {"keyword": k, "preview": v[:50] + "..." if v and len(v) > 50 else v}
        for k, v in LOCAL_QA.items()
        if v and k != "默认"
    ]
    return jsonify({'success': True, 'items': items})


@ai_tutor_bp.route('/suggest_topics', methods=['GET'])
def suggest_topics():
    """
    根据当前页面上下文，推荐可问的问题。
    """
    page = request.args.get('page', '')

    # 按页面推荐话题
    suggestions = {
        'face': [
            "什么是人脸检测？",
            "为什么有时检测不到人脸？",
            "置信度是什么意思？",
            "CNN是怎么识别表情的？",
            "如何提高识别准确率？",
        ],
        'audio': [
            "HuBERT是怎么识别声音的？",
            "录音时要注意什么？",
            "音频为什么要16kHz采样率？",
            "声音特征有哪些？",
            "如何让识别更准确？",
        ],
        'emotion': [
            "多模态融合是什么？",
            "表情和声音，哪个更可靠？",
            "情感计算有什么用？",
        ],
        'ecobottle': [
            "时序预测是什么？",
            "多项式回归和LightGBM哪个更好？",
            "ARIMA的AR是什么意思？",
            "如何提高预测准确率？",
            "闭环控制的三种策略有什么区别？",
        ],
        'skill': [
            "技能树怎么解锁新技能？",
            "什么是数据增强？",
            "模型超参数是什么？",
        ],
        'leaderboard': [
            "排行榜是怎么排名的？",
            "如何刷榜拿到更高分？",
            "R²是什么意思？",
        ],
        'default': [
            "什么是人工智能？",
            "表情识别是怎么工作的？",
            "声音情绪是怎么判断的？",
            "时序预测是什么？",
            "如何开始学习？",
        ],
    }

    topics = suggestions.get(page, suggestions['default'])

    return jsonify({
        'success': True,
        'page': page,
        'topics': topics,
    })
