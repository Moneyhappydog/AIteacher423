"""AI tutor context ingestion routes."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session

from models import (
    AiTutorEvent,
    AiTutorMemorySummary,
    AiTutorMessage,
    AiTutorSession,
    db,
)
from routes.auth import login_required
from services import ai_context_store
from services.ai_context_service import get_recent_db_events, record_event, save_snapshot
from services.ai_session_service import resolve_group_user_id


ai_context_bp = Blueprint('ai_context', __name__, url_prefix='/ai/context')


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _current_group_id(default=None):
    return session.get('group_id') or default


def _require_fields(data: dict, fields: list[str]):
    missing = [field for field in fields if not data.get(field)]
    if missing:
        return jsonify({
            'success': False,
            'error': f"missing required fields: {', '.join(missing)}",
        }), 400
    return None


def _debug_enabled() -> bool:
    return bool(
        current_app.debug
        or current_app.config.get('DEBUG')
        or current_app.config.get('AI_CONTEXT_DEBUG_ENABLED')
    )


@ai_context_bp.route('/event', methods=['POST'])
@login_required
def post_event():
    """Ingest a structured page event."""
    data = _json_body()
    error = _require_fields(
        data,
        ['session_id', 'page', 'course', 'event_type', 'event_name'],
    )
    if error:
        return error

    group_id = data.get('group_id') or _current_group_id()
    if not group_id:
        return jsonify({'success': False, 'error': 'group_id is required'}), 400

    try:
        event = record_event(
            session_id=data['session_id'],
            group_id=group_id,
            page=data['page'],
            course=data['course'],
            event_type=data['event_type'],
            event_name=data['event_name'],
            step_code=data.get('step_code'),
            member_id=data.get('member_id'),
            payload=data.get('payload') or {},
            summary_text=data.get('summary_text'),
            dedupe_key=data.get('dedupe_key'),
            event_time=data.get('event_time'),
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({'success': True, 'event_id': event.id})


@ai_context_bp.route('/snapshot', methods=['POST'])
@login_required
def post_snapshot():
    """Ingest the latest page snapshot."""
    data = _json_body()
    error = _require_fields(data, ['session_id', 'page', 'course'])
    if error:
        return error

    group_id = data.get('group_id') or _current_group_id()
    if not group_id:
        return jsonify({'success': False, 'error': 'group_id is required'}), 400

    try:
        record = save_snapshot(
            session_id=data['session_id'],
            group_id=group_id,
            page=data['page'],
            course=data['course'],
            snapshot=data.get('snapshot') or {},
            step_code=data.get('step_code'),
            member_id=data.get('member_id'),
            diagnosis=data.get('diagnosis'),
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'session_id': record.session_id,
        'updated_at': (
            record.updated_at.isoformat()
            if record.updated_at else datetime.utcnow().isoformat()
        ),
    })


@ai_context_bp.route('/delete_memory', methods=['POST'])
@login_required
def delete_memory():
    """Delete AI tutor memory for the current or requested group."""
    data = _json_body()
    requested_group_id = data.get('group_id') or _current_group_id()
    if not requested_group_id:
        return jsonify({'success': False, 'error': 'group_id is required'}), 400

    try:
        resolved_group_id = resolve_group_user_id(requested_group_id)
        session_ids = [
            row.session_id
            for row in AiTutorSession.query.filter_by(group_id=resolved_group_id).all()
        ]

        deleted_messages = AiTutorMessage.query.filter_by(group_id=resolved_group_id).delete()
        deleted_events = AiTutorEvent.query.filter_by(group_id=resolved_group_id).delete()
        deleted_summaries = AiTutorMemorySummary.query.filter_by(group_id=resolved_group_id).delete()
        deleted_sessions = AiTutorSession.query.filter_by(group_id=resolved_group_id).delete()
        db.session.commit()

        for session_id in session_ids:
            ai_context_store.clear_session_cache(session_id)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'group_id': resolved_group_id,
        'deleted': {
            'sessions': deleted_sessions,
            'events': deleted_events,
            'memory_summaries': deleted_summaries,
            'messages': deleted_messages,
        },
    })


@ai_context_bp.route('/debug/<session_id>', methods=['GET'])
@login_required
def debug_session(session_id):
    """Return cached and persisted context for development."""
    if not _debug_enabled():
        return jsonify({'success': False, 'error': 'debug endpoint disabled'}), 403

    record = AiTutorSession.query.filter_by(session_id=session_id).first()
    return jsonify({
        'success': True,
        'session_id': session_id,
        'store': ai_context_store.get_store_status(),
        'cache': {
            'snapshot': ai_context_store.get_snapshot(session_id),
            'events': ai_context_store.get_recent_cached_events(session_id, limit=30),
            'diagnosis': ai_context_store.get_diag(session_id),
        },
        'database': {
            'session': record.to_dict() if record else None,
            'events': get_recent_db_events(session_id, limit=30),
        },
    })
