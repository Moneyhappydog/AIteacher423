"""Phase 1 rule diagnosis for the AI tutor."""
from __future__ import annotations

from typing import Any


HELP_KEYWORDS = (
    '不会', '怎么做', '下一步', '为什么', '不行', '没结果', '看不懂',
    'help', 'next', 'why', 'how',
)


def _text(value: Any) -> str:
    return str(value or '').strip()


def _lower_question(question: str | None) -> str:
    return _text(question).lower()


def _has_help_intent(question: str | None) -> bool:
    q = _lower_question(question)
    return any(keyword in q for keyword in HELP_KEYWORDS)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _event_names(recent_events: list[dict] | None) -> set[str]:
    return {
        _text(event.get('event_name'))
        for event in (recent_events or [])
        if event.get('event_name')
    }


def _result_emotion(result: Any) -> Any:
    if isinstance(result, dict):
        return result.get('emotion') or result.get('label') or result.get('result')
    return result


def _rule(
    diagnosis: str,
    next_step: str,
    tips: list[str] | None = None,
    confidence: float = 0.8,
    mode: str = 'guide',
) -> dict:
    return {
        'diagnosis': diagnosis,
        'rule_hits': [diagnosis],
        'next_step': next_step,
        'tips': tips or [],
        'confidence': confidence,
        'mode': mode,
        'source': 'rule',
    }


def _no_rule() -> dict:
    return {
        'diagnosis': None,
        'rule_hits': [],
        'next_step': None,
        'tips': [],
        'confidence': 0.0,
        'mode': 'qa',
        'source': 'rule',
    }


def detect_emotion_computing_rules(
    snapshot: dict | None,
    recent_events: list[dict] | None = None,
    question: str | None = None,
) -> dict:
    """Detect phase 1 stuck states for the multimodal emotion course."""
    snap = snapshot or {}
    names = _event_names(recent_events)
    asks_help = _has_help_intent(question)

    face_model_id = snap.get('face_model_id')
    audio_model_id = snap.get('audio_model_id')
    camera_started = bool(snap.get('camera_started'))
    recording = bool(snap.get('recording'))
    last_face_result = snap.get('last_face_result')
    last_audio_result = snap.get('last_audio_result')
    last_fusion_result = snap.get('last_fusion_result')
    selected_toy = snap.get('selected_toy')

    if not _has_value(face_model_id):
        return _rule(
            'emotion_missing_face_model',
            '先选择一个表情模型，再开始摄像头识别。',
            ['如果不确定，先用默认推荐模型。'],
            confidence=0.75,
        )

    if not _has_value(audio_model_id):
        return _rule(
            'emotion_missing_audio_model',
            '再选择一个声音模型，后面才能把表情和声音结果合在一起看。',
            ['表情模型和声音模型都选好后，再开始采集。'],
            confidence=0.75,
        )

    if not camera_started and not _has_value(last_face_result):
        return _rule(
            'emotion_missing_camera_start',
            '点击开始摄像头，先得到一个表情识别结果。',
            ['请站在画面中央，保证脸部光线清楚。'],
            confidence=0.8,
        )

    if _has_value(last_face_result) and not _has_value(last_audio_result) and not recording:
        return _rule(
            'emotion_missing_audio_input',
            '你已经有表情结果了，下一步点击开始录音，让系统也读取声音情绪。',
            ['录音 3 到 5 秒就够了，周围尽量安静。'],
            confidence=0.9 if asks_help else 0.82,
        )

    if (
        (_has_value(last_face_result) or 'face_result_updated' in names)
        and (_has_value(last_audio_result) or 'audio_result_updated' in names)
        and not _has_value(last_fusion_result)
    ):
        return _rule(
            'emotion_has_single_modal_result_but_not_fused',
            '表情和声音结果都准备好了，下一步点击融合，看看综合判断是什么。',
            ['如果融合按钮不能点，先确认两个结果都已经显示出来。'],
            confidence=0.86,
        )

    if _has_value(last_fusion_result) and not _has_value(selected_toy):
        return _rule(
            'emotion_result_ready_but_user_not_understand',
            '你已经得到融合结果了，下一步选择一个玩具反馈，看看系统为什么这样推荐。',
            ['先看结果中的主要情绪，再对照玩具反馈。'],
            confidence=0.72 if not asks_help else 0.84,
            mode='explain',
        )

    return _no_rule()


def detect_face_emotion_rules(
    snapshot: dict | None,
    recent_events: list[dict] | None = None,
    question: str | None = None,
) -> dict:
    """Detect phase 1 stuck states for the face emotion course."""
    snap = snapshot or {}
    names = _event_names(recent_events)
    asks_help = _has_help_intent(question)

    current_model = snap.get('current_model') or snap.get('model_id')
    camera_status = _text(snap.get('camera_status')).lower()
    last_result = snap.get('last_result')
    no_face_count = int(snap.get('consecutive_no_face_count') or 0)
    last_face_count = int(snap.get('last_face_count') or 0)

    if not _has_value(current_model):
        return _rule(
            'face_missing_model_selection',
            '先选择一个表情识别模型，再开启摄像头。',
            ['第一次使用可以先选默认模型。'],
            confidence=0.78,
        )

    if camera_status not in ('running', 'started', 'on', 'active') and 'camera_started' not in names:
        return _rule(
            'face_missing_camera_start',
            '点击开启摄像头，让系统先看到你的脸。',
            ['浏览器弹出权限提示时请选择允许。'],
            confidence=0.8,
        )

    if no_face_count >= 3 or ('no_face_detected' in names and last_face_count == 0):
        return _rule(
            'face_no_face_detected',
            '系统连续没有检测到人脸，下一步请正对摄像头并靠近一点再试。',
            ['保持脸在画面中央，避免背光或遮挡。'],
            confidence=0.93 if asks_help else 0.86,
        )

    if _has_value(last_result) and _has_value(_result_emotion(last_result)):
        return _rule(
            'face_result_ready_but_user_not_understand',
            '你已经得到表情结果了，下一步可以对照置信度看看系统最相信哪一种表情。',
            ['置信度越高，表示模型越确定这个判断。'],
            confidence=0.7 if not asks_help else 0.84,
            mode='explain',
        )

    return _no_rule()


