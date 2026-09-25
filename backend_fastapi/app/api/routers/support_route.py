"""Support contact route: read-only contact details for every logged-in user.

GET /api/v1/support/contact — returns the support email/name/message plus the
pharmacy name. Unlike GET /api/v1/settings (which requires ``settings.read``),
this endpoint only needs an authenticated user so non-admin roles see live
support values instead of a 403.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/support", tags=["support"])

_DEFAULTS = {
    "support_email": "pharmacypro.support@gmail.com",
    "support_name": "PharmacySuite Support",
    "support_message": "For feature requests, technical issues, or questions, email us anytime.",
    "pharmacy_name": "",
    "security_notice": (
        "Official support will NEVER ask for your password, your secret.key file, "
        "or your pharmacy.db file. We will never call you first or request remote "
        "access. If someone claiming to be us asks for any of these, it is a scam — "
        "report it to us at the email above."
    ),
}


def _decode(value: Optional[bytes]) -> Optional[str]:
    return value.decode("utf-8") if value else None


class SupportContact(BaseModel):
    support_email: str
    support_name: str
    support_message: str
    pharmacy_name: str
    security_notice: str


@router.get("/contact", response_model=SupportContact)
async def support_contact(
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SupportContact:
    """Return live support contact details for any authenticated user."""
    values = dict(_DEFAULTS)
    for key in _DEFAULTS:
        row = await session.get(SystemSetting, key)
        decoded = _decode(row.value) if row is not None else None
        if decoded:
            values[key] = decoded
    return SupportContact(**values)
