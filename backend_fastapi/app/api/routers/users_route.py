"""Admin user-management routes: list and read users (RBAC-gated)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import User
from app.core.repositories import UserRepository
from app.shared.schemas import CurrentUser, UserPublic

router = APIRouter(prefix="/api/v1/users", tags=["users"])


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
