"""Patient custom fields (EAV) endpoints for site-specific patient attributes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.models import PatientField

router = APIRouter(prefix="/api/v1/patients", tags=["patients-fields"])


class PatientFieldCreate(BaseModel):
    patient_id: int
    field_name: str
    field_value: str | None = None


class PatientFieldUpdate(BaseModel):
    field_value: str | None = None


class PatientFieldRead(BaseModel):
    id: int
    patient_id: int
    field_name: str
    field_value: str | None

    class Config:
        from_attributes = True


@router.get("/{patient_id}/fields", response_model=list[PatientFieldRead])
async def list_patient_fields(patient_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(PatientField).where(PatientField.patient_id == patient_id)
    )
    return result.scalars().all()


@router.post("/{patient_id}/fields", response_model=PatientFieldRead)
async def upsert_patient_field(patient_id: int, body: PatientFieldCreate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(PatientField).where(
            PatientField.patient_id == patient_id,
            PatientField.field_name == body.field_name,
        )
    )
    field = result.scalar_one_or_none()
    if field:
        field.field_value = body.field_value
    else:
        field = PatientField(
            patient_id=patient_id,
            field_name=body.field_name,
            field_value=body.field_value,
        )
        db.add(field)
    await db.commit()
    await db.refresh(field)
    return field


@router.delete("/{patient_id}/fields/{field_name}")
async def delete_patient_field(patient_id: int, field_name: str, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(PatientField).where(
            PatientField.patient_id == patient_id,
            PatientField.field_name == field_name,
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    await db.delete(field)
    await db.commit()
    return {"ok": True}
