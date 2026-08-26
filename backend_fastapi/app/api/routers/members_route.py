"""Members / dependents routes: CRUD, filtered by patient (F4 Members Group tab)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import MembersGroupRepository
from app.shared.schemas import (
    MembersGroupCreate,
    MembersGroupRead,
    MembersGroupUpdate,
)

router = APIRouter(prefix="/api/v1/members-groups", tags=["members"])


@router.get("", response_model=List[MembersGroupRead])
async def list_members(
    patient_id: Optional[int] = Query(default=None, ge=1),
    _auth: object = Depends(require_permission("members.read")),
    session: AsyncSession = Depends(get_session),
) -> List[MembersGroupRead]:
    repo = MembersGroupRepository(session)
    if patient_id is None:
        members = await repo.all()
    else:
        members = await repo.for_patient(patient_id)
    return [MembersGroupRead.model_validate(m) for m in members]


@router.get("/{member_id}", response_model=MembersGroupRead)
async def get_member(
    member_id: int,
    _auth: object = Depends(require_permission("members.read")),
    session: AsyncSession = Depends(get_session),
) -> MembersGroupRead:
    member = await MembersGroupRepository(session).get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return MembersGroupRead.model_validate(member)


@router.post("", response_model=MembersGroupRead, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: MembersGroupCreate,
    _auth: object = Depends(require_permission("members.write")),
    session: AsyncSession = Depends(get_session),
) -> MembersGroupRead:
    member = await MembersGroupRepository(session).create(payload)
    return MembersGroupRead.model_validate(member)


@router.put("/{member_id}", response_model=MembersGroupRead)
async def update_member(
    member_id: int,
    payload: MembersGroupUpdate,
    _auth: object = Depends(require_permission("members.write")),
    session: AsyncSession = Depends(get_session),
) -> MembersGroupRead:
    repo = MembersGroupRepository(session)
    member = await repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    member = await repo.update(member, payload)
    return MembersGroupRead.model_validate(member)


@router.delete("/{member_id}", response_model=MembersGroupRead)
async def delete_member(
    member_id: int,
    _auth: object = Depends(require_permission("members.write")),
    session: AsyncSession = Depends(get_session),
) -> MembersGroupRead:
    repo = MembersGroupRepository(session)
    member = await repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    deleted = await repo.delete(member_id)
    return MembersGroupRead.model_validate(deleted)
