"""Patient profile routes: CRUD, insurance binding, members, dispenses, history (F4)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import DispenseRepository
from app.services.dispense_service import DispenseService
from app.services.patient_service import PatientService
from app.shared.schemas import (
    DispenseRead,
    InsuranceBindRequest,
    PaginatedPatients,
    PatientCreate,
    PatientHistoryEntry,
    PatientRead,
    PatientUpdate,
)

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("", response_model=PaginatedPatients)
async def list_patients(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(default=None),
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> PaginatedPatients:
    service = PatientService(session)
    items, total = await service.list_patients(page=page, page_size=page_size, q=q)
    return PaginatedPatients(items=items, total=total, page=page, page_size=page_size)


@router.get("/search", response_model=List[PatientRead])
async def search_patients(
    q: str = Query(..., min_length=1),
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> List[PatientRead]:
    return await PatientService(session).search(q)


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(
    patient_id: int,
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> PatientRead:
    return await PatientService(session).get(patient_id)


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PatientRead:
    return await PatientService(session).create(payload)


@router.put("/{patient_id}", response_model=PatientRead)
async def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PatientRead:
    return await PatientService(session).update(patient_id, payload)


@router.post("/{patient_id}/insurance", response_model=PatientRead)
async def bind_patient_insurance(
    patient_id: int,
    payload: InsuranceBindRequest,
    _auth: object = Depends(require_permission("patients.write")),
    session: AsyncSession = Depends(get_session),
) -> PatientRead:
    return await PatientService(session).bind_insurance(patient_id, payload.plan_id)


@router.delete("/{patient_id}", response_model=PatientRead)
async def delete_patient(
    patient_id: int,
    _auth: object = Depends(require_permission("patients.delete")),
    session: AsyncSession = Depends(get_session),
) -> PatientRead:
    return await PatientService(session).soft_delete(patient_id)


@router.get("/{patient_id}/dispenses", response_model=List[DispenseRead])
async def list_patient_dispenses(
    patient_id: int,
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> List[DispenseRead]:
    # Validate the patient exists (404 if soft-deleted) before listing dependents.
    await PatientService(session).get(patient_id)
    dispenses = await DispenseRepository(session).for_patient(patient_id)
    service = DispenseService(session)
    return [await service.get(d.id) for d in dispenses]


@router.get("/{patient_id}/history", response_model=List[PatientHistoryEntry])
async def patient_history(
    patient_id: int,
    limit: int = Query(100, ge=1, le=500),
    _auth: object = Depends(require_permission("patients.read")),
    session: AsyncSession = Depends(get_session),
) -> List[PatientHistoryEntry]:
    return await PatientService(session).history(patient_id, limit=limit)
