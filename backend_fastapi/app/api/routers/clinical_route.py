"""Clinical workflow routes: clinical notes, allergy records, attachments, review."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import AllergyRecord, ClinicalAttachment, ClinicalNote, Patient
from app.shared.schemas import (
    AllergyRecordCreate,
    AllergyRecordRead,
    AllergyRecordUpdate,
    ClinicalAttachmentRead,
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ClinicalNoteUpdate,
    ClinicalReviewSummary,
    CurrentUser,
)

router = APIRouter(prefix="/api/v1/clinical", tags=["clinical"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Clinical Notes ───────────────────────────────────────────────────────────

@router.post("/notes", response_model=ClinicalNoteRead, status_code=status.HTTP_201_CREATED)
async def create_clinical_note(
    payload: ClinicalNoteCreate,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> ClinicalNoteRead:
    patient = await session.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    note = ClinicalNote(
        patient_id=payload.patient_id,
        dispense_id=payload.dispense_id,
        content=payload.content,
        category=payload.category,
        created_by=user.id,
        created_at=_now(),
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.get("/notes", response_model=list[ClinicalNoteRead])
async def list_clinical_notes(
    patient_id: int,
    category: str | None = None,
    limit: int = 50,
    user: CurrentUser = Depends(require_permission("dispense.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ClinicalNoteRead]:
    stmt = select(ClinicalNote).where(ClinicalNote.patient_id == patient_id)
    if category:
        stmt = stmt.where(ClinicalNote.category == category)
    stmt = stmt.order_by(ClinicalNote.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.put("/notes/{note_id}", response_model=ClinicalNoteRead)
async def update_clinical_note(
    note_id: int,
    payload: ClinicalNoteUpdate,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> ClinicalNoteRead:
    note = await session.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found")
    if payload.content is not None:
        note.content = payload.content
    if payload.category is not None:
        note.category = payload.category
    note.updated_at = _now()
    await session.commit()
    await session.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clinical_note(
    note_id: int,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    note = await session.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found")
    await session.delete(note)


# ── Allergy Records ──────────────────────────────────────────────────────────

@router.post("/allergies", response_model=AllergyRecordRead, status_code=status.HTTP_201_CREATED)
async def create_allergy_record(
    payload: AllergyRecordCreate,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> AllergyRecordRead:
    patient = await session.get(Patient, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    record = AllergyRecord(
        patient_id=payload.patient_id,
        drug_name=payload.drug_name,
        reaction=payload.reaction,
        severity=payload.severity,
        recorded_by=user.id,
        created_at=_now(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.get("/allergies", response_model=list[AllergyRecordRead])
async def list_allergy_records(
    patient_id: int,
    user: CurrentUser = Depends(require_permission("dispense.read")),
    session: AsyncSession = Depends(get_session),
) -> list[AllergyRecordRead]:
    stmt = (
        select(AllergyRecord)
        .where(AllergyRecord.patient_id == patient_id)
        .order_by(AllergyRecord.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.put("/allergies/{record_id}", response_model=AllergyRecordRead)
async def update_allergy_record(
    record_id: int,
    payload: AllergyRecordUpdate,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> AllergyRecordRead:
    record = await session.get(AllergyRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Allergy record not found")
    if payload.drug_name is not None:
        record.drug_name = payload.drug_name
    if payload.reaction is not None:
        record.reaction = payload.reaction
    if payload.severity is not None:
        record.severity = payload.severity
    record.updated_at = _now()
    await session.commit()
    await session.refresh(record)
    return record


@router.delete("/allergies/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allergy_record(
    record_id: int,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await session.get(AllergyRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Allergy record not found")
    await session.delete(record)


# ── Attachments (metadata only — file upload handled separately) ─────────────

@router.get("/attachments", response_model=list[ClinicalAttachmentRead])
async def list_attachments(
    patient_id: int,
    user: CurrentUser = Depends(require_permission("dispense.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ClinicalAttachmentRead]:
    stmt = (
        select(ClinicalAttachment)
        .where(ClinicalAttachment.patient_id == patient_id)
        .order_by(ClinicalAttachment.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: int,
    user: CurrentUser = Depends(require_permission("dispense.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    att = await session.get(ClinicalAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await session.delete(att)


# ── Review Summary ───────────────────────────────────────────────────────────

@router.get("/review/{patient_id}", response_model=ClinicalReviewSummary)
async def get_clinical_review(
    patient_id: int,
    user: CurrentUser = Depends(require_permission("dispense.read")),
    session: AsyncSession = Depends(get_session),
) -> ClinicalReviewSummary:
    patient = await session.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    allergy_stmt = (
        select(AllergyRecord)
        .where(AllergyRecord.patient_id == patient_id)
        .order_by(AllergyRecord.created_at.desc())
    )
    allergies = list((await session.execute(allergy_stmt)).scalars().all())

    notes_stmt = (
        select(ClinicalNote)
        .where(ClinicalNote.patient_id == patient_id)
        .order_by(ClinicalNote.created_at.desc())
        .limit(20)
    )
    notes = list((await session.execute(notes_stmt)).scalars().all())

    return ClinicalReviewSummary(
        patient_id=patient_id,
        patient_name=patient.name,
        allergies=allergies,
        recent_notes=notes,
        active_prescriptions=0,
        pending_refills=0,
    )
