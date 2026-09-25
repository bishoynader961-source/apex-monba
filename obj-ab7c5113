"""Label Assignment routes for print preview / bulk label printing."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.label_template_service import LabelAssignmentService
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/label-assignments", tags=["label-assignments"])


class LabelAssignmentCreate(BaseModel):
    medicine_id: int
    quantity: int = 1
    label_template_id: Optional[int] = None
    canvas_width: Optional[int] = None
    canvas_height: Optional[int] = None
    elements: Optional[list[dict]] = None


class LabelAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    medicine_id: int
    quantity: int
    label_template_id: Optional[int] = None
    canvas_width: Optional[int] = None
    canvas_height: Optional[int] = None
    elements: Optional[list[dict]] = None
    created_at: Optional[str] = None
    created_by: Optional[int] = None


@router.post("", response_model=LabelAssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_label_assignment(
    payload: LabelAssignmentCreate,
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> LabelAssignmentRead:
    async with session.begin():
        svc = LabelAssignmentService(session)
        assignment = await svc.create_assignment(
            medicine_id=payload.medicine_id,
            quantity=payload.quantity,
            label_template_id=payload.label_template_id,
            canvas_width=payload.canvas_width,
            canvas_height=payload.canvas_height,
            elements=payload.elements,
            created_by=user.id,
        )
        return LabelAssignmentRead(**assignment)


@router.get("", response_model=list[LabelAssignmentRead], status_code=status.HTTP_200_OK)
async def list_label_assignments(
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[LabelAssignmentRead]:
    svc = LabelAssignmentService(session)
    assignments = await svc.list_assignments()
    return [LabelAssignmentRead(**a) for a in assignments]


@router.get("/{assignment_id}", response_model=LabelAssignmentRead, status_code=status.HTTP_200_OK)
async def get_label_assignment(
    assignment_id: int,
    user: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> LabelAssignmentRead:
    svc = LabelAssignmentService(session)
    assignment = await svc.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label assignment not found")
    return LabelAssignmentRead(**assignment)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label_assignment(
    assignment_id: int,
    user: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    async with session.begin():
        svc = LabelAssignmentService(session)
        deleted = await svc.delete_assignment(assignment_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label assignment not found")