def detect_ecobottle_rules(
    snapshot: dict | None,
    recent_events: list[dict] | None = None,
    question: str | None = None,
) -> dict:
    """Detect phase 1 stuck states for the ecobottle course."""
    snap = snapshot or {}
    names = _event_names(recent_events)
    asks_help = _has_help_intent(question)

    current_tab = _text(snap.get('current_tab')).lower()
    data_count = int(snap.get('data_count') or 0)
    last_prediction = snap.get('last_prediction')
    prediction_model = snap.get('prediction_model')

    if (
        current_tab in ('train', 'train_model', 'training')
        and data_count < 3
    ) or 'training_blocked_not_enough_data' in names:
        return _rule(
            'ecobottle_data_not_enough_for_train',
            '现在数据还不够训练，下一步回到采集页，至少添加 3 条数据。',
            ['数据越多，模型越容易学到稳定规律。'],
            confidence=0.94 if asks_help else 0.88,
        )

    if current_tab in ('predict', 'prediction') and data_count <= 0:
        return _rule(
            'ecobottle_prediction_without_data',
            '还没有可用数据，下一步先采集或导入数据，再进行预测。',
            ['预测需要先看到历史数据，才能推测后面的变化。'],
            confidence=0.88,
        )

    if (
        asks_help
        and prediction_model
        and current_tab not in ('predict', 'prediction')
        and not _has_value(last_prediction)
    ):
        return _rule(
            'ecobottle_wrong_tab_for_action',
            '你已经选了预测模型，下一步切到预测页再运行预测。',
            ['先确认数据数量足够，再点预测。'],
            confidence=0.72,
        )

    if _has_value(last_prediction) or 'prediction_requested' in names:
        return _rule(
            'ecobottle_result_ready_but_user_not_understand',
            '你已经完成预测了，下一步可以进入控制页尝试自动调节，或者生成报告。',
            ['控制页会把预测结果变成具体动作建议。'],
            confidence=0.82 if asks_help else 0.7,
            mode='guide',
        )

    return _no_rule()


def detect_stuck(context: dict) -> dict:
    """Dispatch rule diagnosis by course/page."""
    snapshot = context.get('snapshot') or {}
    recent_events = context.get('recent_events') or []
    question = context.get('question')
    course = _text(context.get('course')).lower()
    page = _text(context.get('page')).lower()

    if course in ('emotion', 'emotion_computing') or page == 'emotion_computing':
        return detect_emotion_computing_rules(snapshot, recent_events, question)
    if course in ('face', 'face_emotion') or page == 'face_emotion':
        return detect_face_emotion_rules(snapshot, recent_events, question)
    if course == 'ecobottle' or page == 'ecobottle':
        return detect_ecobottle_rules(snapshot, recent_events, question)
    return _no_rule()


def build_rule_based_next_step(rule_hit: dict | str | None, context: dict | None = None) -> dict:
    """Normalize a rule result or diagnosis code into a next-step payload."""
    if isinstance(rule_hit, dict):
        return rule_hit

    diagnosis = _text(rule_hit)
    if not diagnosis:
        return _no_rule()

    catalog = {
        'emotion_missing_face_model': (
            '先选择一个表情模型，再开始摄像头识别。',
            ['如果不确定，先用默认推荐模型。'],
        ),
        'emotion_missing_audio_model': (
            '再选择一个声音模型，后面才能把表情和声音结果合在一起看。',
            ['表情模型和声音模型都选好后，再开始采集。'],
        ),
        'emotion_missing_camera_start': (
            '点击开始摄像头，先得到一个表情识别结果。',
            ['请站在画面中央，保证脸部光线清楚。'],
        ),
        'emotion_missing_audio_input': (
            '你已经有表情结果了，下一步点击开始录音，让系统也读取声音情绪。',
            ['录音 3 到 5 秒就够了，周围尽量安静。'],
        ),
        'face_no_face_detected': (
            '系统连续没有检测到人脸，下一步请正对摄像头并靠近一点再试。',
            ['保持脸在画面中央，避免背光或遮挡。'],
        ),
        'ecobottle_data_not_enough_for_train': (
            '现在数据还不够训练，下一步回到采集页，至少添加 3 条数据。',
            ['数据越多，模型越容易学到稳定规律。'],
        ),
        'ecobottle_result_ready_but_user_not_understand': (
            '你已经完成预测了，下一步可以进入控制页尝试自动调节，或者生成报告。',
            ['控制页会把预测结果变成具体动作建议。'],
        ),
    }
    next_step, tips = catalog.get(
        diagnosis,
        ('先看当前页面已经完成了哪一步，再按课程顺序继续下一步。', []),
    )
    return _rule(diagnosis, next_step, tips=tips, confidence=0.7)
