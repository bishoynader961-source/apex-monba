"""RBAC roles management routes: CRUD + permission matrix (RBAC-gated).

Route order matters in FastAPI/Starlette: static/literal paths must be registered
BEFORE parameterized paths (e.g. /{role_id}) to avoid 405 errors.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import LockedFeature, Permission, Role, RolePermission, SystemSetting, User
from app.core.ttl_cache import cache_invalidate_prefix
from app.shared.security import hash_password, verify_password
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


class LockToggleRequest(BaseModel):
    is_locked: bool


class LockPasswordRequest(BaseModel):
    password: str


class LockPasswordVerifyRequest(BaseModel):
    password: str


class LockStatusResponse(BaseModel):
    feature_key: str
    is_locked: bool
    description: Optional[str] = None


class PermissionCreate(BaseModel):
    feature_key: str
    description: Optional[str] = None


class PermissionCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    feature_key: str
    description: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# STATIC ROUTES FIRST — must come before any /{role_id} parameterized routes
# to prevent FastAPI/Starlette from routing /permissions and /lock-password
# to the /{role_id} GET handler and returning 405.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[RoleRead])
async def list_roles(
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[RoleRead]:
    rows = (await session.execute(select(Role))).scalars().all()
    return [RoleRead.model_validate(r) for r in rows]


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
    cache_invalidate_prefix("perms:")
    return RoleRead.model_validate(role)


@router.post("/permissions", response_model=PermissionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    payload: PermissionCreate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> PermissionCreateResponse:
    """Create a new permission/feature key (owner-only extensibility).

    Feature key must follow the pattern: module.action (e.g., reports.view, inventory.export)
    """
    # Only role_id=1 (owner) can create new permissions
    if _user.role_id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can create new permissions",
        )

    # Validate feature_key format: module.action
    import re
    if not re.match(r'^[a-z]+\.[a-z]+$', payload.feature_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feature key must follow pattern: module.action (lowercase, e.g., reports.view)",
        )

    # Check if already exists
    existing = await session.get(Permission, payload.feature_key)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission '{payload.feature_key}' already exists",
        )

    perm = Permission(feature_key=payload.feature_key, description=payload.description)
    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return PermissionCreateResponse.model_validate(perm)


@router.get("/permissions/all", response_model=list[PermissionRead])
async def list_all_permissions(
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> list[PermissionRead]:
    rows = (await session.execute(select(Permission))).scalars().all()
    return [PermissionRead.model_validate(p) for p in rows]


@router.get("/permissions/{feature_key}/lock-status", response_model=LockStatusResponse)
async def get_lock_status(
    feature_key: str,
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> LockStatusResponse:
    """Get lock status for a specific permission/feature."""
    perm = await session.get(Permission, feature_key)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    locked = await session.get(LockedFeature, feature_key)
    return LockStatusResponse(
        feature_key=feature_key,
        is_locked=locked.is_locked if locked else 0,
        description=locked.description if locked else perm.description,
    )


@router.put("/permissions/{feature_key}/lock", response_model=LockStatusResponse)
async def toggle_lock(
    feature_key: str,
    payload: LockToggleRequest,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> LockStatusResponse:
    """Toggle lock on a permission/feature. Requires lock password unless role_id=1."""
    # Only role_id=1 can toggle locks without providing lock password
    if _user.role_id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can toggle feature locks",
        )

    perm = await session.get(Permission, feature_key)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    locked = await session.get(LockedFeature, feature_key)
    if not locked:
        locked = LockedFeature(feature_key=feature_key, is_locked=0)
        session.add(locked)

    locked.is_locked = 1 if payload.is_locked else 0
    locked.description = perm.description
    locked.locked_by_user_id = _user.user_id
    locked.locked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    await session.commit()
    await session.refresh(locked)

    return LockStatusResponse(
        feature_key=feature_key,
        is_locked=locked.is_locked,
        description=locked.description,
    )


@router.post("/lock-password")
async def set_lock_password(
    payload: LockPasswordRequest,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Set or change the owner's lock password (stored in SystemSetting)."""
    # Only role_id=1 (owner) can set the lock password
    if _user.role_id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner (role_id=1) can set the lock password",
        )
    setting = await session.get(SystemSetting, "owner_lock_password_hash")
    hashed = hash_password(payload.password)
    if setting:
        setting.value = hashed
    else:
        setting = SystemSetting(key="owner_lock_password_hash", value=hashed)
        session.add(setting)
    await session.commit()
    return {"message": "Lock password set successfully"}


@router.post("/lock-password/verify")
async def verify_lock_password(
    payload: LockPasswordVerifyRequest,
    _user: CurrentUser = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Verify a lock password attempt (returns true/false, no role_id=1 check needed)."""
    setting = await session.get(SystemSetting, "owner_lock_password_hash")
    if not setting or not setting.value:
        return {"valid": False}
    valid = verify_password(payload.password, setting.value)
    return {"valid": valid}


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETERIZED ROUTES — come AFTER all static routes above
# ─────────────────────────────────────────────────────────────────────────────

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


@router.put("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: int,
    body: RoleUpdate,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> RoleRead:
    # Protect immutable admin role (id=1)
    if role_id == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify the immutable administrator role",
        )
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system roles",
        )
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    session.add(role)
    await session.commit()
    cache_invalidate_prefix("perms:")
    return RoleRead.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    _user: CurrentUser = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Permanently delete a custom role.

    Guards:
    - Role ID 1 (Administrator) is immutable and can never be deleted.
    - System roles (is_system=1) cannot be deleted.
    - Roles assigned to active users cannot be deleted (409 Conflict).
    """
    # Hardcoded guard: immutable administrator role
    if role_id == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the immutable administrator role (Role ID 1)",
        )
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system roles",
        )
    # Prevent deletion if any user is still assigned this role
    user_with_role = await session.scalar(
        select(User.id).where(User.role_id == role_id).limit(1)
    )
    if user_with_role is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete role '{role.name}': it is assigned to one or more users. "
                "Reassign all users to a different role first."
            ),
        )
    # Remove role-permission links first (cascade safety for databases without FK cascades)
    await session.execute(sql_delete(RolePermission).where(RolePermission.role_id == role_id))
    await session.delete(role)
    await session.commit()
    cache_invalidate_prefix("perms:")


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
    # Protect immutable admin role (id=1)
    if role_id == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify permissions of the immutable administrator role",
        )
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system role permissions",
        )
    # Remove existing grants
    await session.execute(
        sql_delete(RolePermission).where(RolePermission.role_id == role_id)
    )
    # Insert new grants
    for pid in body.permission_ids:
        session.add(RolePermission(role_id=role_id, permission_id=pid, granted=1))
    await session.commit()
    # Permissions changed → drop cached (role_name, permissions) tuples so
    # subsequent requests re-source from the DB immediately.
    cache_invalidate_prefix("perms:")
    return {"permission_ids": body.permission_ids}
