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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.config import get_settings

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
