"""Coupon routes: CRUD + validation for promotional coupons."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.coupon_service import CouponService
from app.shared.schemas import (
    CouponCreate,
    CouponRead,
    CouponUpdate,
    CouponValidateResult,
    CurrentUser,
)
from pydantic import BaseModel
from decimal import Decimal

router = APIRouter(prefix="/api/v1/coupons", tags=["coupons"])


class CouponValidateRequest(BaseModel):
    code: str
    subtotal: Decimal


@router.get("/", response_model=list[CouponRead], status_code=status.HTTP_200_OK)
async def list_coupons(
    active_only: bool = Query(default=False),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> list[CouponRead]:
    """List all coupons (admin)."""
    return await CouponService(session).list_coupons(active_only=active_only)


@router.get("/{coupon_id}", response_model=CouponRead, status_code=status.HTTP_200_OK)
async def get_coupon(
    coupon_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> CouponRead:
    """Get a single coupon by ID."""
    return await CouponService(session).get_coupon(coupon_id)


@router.post("/", response_model=CouponRead, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    payload: CouponCreate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> CouponRead:
    """Create a new coupon."""
    return await CouponService(session).create_coupon(payload)


@router.put("/{coupon_id}", response_model=CouponRead, status_code=status.HTTP_200_OK)
async def update_coupon(
    coupon_id: int,
    payload: CouponUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> CouponRead:
    """Update an existing coupon."""
    return await CouponService(session).update_coupon(coupon_id, payload)


@router.delete("/{coupon_id}", response_model=CouponRead, status_code=status.HTTP_200_OK)
async def delete_coupon(
    coupon_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> CouponRead:
    """Soft-delete a coupon (set is_active=0)."""
    return await CouponService(session).delete_coupon(coupon_id)


@router.post("/validate", response_model=CouponValidateResult, status_code=status.HTTP_200_OK)
async def validate_coupon(
    payload: CouponValidateRequest,
    _auth: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> CouponValidateResult:
    """Validate a coupon code against a cart subtotal."""
    return await CouponService(session).validate_coupon(payload.code, payload.subtotal)
