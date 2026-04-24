"""Markdown knowledge lookup for AI tutor phase 1."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = BASE_DIR / 'docs' / 'ai_knowledge'


KNOWLEDGE_INDEX: dict[str, dict[str, list[str]]] = {
    'emotion': {
        'select_model': ['emotion_computing/step_select_model.md'],
        'single_modal_capture': [
            'emotion_computing/stuck_missing_camera.md',
            'emotion_computing/step_record_audio.md',
        ],
        'single_modal_result': ['emotion_computing/step_record_audio.md'],
        'fusion_config': ['emotion_computing/step_fusion.md'],
        'fusion_result': ['emotion_computing/explain_fusion_result.md'],
        'toy_feedback': ['emotion_computing/explain_fusion_result.md'],
        'emotion_missing_face_model': ['emotion_computing/step_select_model.md'],
        'emotion_missing_audio_model': ['emotion_computing/step_select_model.md'],
        'emotion_missing_camera_start': ['emotion_computing/stuck_missing_camera.md'],
        'emotion_missing_audio_input': ['emotion_computing/stuck_missing_audio.md'],
        'emotion_has_single_modal_result_but_not_fused': ['emotion_computing/step_fusion.md'],
        'emotion_result_ready_but_user_not_understand': [
            'emotion_computing/explain_fusion_result.md'
        ],
    },
    'face': {
        'select_model': ['face_emotion/step_select_model.md'],
        'detecting': ['face_emotion/step_start_camera.md'],
        'result_ready': ['face_emotion/explain_result.md'],
        'face_missing_model_selection': ['face_emotion/step_select_model.md'],
        'face_missing_camera_start': ['face_emotion/step_start_camera.md'],
        'face_no_face_detected': ['face_emotion/stuck_no_face.md'],
        'face_result_ready_but_user_not_understand': ['face_emotion/explain_result.md'],
    },
    'ecobottle': {
        'collect_data': ['ecobottle/step_collect_data.md'],
        'explore_data': ['ecobottle/step_explore.md'],
        'train_model': ['ecobottle/step_train.md'],
        'predict': ['ecobottle/step_predict.md'],
        'control': ['ecobottle/step_control.md'],
        'ecobottle_data_not_enough_for_train': ['ecobottle/stuck_not_enough_data.md'],
        'ecobottle_prediction_without_data': ['ecobottle/step_collect_data.md'],
        'ecobottle_wrong_tab_for_action': ['ecobottle/stuck_wrong_tab.md'],
        'ecobottle_result_ready_but_user_not_understand': ['ecobottle/explain_prediction.md'],
    },
}


COURSE_ALIASES = {
    'emotion_computing': 'emotion',
    'emotion': 'emotion',
    'face_emotion': 'face',
    'face': 'face',
    'ecobottle': 'ecobottle',
}


def _normalize_course(course: str | None) -> str | None:
    if not course:
        return None
    return COURSE_ALIASES.get(str(course).strip().lower())


def _clean_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def load_knowledge_index() -> dict[str, dict[str, list[str]]]:
    """Return the static phase 1 knowledge index."""
    return KNOWLEDGE_INDEX


@lru_cache(maxsize=128)
def _read_knowledge_file(relative_path: str) -> str:
    path = KNOWLEDGE_DIR / relative_path
    try:
        return path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return ''


def _select_refs(course: str | None, step_code: str | None, diagnosis: str | None) -> list[str]:
    normalized_course = _normalize_course(course)
    if not normalized_course:
        return []

    course_index = KNOWLEDGE_INDEX.get(normalized_course, {})
    refs: list[str] = []
    for key in (_clean_key(diagnosis), _clean_key(step_code)):
        if not key:
            continue
        for ref in course_index.get(key, []):
            if ref not in refs:
                refs.append(ref)
    return refs


def build_knowledge_context(
    course: str | None,
    step_code: str | None = None,
    diagnosis: str | None = None,
    question: str | None = None,
    max_chars: int = 2400,
) -> dict:
    """Return relevant markdown snippets for answer generation."""
    refs = _select_refs(course, step_code, diagnosis)
    snippets = []
    remaining = max_chars

    for ref in refs:
        content = _read_knowledge_file(ref)
        if not content or remaining <= 0:
            continue
        clipped = content[:remaining]
        snippets.append({
            'ref': ref,
            'content': clipped,
        })
        remaining -= len(clipped)

    return {
        'course': _normalize_course(course),
        'step_code': step_code,
        'diagnosis': diagnosis,
        'question': question,
        'knowledge_refs': [item['ref'] for item in snippets],
        'snippets': snippets,
        'text': '\n\n'.join(
            f"[{item['ref']}]\n{item['content']}" for item in snippets
        ),
    }
