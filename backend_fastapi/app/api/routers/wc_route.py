"""Workers' Compensation Claims CRUD routes."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import WCClaimRepository
from app.shared.schemas import (
    CurrentUser,
    WCClaimCreate,
    WCClaimRead,
    WCClaimUpdate,
)

router = APIRouter(prefix="/api/v1/wc-claims", tags=["workers-compensation"])


def _money_value(payload: WCClaimCreate | WCClaimUpdate, field: str) -> Decimal:
    value = getattr(payload, field, None)
    return value if value is not None else Decimal("0")


def _validate_money_totals(payload: WCClaimCreate | WCClaimUpdate) -> None:
    """H6 money-safety: enforce the WC accounting identity on every write.

    Mirrors the Phase-1 checkout contract. Non-negativity and the
    Numeric(10,2) column cap live in the schemas (Field ge=0/le); this check
    enforces total_charges == insurance_paid + patient_responsibility.
    Unadjudicated claims may keep all three at their zero defaults; on
    update, supply the full balanced triplet or none at all.
    """
    total = _money_value(payload, "total_charges")
    paid = _money_value(payload, "insurance_paid")
    patient = _money_value(payload, "patient_responsibility")
    if total != paid + patient:
        raise HTTPException(
            status_code=422,
            detail=(
                "WC claim totals do not balance: total_charges "
                f"({total}) must equal insurance_paid ({paid}) + "
                f"patient_responsibility ({patient})"
            ),
        )


@router.get("", response_model=list[WCClaimRead])
async def list_claims(
    patient_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _auth: CurrentUser = Depends(require_permission("wc.read")),
    session: AsyncSession = Depends(get_session),
) -> list[WCClaimRead]:
    """List Workers' Compensation claims with optional filters."""
    repo = WCClaimRepository(session)
    claims, _ = await repo.list(
        patient_id=patient_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return [WCClaimRead.model_validate(c) for c in claims]


@router.get("/{claim_id}", response_model=WCClaimRead)
async def get_claim(
    claim_id: int,
    _auth: CurrentUser = Depends(require_permission("wc.read")),
    session: AsyncSession = Depends(get_session),
) -> WCClaimRead:
    """Get a single Workers' Compensation claim by ID."""
    repo = WCClaimRepository(session)
    claim = await repo.get(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="WC claim not found")
    return WCClaimRead.model_validate(claim)


@router.post("", response_model=WCClaimRead, status_code=201)
async def create_claim(
    payload: WCClaimCreate,
    _auth: CurrentUser = Depends(require_permission("wc.write")),
    session: AsyncSession = Depends(get_session),
) -> WCClaimRead:
    """Create a new Workers' Compensation claim."""
    repo = WCClaimRepository(session)
    existing = await repo.get_by_claim_number(payload.claim_number)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Claim number '{payload.claim_number}' already exists",
        )
    _validate_money_totals(payload)
    claim = await repo.create(payload)
    return WCClaimRead.model_validate(claim)


@router.put("/{claim_id}", response_model=WCClaimRead)
async def update_claim(
    claim_id: int,
    payload: WCClaimUpdate,
    _auth: CurrentUser = Depends(require_permission("wc.write")),
    session: AsyncSession = Depends(get_session),
) -> WCClaimRead:
    """Update a Workers' Compensation claim."""
    repo = WCClaimRepository(session)
    _validate_money_totals(payload)
    claim = await repo.update(claim_id, payload)
    if claim is None:
        raise HTTPException(status_code=404, detail="WC claim not found")
    return WCClaimRead.model_validate(claim)


@router.delete("/{claim_id}", status_code=204)
async def delete_claim(
    claim_id: int,
    _auth: CurrentUser = Depends(require_permission("wc.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a Workers' Compensation claim."""
    repo = WCClaimRepository(session)
    deleted = await repo.delete(claim_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="WC claim not found")
