"""AI tutor session persistence helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from models import AiTutorSession, Group, db


def _now() -> datetime:
    return datetime.utcnow()


def resolve_group_user_id(group_id: Any = None) -> int:
    """Resolve a UI group id/code such as G01 to the persisted groups.user_id."""
    if group_id is None:
        try:
            from flask import session
            group_id = session.get('group_id') or session.get('user_id')
        except Exception:
            group_id = None

    if group_id is None:
        raise ValueError('group_id is required')

    if isinstance(group_id, int):
        return group_id

    group_id_str = str(group_id).strip()
    if group_id_str.isdigit():
        return int(group_id_str)

    group = Group.query.filter_by(group_code=group_id_str).first()
    if group:
        return group.user_id

    raise ValueError(f'unknown group_id: {group_id_str}')


def get_or_create_session(
    session_id: str,
    group_id: Any,
    page: str,
    course: str,
    member_id: str | None = None,
    step_code: str | None = None,
    snapshot: dict | None = None,
    commit: bool = True,
) -> AiTutorSession:
    """Return the existing active AI tutor session or create it."""
    if not session_id:
        raise ValueError('session_id is required')
    if not page:
        raise ValueError('page is required')
    if not course:
        raise ValueError('course is required')

    resolved_group_id = resolve_group_user_id(group_id)
    now = _now()
    record = AiTutorSession.query.filter_by(session_id=session_id).first()

    if record is None:
        record = AiTutorSession(
            session_id=session_id,
            group_id=resolved_group_id,
            member_id=member_id,
            page=page,
            course=course,
            step_code=step_code,
            latest_snapshot=snapshot,
            started_at=now,
            last_active_at=now,
            is_active=True,
        )
        db.session.add(record)
    else:
        record.group_id = resolved_group_id
        record.member_id = member_id or record.member_id
        record.page = page or record.page
        record.course = course or record.course
        record.step_code = step_code if step_code is not None else record.step_code
        if snapshot is not None:
            record.latest_snapshot = snapshot
        record.last_active_at = now
        record.is_active = True

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return record


def touch_session(
    session_id: str,
    page: str | None = None,
    course: str | None = None,
    step_code: str | None = None,
    commit: bool = True,
) -> AiTutorSession | None:
    """Update last activity and optional location fields for a session."""
    record = AiTutorSession.query.filter_by(session_id=session_id).first()
    if record is None:
        return None

    if page is not None:
        record.page = page
    if course is not None:
        record.course = course
    if step_code is not None:
        record.step_code = step_code
    record.last_active_at = _now()

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return record


def update_session_snapshot(
    session_id: str,
    snapshot: dict,
    step_code: str | None = None,
    diagnosis: dict | None = None,
    commit: bool = True,
) -> AiTutorSession | None:
    """Persist the latest snapshot and optional diagnosis for a session."""
    record = AiTutorSession.query.filter_by(session_id=session_id).first()
    if record is None:
        return None

    record.latest_snapshot = snapshot or {}
    if step_code is not None:
        record.step_code = step_code
    if diagnosis is not None:
        record.latest_diagnosis = diagnosis
    record.last_active_at = _now()

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return record


def update_session_diagnosis(
    session_id: str,
    diagnosis: dict,
    commit: bool = True,
) -> AiTutorSession | None:
    """Persist the latest diagnosis for a session."""
    record = AiTutorSession.query.filter_by(session_id=session_id).first()
    if record is None:
        return None

    record.latest_diagnosis = diagnosis or {}
    record.last_active_at = _now()

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return record


def close_session(session_id: str, commit: bool = True) -> AiTutorSession | None:
    """Mark a session as inactive."""
    record = AiTutorSession.query.filter_by(session_id=session_id).first()
    if record is None:
        return None

    record.ended_at = _now()
    record.last_active_at = record.ended_at
    record.is_active = False

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return record
