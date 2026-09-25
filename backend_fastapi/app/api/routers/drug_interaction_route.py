"""Drug Interaction routes: check + CRUD."""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.drug_interaction_service import DrugInteractionService
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/drug-interactions", tags=["drug-interactions"])


class InteractionCheckRequest(BaseModel):
    drug_names: list[str] = Field(min_length=1)


class InteractionResultRead(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    description: str
    recommendation: str


class InteractionCreateRequest(BaseModel):
    drug_a: str = Field(min_length=1)
    drug_b: str = Field(min_length=1)
    severity: str = "moderate"
    description: str = ""
    recommendation: str = ""


class InteractionUpdateRequest(BaseModel):
    severity: str | None = None
    description: str | None = None
    recommendation: str | None = None
    is_active: int | None = None


class InteractionRead(BaseModel):
    id: int
    drug_a: str
    drug_b: str
    severity: str
    description: str
    recommendation: str
    is_active: int


@router.post("/check", response_model=list[InteractionResultRead], status_code=status.HTTP_200_OK)
async def check_interactions(
    payload: InteractionCheckRequest,
    session: AsyncSession = Depends(get_session),
) -> list[InteractionResultRead]:
    svc = DrugInteractionService(session)
    results = await svc.check_interactions(payload.drug_names)
    return [InteractionResultRead(
        drug_a=r.drug_a, drug_b=r.drug_b, severity=r.severity,
        description=r.description, recommendation=r.recommendation,
    ) for r in results]


@router.get("/", response_model=list[InteractionRead], status_code=status.HTTP_200_OK)
async def list_interactions(
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> list[InteractionRead]:
    rows = await DrugInteractionService(session).list_interactions()
    return [InteractionRead.model_validate(r) for r in rows]


@router.post("/", response_model=InteractionRead, status_code=status.HTTP_201_CREATED)
async def create_interaction(
    payload: InteractionCreateRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> InteractionRead:
    svc = DrugInteractionService(session)
    ix = await svc.create_interaction(payload.drug_a, payload.drug_b, payload.severity, payload.description, payload.recommendation)
    return InteractionRead.model_validate(ix)


@router.put("/{interaction_id}", response_model=InteractionRead, status_code=status.HTTP_200_OK)
async def update_interaction(
    interaction_id: int,
    payload: InteractionUpdateRequest,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> InteractionRead:
    svc = DrugInteractionService(session)
    ix = await svc.update_interaction(interaction_id, payload.severity, payload.description, payload.recommendation, payload.is_active)
    return InteractionRead.model_validate(ix)


@router.delete("/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interaction(
    interaction_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    await DrugInteractionService(session).delete_interaction(interaction_id)
