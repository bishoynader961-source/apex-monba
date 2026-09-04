"""Admin user-management routes: list, read, update, deactivate (RBAC-gated)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import User
from app.core.repositories import UserRepository
from app.shared.schemas import CurrentUser, UserPublic

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role_id: Optional[int] = None


@router.get("", response_model=list[UserPublic])
async def list_users(
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[UserPublic]:
    rows = (await session.execute(select(User))).scalars().all()
    return [UserPublic.model_validate(u) for u in rows]


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    user_id: int,
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    u = await UserRepository(session).get(user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(u)


@router.put("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: int,
    body: UserUpdate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    u = await UserRepository(session).get(user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.role_id is not None:
        u.role_id = body.role_id
    session.add(u)
    await session.commit()
    return UserPublic.model_validate(u)


@router.patch("/{user_id}/active", response_model=UserPublic)
async def set_user_active(
    user_id: int,
    active: bool = True,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    u = await UserRepository(session).get(user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    u.is_active = 1 if active else 0
    session.add(u)
    await session.commit()
    return UserPublic.model_validate(u)
