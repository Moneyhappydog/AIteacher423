"""AI tutor context orchestration service."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from models import AiTutorEvent, AiTutorSession, db
from services import ai_context_store
from services.ai_session_service import get_or_create_session, resolve_group_user_id


def _now() -> datetime:
    return datetime.utcnow()


def _parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            pass
    return _now()


def _normalize_context(raw_context: dict | None) -> dict:
    context = raw_context or {}
    return {
        'session_id': context.get('session_id'),
        'group_id': context.get('group_id'),
        'page': context.get('page') or context.get('course_page'),
        'course': context.get('course'),
        'step_code': context.get('step_code'),
        'member_id': context.get('member_id'),
        'snapshot': context.get('snapshot') or {},
    }


def _event_summary(event: dict) -> str:
    name = event.get('event_name') or 'unknown_event'
    step = event.get('step_code')
    payload = event.get('payload') or {}

    compact_payload = []
    for key, value in payload.items():
        if value is None or isinstance(value, (dict, list)):
            continue
        compact_payload.append(f'{key}={value}')
        if len(compact_payload) >= 3:
            break

    suffix = f" ({', '.join(compact_payload)})" if compact_payload else ''
    return f'{step + ": " if step else ""}{name}{suffix}'


def record_event(
    session_id: str,
    group_id: Any,
    page: str,
    course: str,
    event_type: str,
    event_name: str,
    step_code: str | None = None,
    member_id: str | None = None,
    payload: dict | None = None,
    summary_text: str | None = None,
    dedupe_key: str | None = None,
    event_time: Any = None,
    commit: bool = True,
) -> AiTutorEvent:
    """Persist one AI tutor context event and append it to hot cache."""
    if not event_type:
        raise ValueError('event_type is required')
    if not event_name:
        raise ValueError('event_name is required')

    session_record = get_or_create_session(
        session_id=session_id,
        group_id=group_id,
        page=page,
        course=course,
        member_id=member_id,
        step_code=step_code,
        commit=False,
    )

    event_payload = payload or {}
    event = AiTutorEvent(
        session_id=session_record.session_id,
        group_id=session_record.group_id,
        member_id=member_id,
        page=page,
        course=course,
        step_code=step_code,
        event_type=event_type,
        event_name=event_name,
        payload=event_payload,
        summary_text=summary_text,
        dedupe_key=dedupe_key,
        event_time=_parse_event_time(event_time),
    )
    db.session.add(event)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    cached_event = event.to_dict()
    cached_event['summary_text'] = summary_text or _event_summary(cached_event)
    ai_context_store.append_event(session_record.session_id, cached_event)
    return event


def save_snapshot(
    session_id: str,
    group_id: Any,
    page: str,
    course: str,
    snapshot: dict | None,
    step_code: str | None = None,
    member_id: str | None = None,
    diagnosis: dict | None = None,
    commit: bool = True,
) -> AiTutorSession:
    """Persist and cache the latest page snapshot for a session."""
    session_record = get_or_create_session(
        session_id=session_id,
        group_id=group_id,
        page=page,
        course=course,
        member_id=member_id,
        step_code=step_code,
        snapshot=snapshot or {},
        commit=False,
    )

    session_record.latest_snapshot = snapshot or {}
    session_record.step_code = step_code if step_code is not None else session_record.step_code
    if diagnosis is not None:
        session_record.latest_diagnosis = diagnosis

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    ai_context_store.set_snapshot(session_id, snapshot or {})
    if diagnosis is not None:
        ai_context_store.set_diag(session_id, diagnosis)
    return session_record


def get_recent_db_events(session_id: str, limit: int = 15) -> list[dict]:
    """Load recent events from MySQL when cache is cold."""
    if limit <= 0:
        return []

    events = (
        AiTutorEvent.query
        .filter_by(session_id=session_id)
        .order_by(AiTutorEvent.event_time.desc(), AiTutorEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [event.to_dict() for event in reversed(events)]


def compress_recent_events(events: list[dict], limit: int = 15) -> list[str]:
    """Compress recent event dictionaries into short evidence strings."""
    if limit <= 0:
        return []
    return [_event_summary(event) for event in (events or [])[-limit:]]


def build_request_context(
    question: str,
    raw_context: dict | None,
    group_id: Any = None,
) -> dict:
    """Build the normalized context object consumed by later answer services."""
    normalized = _normalize_context(raw_context)
    session_id = normalized.get('session_id')
    if not session_id:
        raise ValueError('context.session_id is required')

    resolved_group_id = resolve_group_user_id(
        group_id if group_id is not None else normalized.get('group_id')
    )
    page = normalized.get('page') or 'unknown'
    course = normalized.get('course') or 'unknown'
    step_code = normalized.get('step_code')
    snapshot = normalized.get('snapshot') or ai_context_store.get_snapshot(session_id)

    session_record = get_or_create_session(
        session_id=session_id,
        group_id=resolved_group_id,
        page=page,
        course=course,
        member_id=normalized.get('member_id'),
        step_code=step_code,
        snapshot=snapshot,
    )

    recent_events = ai_context_store.get_recent_cached_events(session_id)
    if not recent_events:
        recent_events = get_recent_db_events(session_id)
        for event in recent_events:
            ai_context_store.append_event(session_id, event)

    diagnosis = ai_context_store.get_diag(session_id) or session_record.latest_diagnosis

    return {
        'question': question,
        'session': session_record,
        'session_id': session_id,
        'group_id': resolved_group_id,
        'member_id': normalized.get('member_id'),
        'page': page,
        'course': course,
        'step_code': step_code or session_record.step_code,
        'snapshot': snapshot or session_record.latest_snapshot or {},
        'recent_events': recent_events,
        'recent_event_summaries': compress_recent_events(recent_events),
        'diagnosis': diagnosis,
    }


def build_context_used(
    context: dict,
    rule_hits: list[str] | None = None,
    knowledge_refs: list[str] | None = None,
) -> dict:
    """Build the evidence object returned by structured `/ai/ask` responses."""
    return {
        'page': context.get('page'),
        'course': context.get('course'),
        'step_code': context.get('step_code'),
        'recent_events': context.get('recent_event_summaries') or [],
        'rule_hits': rule_hits or [],
        'knowledge_refs': knowledge_refs or [],
    }
