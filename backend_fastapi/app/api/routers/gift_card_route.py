"""Gift card issue, redeem, void, and lookup endpoints."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import GiftCard
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/gift-cards", tags=["gift-cards"])


class GiftCardCreate(BaseModel):
    initial_balance: float
    issued_to_patient_id: int | None = None
    note: str | None = None


class GiftCardRedeem(BaseModel):
    amount: float


class GiftCardRead(BaseModel):
    id: int
    code: str
    initial_balance: float
    current_balance: float
    status: str
    issued_to_patient_id: int | None
    issued_by_user_id: int | None
    issued_at: str | None
    redeemed_at: str | None
    voided_at: str | None
    note: str | None

    class Config:
        from_attributes = True


def _generate_code() -> str:
    return f"GC-{secrets.token_hex(4).upper()}"


@router.post("", response_model=GiftCardRead)
async def issue_gift_card(
    body: GiftCardCreate,
    user: CurrentUser = Depends(require_permission("pos.write")),
    db: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc).isoformat()
    card = GiftCard(
        code=_generate_code(),
        initial_balance=Decimal(str(body.initial_balance)),
        current_balance=Decimal(str(body.initial_balance)),
        status="active",
        issued_to_patient_id=body.issued_to_patient_id,
        issued_at=now,
        note=body.note,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.get("", response_model=list[GiftCardRead])
async def list_gift_cards(
    status: str | None = None,
    user: CurrentUser = Depends(require_permission("giftCards.read")),
    db: AsyncSession = Depends(get_session),
):
    q = select(GiftCard)
    if status:
        q = q.where(GiftCard.status == status)
    q = q.order_by(GiftCard.id.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/lookup/{code}", response_model=GiftCardRead)
async def lookup_gift_card(
    code: str,
    user: CurrentUser = Depends(require_permission("giftCards.read")),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(GiftCard).where(GiftCard.code == code))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return card


@router.post("/{card_id}/redeem", response_model=GiftCardRead)
async def redeem_gift_card(
    card_id: int,
    body: GiftCardRedeem,
    user: CurrentUser = Depends(require_permission("pos.write")),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(GiftCard).where(GiftCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    if card.status != "active":
        raise HTTPException(status_code=400, detail=f"Gift card is {card.status}")
    if card.current_balance < Decimal(str(body.amount)):
        raise HTTPException(status_code=400, detail="Insufficient balance")
    card.current_balance -= Decimal(str(body.amount))
    if card.current_balance == 0:
        card.status = "redeemed"
        card.redeemed_at = datetime.now(timezone.utc).isoformat()
    await db.commit()
    await db.refresh(card)
    return card


@router.post("/{card_id}/void", response_model=GiftCardRead)
async def void_gift_card(
    card_id: int,
    user: CurrentUser = Depends(require_permission("pos.write")),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(GiftCard).where(GiftCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    if card.status == "void":
        raise HTTPException(status_code=400, detail="Gift card is already void")
    card.status = "void"
    card.current_balance = Decimal("0")
    card.voided_at = datetime.now(timezone.utc).isoformat()
    await db.commit()
    await db.refresh(card)
    return card
