"""In-process TTL cache for highly-queried, infrequently-changed reference data
(diagnostics_and_improvements Phase 3: Settings / Categories / Roles).

Single-process invariant: the FastAPI app runs as ONE uvicorn worker
(FLOW_LOGIC §6 "Single Uvicorn worker"), so a module-level dict is a correct
process-wide cache — no cross-process invalidation is needed. Multi-terminal
client terminals always read through this server, never around it.

All helpers are synchronous and O(1); expired entries are lazily evicted on
read and pruned opportunistically on write, so there is no background timer.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

_DEFAULT_TTL_SECONDS = 60.0

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def cache_get(key: str) -> Optional[Any]:
    """Return the cached value for ``key`` or ``None`` if missing/expired."""
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if now >= expires_at:
            del _store[key]
            return None
        return value


def cache_set(key: str, value: Any, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
    """Store ``value`` under ``key`` for ``ttl_seconds`` (prunes expired entries)."""
    now = time.monotonic()
    with _lock:
        if len(_store) > 256:
            expired = [k for k, (exp, _) in _store.items() if now >= exp]
            for k in expired:
                del _store[k]
        _store[key] = (now + ttl_seconds, value)


def cache_invalidate(key: str) -> None:
    """Drop ``key`` from the cache (no-op if absent). Must follow every write."""
    with _lock:
        _store.pop(key, None)


def cache_invalidate_prefix(prefix: str) -> None:
    """Drop every key starting with ``prefix`` (e.g. role permission entries)."""
    with _lock:
        stale = [k for k in _store if k.startswith(prefix)]
        for k in stale:
            del _store[k]


def cache_clear() -> None:
    """Empty the whole cache (used by tests and admin reset paths)."""
    with _lock:
        _store.clear()
