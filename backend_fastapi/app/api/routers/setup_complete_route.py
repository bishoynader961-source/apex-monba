"""First-run setup completion (Sprint 2D).

Lives OUTSIDE the setup-gated surface: ``require_setup_complete`` is applied
at include time to every non-exempt router, so the endpoint that FLIPS the
flag must be mounted on its own exempt router (prefix matches the admin API
so the client contract stays ``POST /api/v1/admin/setup/complete``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/admin", tags=["setup"])


@router.post("/setup/complete", status_code=200)
async def complete_setup(
    session: AsyncSession = Depends(get_session),
    _auth: CurrentUser = Depends(require_permission("settings.manage")),
) -> dict[str, bool]:
    """First-run gate (Sprint 2D): admin flips ``setup_complete`` to true.

    Intentionally mounted on an un-gated router — this is the endpoint that
    ends the first-run state. Still admin-only (settings.manage)."""
    setting = await session.get(SystemSetting, "setup_complete")
    if setting is None:
        session.add(SystemSetting(key="setup_complete", value="true".encode("utf-8")))
    else:
        setting.value = "true".encode("utf-8")
    await session.commit()
    return {"setup_complete": True}
