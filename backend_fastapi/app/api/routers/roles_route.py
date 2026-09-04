"""RBAC roles management routes: CRUD + permission matrix (RBAC-gated)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import Role, Permission, RolePermission
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    is_system: int = 0


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    feature_key: str
    description: Optional[str] = None


class RolePermissionUpdate(BaseModel):
    permission_ids: list[int]


@router.get("", response_model=list[RoleRead])
async def list_roles(
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[RoleRead]:
    rows = (await session.execute(select(Role))).scalars().all()
    return [RoleRead.model_validate(r) for r in rows]


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: int,
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> RoleRead:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return RoleRead.model_validate(role)


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> RoleRead:
    role = Role(name=body.name, description=body.description, is_system=0)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return RoleRead.model_validate(role)


@router.put("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: int,
    body: RoleUpdate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> RoleRead:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify system roles")
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    session.add(role)
    await session.commit()
    return RoleRead.model_validate(role)


@router.get("/{role_id}/permissions", response_model=list[int])
async def get_role_permissions(
    role_id: int,
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[int]:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    rows = (
        await session.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role_id,
                RolePermission.granted == 1,
            )
        )
    ).scalars().all()
    return list(rows)


@router.put("/{role_id}/permissions")
async def set_role_permissions(
    role_id: int,
    body: RolePermissionUpdate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[int]]:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify system role permissions")
    # Remove existing
    await session.execute(
        sql_delete(RolePermission).where(RolePermission.role_id == role_id)
    )
    # Insert new
    for pid in body.permission_ids:
        session.add(RolePermission(role_id=role_id, permission_id=pid, granted=1))
    await session.commit()
    return {"permission_ids": body.permission_ids}


@router.get("/permissions/all", response_model=list[PermissionRead])
async def list_all_permissions(
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[PermissionRead]:
    rows = (await session.execute(select(Permission))).scalars().all()
    return [PermissionRead.model_validate(p) for p in rows]
