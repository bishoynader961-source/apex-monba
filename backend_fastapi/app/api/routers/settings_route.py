"""System settings routes: read-only (RBAC-gated)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.shared.schemas import CurrentUser, SystemSettingRead

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _decode(value: Optional[bytes]) -> Optional[str]:
    return value.decode("utf-8") if value else None


@router.get("", response_model=list[SystemSettingRead])
async def list_settings(
    _user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[SystemSettingRead]:
    rows = (await session.execute(select(SystemSetting))).scalars().all()
    return [SystemSettingRead(key=s.key, value=_decode(s.value)) for s in rows]


@router.get("/{key}", response_model=SystemSettingRead)
async def get_setting(
    key: str,
    _user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> SystemSettingRead:
    setting = await session.get(SystemSetting, key)
    if setting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    return SystemSettingRead(key=setting.key, value=_decode(setting.value))
