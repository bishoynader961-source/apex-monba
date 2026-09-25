"""Support fix-code routes: verify a signed fix code, then apply it.

Fix codes are signed JSON::

    {"action": "update_setting", "key": "session_idle_minutes", "value": "60",
     "sig": "<HMAC-SHA256 hex>"}

The signature is computed on the server-side ``FIX_CODE_SECRET`` by the support
team's tooling (Python ``hmac``), and verified here before anything changes.
An invalid signature returns ``403`` — nobody can forge a fix code.

Note: the signing key is a *server secret*, not the JWT secret (``SECRET_KEY``
in ``config.py``). They are different values with different owners. Rotating one
never touches the other.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.config import get_settings

router = APIRouter(prefix="/api/v1/support", tags=["support"])

# The support team's signing secret. Set as FIX_CODE_SECRET in the backend .env;
# never committed, never leaves the server. Different from SECRET_KEY.
FIX_CODE_SECRET = ""
try:
    from app.shared.config import get_settings

    _cfg = get_settings()
    _fc = getattr(_cfg, "fix_code_secret", "")
    if _fc:
        FIX_CODE_SECRET = _fc
except Exception:
    pass


class FixCodeIn(BaseModel):
    action: str
    payload: dict[str, Any]


class FixCodeOut(BaseModel):
    action: str
    payload: dict[str, Any]


def _verify_fix_signature(payload: dict[str, Any]) -> bool:
    """Return True only if the signature matches the HMAC-SHA256 of the payload."""
    if not FIX_CODE_SECRET:
        return False
    # The signature is computed as HMAC-SHA256 over the canonical JSON payload,
    # with sorted keys so the same bytes always produce the same message.
    message = __import__("json").dumps(payload["payload"], sort_keys=True).encode("utf-8")
    expected = hmac.new(
        FIX_CODE_SECRET.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, payload.get("sig", ""))


@router.post("/fix-code/verify", response_model=FixCodeOut, status_code=status.HTTP_200_OK)
async def verify_fix_code(
    body: FixCodeIn,
    _user: Any = Depends(require_permission("settings.write")),
    session: AsyncSession = Depends(get_session),
) -> FixCodeOut:
    """Verify the signature; apply the fix only if valid.

    Returns 403 for any tampering so the frontend can never trust an unsigned
    or unknown-code submission.
    """
    if not _verify_fix_signature(body.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid fix code signature",
        )

    payload = body.payload
    if body.action == "update_setting" and "key" in payload and "value" in payload:
        key = payload["key"]
        value = str(payload["value"])
        setting = await session.get(SystemSetting, key)
        if setting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting '{key}' not found",
            )
        setting.value = value.encode("utf-8")
        await session.commit()
        return FixCodeOut(action="update_setting", payload=payload)
    if body.action == "reload_permissions":
        # No DB change; refresh is a client-side action.
        return FixCodeOut(action="reload_permissions", payload={})

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown action: {body.action}",
    )
