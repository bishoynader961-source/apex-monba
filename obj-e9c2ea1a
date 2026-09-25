"""Setup routes: first-run status and completion."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.models import User
from app.core.repositories import UserRepository
from app.services.seed_service import seed_admin_role, seed_clinical_defaults
from app.shared.security import hash_password

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


class SetupStatusResponse(BaseModel):
    setup_required: bool


class SetupCompleteRequest(BaseModel):
    admin_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: Optional[str] = None
    pharmacy_name: str = Field(default="", max_length=255)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=50)
    license_number: str = Field(default="", max_length=100)


class SetupCompleteResponse(BaseModel):
    success: bool


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: AsyncSession = Depends(get_session)) -> SetupStatusResponse:
    """Check if first-run setup is required.

    Returns setup_required=true when there are zero users in the database.
    This endpoint is unauthenticated.
    """
    user_count = await db.scalar(select(func.count()).select_from(User))
    return SetupStatusResponse(setup_required=user_count == 0)


@router.post("/complete", response_model=SetupCompleteResponse)
async def complete_setup(
    payload: SetupCompleteRequest,
    db: AsyncSession = Depends(get_session),
) -> SetupCompleteResponse:
    """Complete the first-run setup by creating the admin user and pharmacy profile.

    This endpoint only works when user count is 0 (fresh database).
    Returns 403 if setup has already been completed.
    """
    user_count = await db.scalar(select(func.count()).select_from(User))
    if user_count > 0:
        raise HTTPException(status_code=403, detail="Setup already completed")

    # Server-side password confirmation (the wizard also checks client-side).
    if payload.confirm_password is not None and payload.confirm_password != payload.password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Create admin role (role_id=1) and grant all permissions
    await seed_admin_role(db)
    await seed_clinical_defaults(db)

    # Create admin user with role_id=1
    password_hash = hash_password(payload.password)
    repo = UserRepository(db)
    await repo.create(
        username=payload.username,
        display_name=payload.admin_name,
        password_hash=password_hash,
        role_id=1,
    )

    # Store pharmacy settings (upsert — lifespan seeding may have created
    # empty defaults such as pharmacy_name already; blind INSERT would 500
    # on the UNIQUE key and strand the buyer after their admin was created).
    from app.core.models import SystemSetting
    pharmacy_settings = {
        "pharmacy_name": payload.pharmacy_name,
        "pharmacy_address": payload.address,
        "pharmacy_phone": payload.phone,
        "pharmacy_license": payload.license_number,
    }
    for key, val in pharmacy_settings.items():
        if not val:
            continue
        existing = await db.get(SystemSetting, key)
        if existing is None:
            db.add(SystemSetting(key=key, value=val.encode("utf-8")))
        else:
            existing.value = val.encode("utf-8")

    await db.commit()

    return SetupCompleteResponse(success=True)