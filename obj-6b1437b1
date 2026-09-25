"""Coupon service: CRUD + validation for promotional coupons."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Coupon
from app.shared.exceptions import AppException, NotFoundError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CouponCreate,
    CouponRead,
    CouponUpdate,
    CouponValidateResult,
)

logger = get_logger("coupon")


class CouponService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_coupons(self, active_only: bool = False) -> list[CouponRead]:
        """List all coupons, optionally filtering to active ones."""
        stmt = select(Coupon).order_by(Coupon.id.desc())
        if active_only:
            stmt = stmt.where(Coupon.is_active == 1)
        result = await self.session.execute(stmt)
        return [CouponRead.model_validate(c) for c in result.scalars().all()]

    async def get_coupon(self, coupon_id: int) -> CouponRead:
        """Get a single coupon by ID."""
        coupon = await self.session.get(Coupon, coupon_id)
        if coupon is None:
            raise NotFoundError("Coupon", str(coupon_id))
        return CouponRead.model_validate(coupon)

    async def create_coupon(self, payload: CouponCreate) -> CouponRead:
        """Create a new coupon. Code is uppercased and must be unique."""
        code = payload.code.strip().upper()
        existing = (
            await self.session.execute(select(Coupon).where(Coupon.code == code))
        ).scalar_one_or_none()
        if existing is not None:
            raise AppException(
                f"Coupon code '{code}' already exists",
                status_code=409,
                error_code="coupon_duplicate",
            )
        coupon = Coupon(
            code=code,
            description=payload.description,
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            min_purchase=payload.min_purchase,
            max_uses=payload.max_uses,
            expires_at=payload.expires_at,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.session.add(coupon)
        await self.session.flush()
        return CouponRead.model_validate(coupon)

    async def update_coupon(self, coupon_id: int, payload: CouponUpdate) -> CouponRead:
        """Update an existing coupon."""
        coupon = await self.session.get(Coupon, coupon_id)
        if coupon is None:
            raise NotFoundError("Coupon", str(coupon_id))
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(coupon, field, value)
        await self.session.flush()
        return CouponRead.model_validate(coupon)

    async def delete_coupon(self, coupon_id: int) -> CouponRead:
        """Soft-delete a coupon (set is_active=0)."""
        coupon = await self.session.get(Coupon, coupon_id)
        if coupon is None:
            raise NotFoundError("Coupon", str(coupon_id))
        coupon.is_active = 0
        await self.session.flush()
        return CouponRead.model_validate(coupon)

    async def validate_coupon(self, code: str, subtotal: Decimal) -> CouponValidateResult:
        """Validate a coupon code against the cart subtotal."""
        code = code.strip().upper()
        coupon = (
            await self.session.execute(select(Coupon).where(Coupon.code == code))
        ).scalar_one_or_none()
        if coupon is None:
            return CouponValidateResult(valid=False, code=code, message="Coupon not found")
        if coupon.is_active != 1:
            return CouponValidateResult(valid=False, code=code, message="Coupon is no longer active")
        if coupon.expires_at and coupon.expires_at < datetime.now(timezone.utc).isoformat():
            return CouponValidateResult(valid=False, code=code, message="Coupon has expired")
        if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
            return CouponValidateResult(valid=False, code=code, message="Coupon usage limit reached")
        if subtotal < coupon.min_purchase:
            return CouponValidateResult(
                valid=False,
                code=code,
                message=f"Minimum purchase of ${coupon.min_purchase} required",
            )
        return CouponValidateResult(
            valid=True,
            coupon_id=coupon.id,
            code=coupon.code,
            discount_type=coupon.discount_type,
            discount_value=coupon.discount_value,
            message="Coupon applied",
        )

    async def increment_usage(self, coupon_id: int) -> None:
        """Increment the used_count for a coupon after successful checkout."""
        coupon = await self.session.get(Coupon, coupon_id)
        if coupon is not None:
            coupon.used_count += 1
            await self.session.flush()
