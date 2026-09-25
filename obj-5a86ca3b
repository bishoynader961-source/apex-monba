"""System settings routes: read + write (RBAC-gated)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import SystemSetting
from app.core.ttl_cache import cache_get, cache_invalidate, cache_set
from app.shared.schemas import CurrentUser, SystemSettingRead

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Read-through TTL cache for the settings list (Phase 3 diagnostics: highly
# queried, rarely changed). Invalidated on every write below.
_SETTINGS_CACHE_KEY = "settings:list"
_SETTINGS_CACHE_TTL = 60.0


def _decode(value: Optional[bytes]) -> Optional[str]:
    return value.decode("utf-8") if value else None


class SettingUpdate(BaseModel):
    value: str


@router.get("", response_model=list[SystemSettingRead])
async def list_settings(
    _user: CurrentUser = Depends(require_permission("settings.read")),
    session: AsyncSession = Depends(get_session),
) -> list[SystemSettingRead]:
    cached = cache_get(_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    rows = (await session.execute(select(SystemSetting))).scalars().all()
    result = [SystemSettingRead(key=s.key, value=_decode(s.value)) for s in rows]
    cache_set(_SETTINGS_CACHE_KEY, result, _SETTINGS_CACHE_TTL)
    return result


@router.get("/{key}", response_model=SystemSettingRead)
async def get_setting(
    key: str,
    _user: CurrentUser = Depends(require_permission("settings.read")),
    session: AsyncSession = Depends(get_session),
) -> SystemSettingRead:
    setting = await session.get(SystemSetting, key)
    if setting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    return SystemSettingRead(key=setting.key, value=_decode(setting.value))


@router.put("/{key}", response_model=SystemSettingRead)
async def update_setting(
    key: str,
    body: SettingUpdate,
    _user: CurrentUser = Depends(require_permission("settings.write")),
    session: AsyncSession = Depends(get_session),
) -> SystemSettingRead:
    setting = await session.get(SystemSetting, key)
    if setting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    setting.value = body.value.encode("utf-8")
    session.add(setting)
    await session.commit()
    cache_invalidate(_SETTINGS_CACHE_KEY)
    return SystemSettingRead(key=setting.key, value=body.value)
