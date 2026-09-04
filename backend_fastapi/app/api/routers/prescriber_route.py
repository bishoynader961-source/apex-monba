"""Prescriber routes: CRUD for physician/prescriber master records."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import PrescriberRepository
from app.shared.schemas import PrescriberCreate, PrescriberRead

router = APIRouter(prefix="/api/v1/prescribers", tags=["prescribers"])


@router.get("", response_model=List[PrescriberRead])
async def list_prescribers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> List[PrescriberRead]:
    items, _ = await PrescriberRepository(session).all(
        page=page, page_size=page_size, search=search
    )
    return [PrescriberRead.model_validate(p) for p in items]


@router.get("/{prescriber_id}", response_model=PrescriberRead)
async def get_prescriber(
    prescriber_id: int,
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> PrescriberRead:
    prescriber = await PrescriberRepository(session).get(prescriber_id)
    if prescriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prescriber not found"
        )
    return PrescriberRead.model_validate(prescriber)


@router.post("", response_model=PrescriberRead, status_code=status.HTTP_201_CREATED)
async def create_prescriber(
    payload: PrescriberCreate,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PrescriberRead:
    repo = PrescriberRepository(session)
    if payload.npi:
        existing = await repo.get_by_npi(payload.npi)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Prescriber with NPI '{payload.npi}' already exists",
            )
    return PrescriberRead.model_validate(await repo.create(payload))


@router.put("/{prescriber_id}", response_model=PrescriberRead)
async def update_prescriber(
    prescriber_id: int,
    payload: PrescriberCreate,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PrescriberRead:
    repo = PrescriberRepository(session)
    prescriber = await repo.get(prescriber_id)
    if prescriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prescriber not found"
        )
    return PrescriberRead.model_validate(await repo.update(prescriber, payload))


@router.delete("/{prescriber_id}", response_model=PrescriberRead)
async def delete_prescriber(
    prescriber_id: int,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PrescriberRead:
    prescriber = await PrescriberRepository(session).soft_delete(prescriber_id)
    if prescriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prescriber not found"
        )
    return PrescriberRead.model_validate(prescriber)
