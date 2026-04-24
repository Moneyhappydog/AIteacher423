"""Short-lived AI tutor context cache.

The store uses the app's Flask-Caching/Redis setup when available and falls back
to an in-process TTL dictionary when Redis or Flask app context is unavailable.
MySQL remains the durable source; this module only keeps hot session state.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from threading import RLock
from typing import Any


DEFAULT_SNAPSHOT_TTL = 60 * 60 * 6
DEFAULT_EVENTS_TTL = 60 * 60 * 6
DEFAULT_DIAG_TTL = 60 * 30
DEFAULT_COOLDOWN_TTL = 60 * 3

_MEMORY_LOCK = RLock()
_MEMORY_CACHE: dict[str, tuple[datetime | None, Any]] = {}


def _now() -> datetime:
    return datetime.utcnow()


def _expires_at(ttl: int | None) -> datetime | None:
    if ttl is None:
        return None
    return _now() + timedelta(seconds=ttl)


def _memory_get(key: str) -> Any:
    with _MEMORY_LOCK:
        item = _MEMORY_CACHE.get(key)
        if item is None:
            return None

        expires_at, value = item
        if expires_at is not None and expires_at <= _now():
            _MEMORY_CACHE.pop(key, None)
            return None
        return deepcopy(value)


def _memory_set(key: str, value: Any, ttl: int | None = None) -> bool:
    with _MEMORY_LOCK:
        _MEMORY_CACHE[key] = (_expires_at(ttl), deepcopy(value))
    return True


def _memory_delete(key: str) -> bool:
    with _MEMORY_LOCK:
        _MEMORY_CACHE.pop(key, None)
    return True


def _cache_backend():
    try:
        from utils import cache
    except Exception:
        return None
    return cache


def _cache_get(key: str) -> Any:
    backend = _cache_backend()
    if backend is None:
        return _memory_get(key)

    try:
        value = backend.get(key)
    except Exception:
        return _memory_get(key)

    if value is None:
        return _memory_get(key)
    return value


def _cache_set(key: str, value: Any, ttl: int | None = None) -> bool:
    backend = _cache_backend()
    if backend is not None:
        try:
            backend.set(key, value, timeout=ttl)
            _memory_set(key, value, ttl)
            return True
        except Exception:
            pass

    return _memory_set(key, value, ttl)


def _cache_delete(key: str) -> bool:
    backend = _cache_backend()
    if backend is not None:
        try:
            backend.delete(key)
        except Exception:
            pass

    return _memory_delete(key)


def _snapshot_key(session_id: str) -> str:
    return f'ai:snapshot:{session_id}'


def _events_key(session_id: str) -> str:
    return f'ai:events:{session_id}'


def _diag_key(session_id: str) -> str:
    return f'ai:diag:{session_id}'


def _cooldown_key(session_id: str, rule: str) -> str:
    return f'ai:cooldown:{session_id}:{rule}'


def get_snapshot(session_id: str) -> dict | None:
    """Return the latest cached page snapshot for a session."""
    return _cache_get(_snapshot_key(session_id))


def set_snapshot(session_id: str, snapshot: dict, ttl: int | None = DEFAULT_SNAPSHOT_TTL) -> bool:
    """Cache the latest page snapshot for a session."""
    return _cache_set(_snapshot_key(session_id), snapshot or {}, ttl)


def append_event(
    session_id: str,
    event: dict,
    max_len: int = 30,
    ttl: int | None = DEFAULT_EVENTS_TTL,
) -> bool:
    """Append one normalized event to the cached recent event list."""
    key = _events_key(session_id)
    events = _cache_get(key) or []
    if not isinstance(events, list):
        events = []

    events.append(event or {})
    if max_len > 0:
        events = events[-max_len:]
    return _cache_set(key, events, ttl)


def get_recent_cached_events(session_id: str, limit: int = 15) -> list[dict]:
    """Return recent cached events, newest last."""
    events = _cache_get(_events_key(session_id)) or []
    if not isinstance(events, list):
        return []
    if limit <= 0:
        return []
    return events[-limit:]


def get_diag(session_id: str) -> dict | None:
    """Return the latest cached rule diagnosis for a session."""
    return _cache_get(_diag_key(session_id))


def set_diag(session_id: str, diag: dict, ttl: int | None = DEFAULT_DIAG_TTL) -> bool:
    """Cache the latest rule diagnosis for a session."""
    return _cache_set(_diag_key(session_id), diag or {}, ttl)


def get_cooldown(session_id: str, rule: str) -> dict | None:
    """Return cooldown metadata for a rule, if it is still active."""
    return _cache_get(_cooldown_key(session_id, rule))


def set_cooldown(
    session_id: str,
    rule: str,
    value: dict | None = None,
    ttl: int | None = DEFAULT_COOLDOWN_TTL,
) -> bool:
    """Set a short cooldown marker for proactive hint rules."""
    payload = value or {'active': True, 'rule': rule, 'created_at': _now().isoformat()}
    return _cache_set(_cooldown_key(session_id, rule), payload, ttl)


def clear_session_cache(session_id: str) -> None:
    """Clear hot cache entries owned directly by a session."""
    _cache_delete(_snapshot_key(session_id))
    _cache_delete(_events_key(session_id))
    _cache_delete(_diag_key(session_id))


def get_store_status() -> dict:
    """Expose lightweight debug status for later development routes."""
    backend = _cache_backend()
    redis_available = False
    if backend is not None:
        try:
            probe_key = 'ai:store:probe'
            backend.set(probe_key, {'ok': True}, timeout=5)
            redis_available = backend.get(probe_key) == {'ok': True}
        except Exception:
            redis_available = False

    with _MEMORY_LOCK:
        memory_keys = len(_MEMORY_CACHE)

    return {
        'redis_available': redis_available,
        'memory_keys': memory_keys,
        'fallback': not redis_available,
    }
