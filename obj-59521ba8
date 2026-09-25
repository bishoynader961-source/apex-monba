"""Compound prescription routes: formula CRUD, pricing, and FIFO dispensing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.compound_service import CompoundService
from app.shared.schemas import (
    CompoundCreate,
    CompoundDispenseRequest,
    CompoundDispenseResult,
    CompoundPriceCalculationRequest,
    CompoundPriceCalculationResult,
    CompoundRead,
    CompoundUpdate,
    CurrentUser,
)

router = APIRouter(prefix="/api/v1/compounds", tags=["compounds"])


@router.post("", response_model=CompoundRead, status_code=status.HTTP_201_CREATED)
async def create_compound(
    payload: CompoundCreate,
    user: CurrentUser = Depends(require_permission("compounds.write")),
    session: AsyncSession = Depends(get_session),
) -> CompoundRead:
    """Create a new compound formula with ingredients."""
    service = CompoundService(session)
    return await service.create_compound(payload, user)


@router.get("", response_model=list[CompoundRead])
async def list_compounds(
    page: int = 1,
    page_size: int = 50,
    user: CurrentUser = Depends(require_permission("compounds.read")),
    session: AsyncSession = Depends(get_session),
) -> list[CompoundRead]:
    """List all compound formulas with pagination."""
    service = CompoundService(session)
    compounds, _ = await service.list_compounds(page=page, page_size=page_size)
    return compounds


@router.get("/{compound_id}", response_model=CompoundRead)
async def get_compound(
    compound_id: int,
    user: CurrentUser = Depends(require_permission("compounds.read")),
    session: AsyncSession = Depends(get_session),
) -> CompoundRead:
    """Get a compound formula with ingredients."""
    service = CompoundService(session)
    return await service.get_compound(compound_id)


@router.put("/{compound_id}", response_model=CompoundRead)
async def update_compound(
    compound_id: int,
    payload: CompoundUpdate,
    user: CurrentUser = Depends(require_permission("compounds.write")),
    session: AsyncSession = Depends(get_session),
) -> CompoundRead:
    """Update a compound formula (replaces ingredients if provided)."""
    service = CompoundService(session)
    return await service.update_compound(compound_id, payload, user)


@router.delete("/{compound_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compound(
    compound_id: int,
    user: CurrentUser = Depends(require_permission("compounds.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a compound formula."""
    service = CompoundService(session)
    await service.delete_compound(compound_id, user)


@router.post("/{compound_id}/price", response_model=CompoundPriceCalculationResult)
async def calculate_compound_price(
    compound_id: int,
    payload: CompoundPriceCalculationRequest,
    user: CurrentUser = Depends(require_permission("compounds.read")),
    session: AsyncSession = Depends(get_session),
) -> CompoundPriceCalculationResult:
    """Calculate compound price from ingredient costs + PriceCode formula."""
    service = CompoundService(session)
    return await service.calculate_price(payload)


@router.post("/dispense", response_model=CompoundDispenseResult, status_code=status.HTTP_201_CREATED)
async def dispense_compound(
    payload: CompoundDispenseRequest,
    user: CurrentUser = Depends(require_permission("compounds.dispense")),
    session: AsyncSession = Depends(get_session),
) -> CompoundDispenseResult:
    """Dispense a compound: consume ingredients via FIFO, create dispense record."""
    service = CompoundService(session)
    return await service.dispense_compound(payload, user)