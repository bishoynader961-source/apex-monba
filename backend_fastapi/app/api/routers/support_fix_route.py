"""Support fix-code routes: verify a signed fix code, then apply it.

Fix codes are signed JSON envelopes::

    {"action": "update_setting",
     "payload": {"key": "session_idle_minutes", "value": "60"},
     "sig": "<HMAC-SHA256 hex>"}

The signature is HMAC-SHA256 over the canonical JSON of ``payload`` (sorted
keys, UTF-8), keyed by the server-side ``FIX_CODE_SECRET``. Support-team
tooling computes it offline; this route recomputes and compares with
``hmac.compare_digest`` before anything changes. An invalid signature returns
``403`` — nobody can forge a fix code.

Note: the signing key is a *server secret*, not the JWT secret (``SECRET_KEY``
in ``config.py``). They are different values with different owners. Rotating
one never touches the other.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.config import get_settings
from app.shared.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/support", tags=["support"])


def _fix_code_secret() -> str:
    """Read the signing secret from settings on each call.

    Reading per-call (instead of once at import) keeps the value correct if
    the env/config changes and makes tests deterministic via monkeypatching.
    """
    try:
        return getattr(get_settings(), "fix_code_secret", "") or ""
    except Exception:  # pragma: no cover - settings are cached, rarely fail
        return ""


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """HMAC-SHA256 hex digest over canonical JSON (sorted keys).

    Shared by support-team tooling (same algorithm) and by the test suite.
    """
    message = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class FixCodeIn(BaseModel):
    action: str
    payload: dict[str, Any]
    sig: str


class FixCodeOut(BaseModel):
    action: str
    payload: dict[str, Any]


@router.post("/fix-code/verify", response_model=FixCodeOut, status_code=status.HTTP_200_OK)
async def verify_fix_code(
    body: FixCodeIn,
    _user: Any = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> FixCodeOut:
    """Verify the signature; apply the fix only if valid.

    Returns 403 for any tampering so the frontend can never trust an
    unsigned or unknown-code submission. Fail-closed: with no secret
    configured every code is rejected.
    """
    secret = _fix_code_secret()
    if not secret or not hmac.compare_digest(sign_payload(body.payload, secret), body.sig):
        logger.warning("fix_code_verify_rejected", extra={"action": body.action})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid fix code signature",
        )

    payload = body.payload
    if body.action == "update_setting":
        key = payload.get("key")
        if not key or "value" not in payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="update_setting requires 'key' and 'value'",
            )
        setting = await session.get(SystemSetting, key)
        if setting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting '{key}' not found",
            )
        setting.value = str(payload["value"]).encode("utf-8")
        await session.commit()
        logger.info("fix_code_applied", extra={"key": key})
        return FixCodeOut(action="update_setting", payload=payload)
    if body.action == "reload_permissions":
        # No DB change; refresh is a client-side action.
        return FixCodeOut(action="reload_permissions", payload={})

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown action: {body.action}",
    )


# ── Audit M4: remote fix-code verification for the desktop engine ────────────
# The desktop binary no longer embeds FIX_CODE_SECRET/FIX_ADMIN_KEY. The Rust
# fix engine (in-app recovery window + standalone recovery CLI) POSTs the raw
# fix code plus the admin key here instead; both secrets stay server-side.
# Fail-closed: a missing secret, bad admin key, bad HMAC, expired code, unknown
# action, or non-whitelisted setting key all answer ``{"valid": false}``.
#
# Anti-oracle: the response never distinguishes "wrong admin key" from "wrong
# HMAC"/"expired" (matching the local engine's signature-checked-first design),
# so an unauthenticated caller learns nothing per attempt. Rate-limited to
# bound brute-force attempts on the admin key over a LAN-exposed instance.
admin_fix_router = APIRouter(prefix="/api/v1/admin/fix", tags=["support"])

_ALLOWED_FIX_ACTIONS = ("update_setting", "delete_crash_logs", "reset_config")
# Mirrors ALLOWED_SETTING_KEYS in src-tauri/src/fix_engine.rs (defense in
# depth: the engine re-checks this list locally before applying anything).
_ALLOWED_SETTING_KEYS = (
    "session_idle_minutes",
    "session_absolute_minutes",
    "terminal_mode",
    "mobile_access_mode",
    "support_email",
)


def _fix_admin_key() -> str:
    """Read the admin key from settings on each call (monkeypatch-friendly)."""
    try:
        return getattr(get_settings(), "fix_admin_key", "") or ""
    except Exception:  # pragma: no cover - settings are cached, rarely fail
        return ""


class FixVerifyIn(BaseModel):
    """Raw fix code + admin key, sent by the Rust fix engine over loopback."""

    admin_key: str = ""
    # The envelope exactly as received (string, not parsed) so the bytes the
    # support team signed are what gets verified.
    fix_code: Optional[str] = None
    # The desktop binary's version, for the major.minor compatibility check.
    client_version: Optional[str] = None
    # Admin-key-only operation: recovery_reset_config has no fix envelope.
    requested_action: Optional[str] = None


class FixVerifyOut(BaseModel):
    valid: bool
    action: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    # Whitelisted operations this code is authorized to perform. Empty on any
    # rejection (fail-closed).
    ops: list[str] = Field(default_factory=list)


@admin_fix_router.post("/verify", response_model=FixVerifyOut, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def verify_fix_code_remote(request: Request, body: FixVerifyIn) -> FixVerifyOut:
    """Verify a fix code for the desktop engine (audit M4).

    Authenticated by the admin key (the recovery window has no user session).
    Every rejection is ``{"valid": false}``; the caller also fails closed on
    network errors and timeouts.
    """
    admin_secret = _fix_admin_key()
    if not admin_secret or not hmac.compare_digest(body.admin_key.strip(), admin_secret):
        logger.warning("fix_remote_verify_rejected")
        return FixVerifyOut(valid=False)

    # Admin-key-only operation (standalone recovery "reset configuration").
    if body.fix_code is None:
        if body.requested_action == "reset_config":
            return FixVerifyOut(valid=True, action="reset_config", payload=None, ops=["reset_config"])
        return FixVerifyOut(valid=False)

    signing_secret = _fix_code_secret()
    if not signing_secret:
        return FixVerifyOut(valid=False)

    try:
        envelope = json.loads(body.fix_code)
        action = envelope["action"]
        payload = envelope["payload"]
        sig = envelope["sig"]
        if not isinstance(action, str) or not isinstance(payload, dict) or not isinstance(sig, str):
            raise ValueError("malformed envelope")
    except (ValueError, KeyError, TypeError):
        return FixVerifyOut(valid=False)

    if not hmac.compare_digest(sign_payload(payload, signing_secret), sig.lower()):
        return FixVerifyOut(valid=False)

    # Expiry + version live inside the signed payload (see fix_engine.rs).
    expires_at = payload.get("expiresAt")
    version = payload.get("version")
    if not isinstance(expires_at, str) or not isinstance(version, str):
        return FixVerifyOut(valid=False)
    try:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return FixVerifyOut(valid=False)
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= expires_dt:
        return FixVerifyOut(valid=False)

    # Version compatibility: the code's major.minor must match the binary's.
    if body.client_version:
        if body.client_version.split(".")[:2] != version.split(".")[:2]:
            return FixVerifyOut(valid=False)

    if action not in _ALLOWED_FIX_ACTIONS:
        return FixVerifyOut(valid=False)
    if action == "update_setting":
        key = payload.get("key")
        if key not in _ALLOWED_SETTING_KEYS or "value" not in payload:
            return FixVerifyOut(valid=False)
        ops = [key]
    else:
        ops = [action]
    return FixVerifyOut(valid=True, action=action, payload=payload, ops=ops)
