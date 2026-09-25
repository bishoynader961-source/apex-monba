"""Barcode sequence, validation, and strategy-based generation endpoints."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import Product
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/barcodes", tags=["barcodes"])


class BarcodeStrategy(str, Enum):
    """Pharmacy-generated internal barcode strategies (Spec: Objective 2)."""

    random = "random"          # default/safest: collision-resistant secure random
    sequential = "sequential"  # auto-increment from a base (e.g. 10001, 10002)
    manual = "manual"          # user-typed value, uniqueness-checked
    pattern = "pattern"        # pattern tokens: [YYYY] [MM] [DD] [0000] [CAT] [PREFIX]
    manufacturer = "manufacturer"  # reuse the existing manufacturer barcode


class BarcodeGenerateRequest(BaseModel):
    strategy: BarcodeStrategy = BarcodeStrategy.random
    value: str | None = None        # manual strategy: the user-typed barcode
    prefix: str = "GEN"            # random/sequential/pattern prefix
    pattern: str | None = None      # pattern strategy, e.g. "RX-[YYYY]-[0000]"
    category: str | None = None     # pattern strategy [CAT] token
    manufacturer_barcode: str | None = None  # manufacturer strategy source


class BarcodeGenerateResponse(BaseModel):
    barcode: str
    strategy: BarcodeStrategy


class NextSequenceResponse(BaseModel):
    next: int


class ValidateBarcodeResponse(BaseModel):
    exists: bool


@router.get("/next-sequence", response_model=NextSequenceResponse, status_code=status.HTTP_200_OK)
async def get_next_sequence(
    prefix: str = Query(..., min_length=1, description="Barcode prefix to get next sequence for"),
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> NextSequenceResponse:
    """
    Get the next sequential number for a given barcode prefix.
    Counts existing barcodes in the database that start with the prefix.
    """
    # Count existing products with internal_unique_barcode starting with the prefix
    count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.internal_unique_barcode.like(f"{prefix}%")
        )
    )
    return NextSequenceResponse(next=(count or 0) + 1)


@router.post("/generate", response_model=BarcodeGenerateResponse, status_code=status.HTTP_200_OK)
async def generate_barcode(
    req: BarcodeGenerateRequest,
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> BarcodeGenerateResponse:
    """Generate an internal barcode using the requested strategy.

    - random (default/safest): ``PREFIX-XXXXXXXXXX`` from a CSPRNG.
    - sequential: ``PREFIX-10001`` style, next free number above the highest
      existing sequence for the prefix.
    - manual: user-supplied value; rejected if already in use.
    - pattern: tokens [YYYY], [MM], [DD], [PREFIX], [CAT], [0000] (zero-padded
      sequence) auto-filled from today's date / category.
    - manufacturer: echoes the product's manufacturer barcode (use it as-is).
    """
    prefix = (req.prefix or "GEN").upper().strip() or "GEN"

    async def exists(value: str) -> bool:
        found = await session.scalar(
            select(func.count(Product.id)).where(Product.internal_unique_barcode == value)
        )
        return (found or 0) > 0

    if req.strategy is BarcodeStrategy.manufacturer:
        if not req.manufacturer_barcode or not req.manufacturer_barcode.strip():
            raise HTTPException(status_code=400, detail="No manufacturer barcode on this product to reuse.")
        return BarcodeGenerateResponse(barcode=req.manufacturer_barcode.strip(), strategy=req.strategy)

    if req.strategy is BarcodeStrategy.manual:
        value = (req.value or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="Manual strategy requires a value.")
        if await exists(value):
            raise HTTPException(status_code=409, detail=f"Barcode '{value}' is already in use.")
        return BarcodeGenerateResponse(barcode=value, strategy=req.strategy)

    if req.strategy is BarcodeStrategy.random:
        for _ in range(10):  # collision-resistant; retry is belt-and-braces
            candidate = f"{prefix}-{secrets.token_hex(5).upper()}"
            if not await exists(candidate):
                return BarcodeGenerateResponse(barcode=candidate, strategy=req.strategy)
        raise HTTPException(status_code=500, detail="Could not generate a unique random barcode.")

    if req.strategy is BarcodeStrategy.sequential:
        base = 10000
        highest = await session.scalar(
            select(func.max(Product.id)).where(
                Product.internal_unique_barcode.like(f"{prefix}-%")
            )
        )
        # Next number = count of prefix barcodes + base, bumped until free.
        count = await session.scalar(
            select(func.count(Product.id)).where(
                Product.internal_unique_barcode.like(f"{prefix}-%")
            )
        )
        candidate_num = base + (count or 0) + 1
        for _ in range(1000):
            candidate = f"{prefix}-{candidate_num}"
            if not await exists(candidate):
                return BarcodeGenerateResponse(barcode=candidate, strategy=req.strategy)
            candidate_num += 1
        raise HTTPException(status_code=500, detail="Could not allocate a sequential barcode.")

    # pattern strategy
    pattern = (req.pattern or "").strip()
    if not pattern:
        raise HTTPException(status_code=400, detail="Pattern strategy requires a pattern.")
    now = datetime.now()
    count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.internal_unique_barcode.like(f"{prefix}-%")
        )
    )
    seq = (count or 0) + 1
    for _ in range(1000):
        candidate = (
            pattern.replace("[YYYY]", f"{now.year:04d}")
            .replace("[MM]", f"{now.month:02d}")
            .replace("[DD]", f"{now.day:02d}")
            .replace("[PREFIX]", prefix)
            .replace("[CAT]", (req.category or "GEN").upper()[:8])
            .replace("[0000]", f"{seq:04d}")
        )
        if not await exists(candidate):
            return BarcodeGenerateResponse(barcode=candidate, strategy=req.strategy)
        seq += 1
    raise HTTPException(status_code=500, detail="Could not allocate a pattern barcode.")


@router.post("/validate", response_model=ValidateBarcodeResponse, status_code=status.HTTP_200_OK)
async def validate_barcode(
    barcode: str = Query(..., min_length=1, description="Barcode value to validate"),
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> ValidateBarcodeResponse:
    """
    Check if a barcode value already exists in the database.
    Checks both manufacturer_barcode and internal_unique_barcode fields.
    """
    exists = await session.scalar(
        select(func.count(Product.id)).where(
            (Product.manufacturer_barcode == barcode) | (Product.internal_unique_barcode == barcode)
        )
    )
    return ValidateBarcodeResponse(exists=(exists or 0) > 0)