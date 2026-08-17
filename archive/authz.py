"""authz.py — Authorization middleware for the CustomTkinter RBAC layer.

Provides:
  * check_permission(user_id, feature)        — boolean gate
  * access_denied(feature)                    — user-facing alert
  * require_permission(feature)               — decorator for button commands
  * create_first_owner(...)                   — secure initial Owner creation (Option A)
"""
from __future__ import annotations

import tkinter.messagebox as msgbox

import database as db

# Features that additionally require a re-entered PIN / Owner override at runtime.
SENSITIVE_FEATURES = {
    "audit.view",
    "audit.export",
    "roles.manage",
    "users.manage",
    "settings.manage",
    "sales.modify_report",
    "pos.price_override",
    "pos.void",
    "backup.manage",
}


def check_permission(user_id, required_feature: str) -> bool:
    """Return True if ``user_id`` is granted ``required_feature``.

    The ``owner`` role implicitly holds every defined permission.
    """
    if user_id is None:
        return False
    return required_feature in db.get_user_permissions(user_id)


def access_denied(feature: str) -> None:
    """Show a blocking "Access Denied" alert for an unauthorized action."""
    msgbox.showerror("Access Denied", f"You do not have permission: {feature}.")


def pin_denied(feature: str) -> None:
    """Show a blocking alert when a sensitive action fails PIN re-verification."""
    msgbox.showerror(
        "PIN Verification Required",
        f"This action requires PIN confirmation: {feature}.",
    )


def require_pin_for(feature: str, parent=None) -> bool:
    """Imperative counterpart to :func:`require_permission` for inline guards.

    Returns True only when the session holds ``feature`` AND (for sensitive
    features) a PIN has been verified within the TTL. Shows the appropriate
    alert and returns False otherwise. Use inside handlers that cannot be
    wrapped as a ``command`` callback::

        if not authz.require_pin_for("audit.view", self):
            return
    """
    import auth_session

    uid = auth_session.current_user_id()
    if uid is None or not check_permission(uid, feature):
        access_denied(feature)
        return False
    if feature in SENSITIVE_FEATURES and not auth_session.pin_verified():
        try:
            has_pin = db.user_has_pin(uid)
        except Exception:
            has_pin = False
        if has_pin and not auth_session.require_pin(parent):
            pin_denied(feature)
            return False
    return True


def require_permission(required_feature: str, parent=None):
    """Decorator factory for CustomTkinter button ``command`` callbacks.

    Enforces two layers before the wrapped handler runs:

    1. **Permission gate** — the active session must hold ``required_feature``.
    2. **PIN re-prompt (G6)** — when ``required_feature`` is in
       :data:`SENSITIVE_FEATURES`, a PIN must have been verified within the
       session TTL. If the cached PIN has expired, the user is re-prompted
       once via ``auth_session.require_pin``.

    Graceful degradation: users with no PIN configured (``pin_hash`` NULL) are
    not locked out of sensitive actions — the permission check alone governs,
    matching the plan's "degrades to deny if PIN not set" intent without
    stranding PIN-less accounts.

    Wrap any handler, e.g.::

        btn = ctk.CTkButton(self, command=require_permission("sales.modify_report")(self._on_edit))
    """
    import auth_session

    def decorator(func):
        def wrapper(*args, **kwargs):
            uid = auth_session.current_user_id()
            if uid is None or not check_permission(uid, required_feature):
                access_denied(required_feature)
                return

            if required_feature in SENSITIVE_FEATURES and not auth_session.pin_verified():
                # Only demand a PIN from users who actually have one configured.
                try:
                    has_pin = db.user_has_pin(uid)
                except Exception:
                    has_pin = False
                if has_pin:
                    # Resolve a Tk parent for the modal: explicit > bound widget.
                    owner = parent if parent is not None else (args[0] if args else None)
                    if not auth_session.require_pin(owner):
                        pin_denied(required_feature)
                        return

            return func(*args, **kwargs)

        # Preserve identity for introspection/tests.
        wrapper.__name__ = getattr(func, "__name__", "wrapper")
        wrapper.__doc__ = getattr(func, "__doc__", None)
        wrapper.__wrapped__ = func
        wrapper.__rbac_feature__ = required_feature
        wrapper.__rbac_sensitive__ = required_feature in SENSITIVE_FEATURES
        return wrapper

    return decorator


def create_first_owner(username: str, secret: str, display_name: str = "", pin: str = "") -> int:
    """Securely create the initial Owner account (anti-escalation guard).

    This is the only path that may mint an ``owner`` user without an existing
    authenticated Owner session. It is permitted strictly when the system has
    no users yet. Raises ``ValueError``/``RuntimeError`` on invalid input or if
    users already exist.

    Returns the new user id.
    """
    if not username or not username.strip():
        raise ValueError("A username is required.")
    if not secret or len(secret) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if db.count_users() != 0:
        raise RuntimeError("The Owner account can only be created on a fresh system with no users.")
    owner_role_id = next((r[0] for r in db.get_roles() if r[1] == "owner"), None)
    if owner_role_id is None:
        raise RuntimeError("The 'owner' role is missing from the database.")
    # G8 (fresh install): set the Owner override to the chosen account secret and
    # mark it rotated, so the shipped bootstrap secret is never written.
    uid = db.create_user(username.strip(), secret, owner_role_id, display_name=display_name.strip(), pin=pin)
    db.set_owner_override_password(secret)
    db.mark_owner_override_rotated()
    return uid
