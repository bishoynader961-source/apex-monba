"""auth_session.py — In-memory RBAC session (process lifetime).

Holds the currently authenticated user id so the authorization middleware can
evaluate permissions for CustomTkinter command handlers. Provides PIN
quick-auth caching (re-prompt avoidance for sensitive actions), a pluggable
Owner-override hook so the UI layer can supply the master-password prompt
without creating a circular import between this module and ``ui_auth``, and
an optional idle/absolute session timer (G9) that auto-logs-out on expiry.
"""
from __future__ import annotations

import time

_current_user_id: int | None = None
_pin_verified_until: float = 0.0
_PIN_TTL_SECONDS: float = 300.0  # 5 minutes

# Session TTL (G9): absolute timer after login; 0 = disabled.
_session_expires_at: float = 0.0
_expiry_job: str | None = None

# Pluggable UI prompts (registered by the UI layer at startup).
_owner_override_prompt = None  # callable(parent) -> bool
_pin_prompt = None             # callable(parent) -> bool


def login(user_id: int) -> None:
    global _current_user_id, _pin_verified_until
    _current_user_id = user_id
    _pin_verified_until = 0.0  # a fresh login invalidates any cached PIN


def logout() -> None:
    global _current_user_id, _pin_verified_until, _expiry_job
    _current_user_id = None
    _pin_verified_until = 0.0
    _expiry_job = None


def current_user_id() -> int | None:
    return _current_user_id


def set_owner_override_prompt(fn) -> None:
    global _owner_override_prompt
    _owner_override_prompt = fn


def set_pin_prompt(fn) -> None:
    global _pin_prompt
    _pin_prompt = fn


def cache_pin() -> None:
    """Mark the PIN as verified for the next ``_PIN_TTL_SECONDS``."""
    global _pin_verified_until
    _pin_verified_until = time.time() + _PIN_TTL_SECONDS


def pin_verified() -> bool:
    """True if a PIN was successfully re-entered within the TTL window."""
    return time.time() < _pin_verified_until


def require_owner_override(parent=None) -> bool:
    """Prompt for the Owner override master secret (via the registered UI).

    Returns True only when the secret verifies. Returns False if no prompt is
    registered or the user cancels/fails.
    """
    if _owner_override_prompt is None:
        return False
    return bool(_owner_override_prompt(parent))


def require_pin(parent=None) -> bool:
    """Prompt for the active user's PIN (via the registered UI).

    On success the PIN is cached for the TTL window. Returns True when verified.
    """
    if _pin_prompt is None:
        return False
    ok = bool(_pin_prompt(parent))
    if ok:
        cache_pin()
    return ok


# ── Session TTL (G9) ──────────────────────────────────────────────────

def start_session_timer(root, on_expire=None) -> None:
    """Start the idle/absolute session TTL timer.

    Uses ``root.after()`` which is safe only post-``mainloop()``.  The TTL is
    read from config on each start; ``session_timeout_minutes = 0`` disables
    the timer entirely.
    """
    import barcode_logic
    minutes = barcode_logic.get_int("session_timeout_minutes", 0, lo=0)
    if minutes <= 0:
        return
    global _session_expires_at
    _session_expires_at = time.time() + (minutes * 60)
    _schedule_expiry_check(root, on_expire)


def _schedule_expiry_check(root, on_expire) -> None:
    global _expiry_job
    if _expiry_job is not None:
        try:
            root.after_cancel(_expiry_job)
        except Exception:
            pass
    _expiry_job = root.after(60_000, lambda: _check_expiry(root, on_expire))


def _check_expiry(root, on_expire) -> None:
    """Called every 60 s while a session is active."""
    global _expiry_job, _current_user_id
    if _current_user_id is None:
        return
    if root is not None:
        try:
            if not root.winfo_exists():
                return
        except Exception:
            return
    if time.time() >= _session_expires_at:
        _expiry_job = None
        if on_expire:
            on_expire()
        return
    _schedule_expiry_check(root, on_expire)


def refresh_session_timer() -> None:
    """Reset the expiry clock on user activity (call on button clicks, etc.)."""
    global _session_expires_at
    import barcode_logic
    minutes = barcode_logic.get_int("session_timeout_minutes", 0, lo=0)
    if minutes > 0 and _current_user_id is not None:
        _session_expires_at = time.time() + (minutes * 60)
