"""Receipt History routes for POS transactions and prescription sales."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import Receipt, ReceiptItem, SystemSetting
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/receipts", tags=["receipts"])


class ReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_name: str
    quantity: int
    price_at_time: str
    internal_barcode: str
    vendor: str
    expiry_date: str


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: str
    type: str
    total_amount: str
    payment_method: str
    user_id: Optional[int] = None
    created_at: str
    expires_at: Optional[str] = None
    items: list[ReceiptItemRead] = []


class ReceiptListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: str
    type: str
    total_amount: str
    payment_method: str
    user_id: Optional[int] = None
    created_at: str
    expires_at: Optional[str] = None


class ReceiptsSettingsRead(BaseModel):
    retention_days: Optional[int] = None


class ReceiptsSettingsUpdate(BaseModel):
    retention_days: Optional[int] = None


DEFAULT_RETENTION_DAYS = 365


def _get_retention_days(session: AsyncSession) -> int:
    setting = session.get(SystemSetting, "receipt_retention_days")
    if setting and setting.value:
        try:
            return int(setting.value.decode())
        except (ValueError, UnicodeDecodeError):
            pass
    return DEFAULT_RETENTION_DAYS


def _compute_expires_at(created_at: str, retention_days: Optional[int]) -> Optional[str]:
    if retention_days is None:
        return None
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        expires = dt + timedelta(days=retention_days)
        return expires.isoformat()
    except Exception:
        return None


async def _update_all_expires_at(session: AsyncSession, retention_days: Optional[int]) -> int:
    """Recalculate expires_at for all receipts based on new retention setting."""
    receipts = (await session.execute(select(Receipt))).scalars().all()
    updated = 0
    for r in receipts:
        new_expires = _compute_expires_at(r.timestamp, retention_days)
        if r.expires_at != new_expires:
            r.expires_at = new_expires
            updated += 1
    return updated


@router.get("/settings", response_model=ReceiptsSettingsRead, status_code=status.HTTP_200_OK)
async def get_receipts_settings(
    user: CurrentUser = Depends(require_permission("settings.read")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptsSettingsRead:
    retention = _get_retention_days(session)
    return ReceiptsSettingsRead(retention_days=retention)


@router.put("/settings", response_model=ReceiptsSettingsRead, status_code=status.HTTP_200_OK)
async def update_receipts_settings(
    payload: ReceiptsSettingsUpdate,
    user: CurrentUser = Depends(require_permission("settings.write")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptsSettingsRead:
    retention = payload.retention_days
    setting = await session.get(SystemSetting, "receipt_retention_days")
    if retention is None:
        if setting:
            await session.delete(setting)
    else:
        if setting:
            setting.value = str(retention).encode()
        else:
            session.add(SystemSetting(key="receipt_retention_days", value=str(retention).encode()))
    await session.commit()

    # Recalculate expires_at for all existing receipts (going forward only)
    await _update_all_expires_at(session, retention)

    return ReceiptsSettingsRead(retention_days=retention)


@router.get("", response_model=list[ReceiptListRead], status_code=status.HTTP_200_OK)
async def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    type: Optional[str] = Query(None, pattern="^(pos_sale|prescription|adjustment)$"),
    start_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = Query(None, min_length=1),
    user: CurrentUser = Depends(require_permission("pos.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ReceiptListRead]:
    stmt = select(Receipt)

    if type:
        stmt = stmt.where(Receipt.sale_type == type)
    if start_date:
        stmt = stmt.where(Receipt.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(Receipt.timestamp <= end_date)
    if user_id:
        stmt = stmt.where(Receipt.user_id == user_id)
    if search:
        stmt = stmt.where(Receipt.receipt_number.ilike(f"%{search}%"))

    stmt = stmt.order_by(Receipt.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return [ReceiptListRead.model_validate(r) for r in rows]


@router.get("/{receipt_id}", response_model=ReceiptRead, status_code=status.HTTP_200_OK)
async def get_receipt(
    receipt_id: int,
    user: CurrentUser = Depends(require_permission("pos.read")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptRead:
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    items = (await session.execute(
        select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id)
    )).scalars().all()
    return ReceiptRead(
        **ReceiptRead.model_validate(receipt).model_dump(),
        items=[ReceiptItemRead.model_validate(i) for i in items]
    )


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: int,
    user: CurrentUser = Depends(require_permission("pos.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    await session.delete(receipt)
    await session.commit()


@router.delete("/expired", status_code=status.HTTP_200_OK)
async def delete_expired_receipts(
    user: CurrentUser = Depends(require_permission("pos.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    now = datetime.now(timezone.utc).isoformat()
    stmt = select(Receipt).where(Receipt.expires_at.is_not(None), Receipt.expires_at <= now)
    expired = (await session.execute(stmt)).scalars().all()
    count = len(expired)
    for r in expired:
        await session.delete(r)
    await session.commit()
    return {"deleted": count}


@router.post("/internal/create", status_code=status.HTTP_201_CREATED)
async def create_receipt_internal(
    payload: dict,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Internal endpoint for POS/Dispense modules to create receipt records.
    Expected payload fields:
    - receipt_number, type, total_amount, payment_method, user_id, items (list)
    """
    receipt_number = payload.get("receipt_number") or f"RCP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    sale_type = payload.get("type", "pos_sale")
    total_amount = str(payload.get("total_amount", "0"))
    payment_method = payload.get("payment_method", "Cash")
    user_id = payload.get("user_id")
    items = payload.get("items", [])

    retention = _get_retention_days(session)
    expires_at = _compute_expires_at(datetime.now(timezone.utc).isoformat(), retention)

    receipt = Receipt(
        receipt_number=receipt_number,
        sale_type=sale_type,
        total_amount=total_amount,
        payment_method=payment_method,
        user_id=user_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
    )
    session.add(receipt)
    await session.flush()

    for item in items:
        session.add(ReceiptItem(
            receipt_id=receipt.id,
            product_name=item.get("product_name", ""),
            quantity=item.get("quantity", 0),
            price_at_time=str(item.get("price_at_time", "0")),
            internal_barcode=item.get("internal_barcode", ""),
            vendor=item.get("vendor", ""),
            expiry_date=item.get("expiry_date", ""),
        ))

    await session.commit()
    await session.refresh(receipt)
    return {"id": receipt.id, "receipt_number": receipt_number}


@router.get("/count", status_code=status.HTTP_200_OK)
async def count_receipts(
    type: Optional[str] = Query(None, pattern="^(pos_sale|prescription|adjustment)$"),
    start_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: CurrentUser = Depends(require_permission("pos.read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    stmt = select(func.count(Receipt.id))
    if type:
        stmt = stmt.where(Receipt.sale_type == type)
    if start_date:
        stmt = stmt.where(Receipt.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(Receipt.timestamp <= end_date)
    count = await session.scalar(stmt) or 0
    return {"count": count}