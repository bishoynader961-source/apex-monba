"""Inventory business logic: receiving, FIFO deduction, low-stock + expiry alerts."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import InventoryExtended, Product
from app.core.repositories import BatchRepository
from app.core.lock_manager import acquire_drug_lock
from app.shared.exceptions import (
    ExpiredLotError,
    InsufficientStockError,
    MissingLotError,
    NotFoundError,
    OverSellError,
    RecalledLotError,
    ValidationError,
)
from app.shared.schemas import BatchRead, BatchUpdate, ProductRead, StockLevelRead


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def receive_batch(
        self,
        product_name: str,
        lot_number: str,
        expiry_date: str,
        quantity: int,
        unit_cost: float,
        supplier: str,
        ndc_code: Optional[str] = None,
    ) -> BatchRead:
        batch = await BatchRepository(self.session).receive(
            product_name, lot_number, expiry_date, quantity, unit_cost, supplier, ndc_code
        )
        return BatchRead.model_validate(batch)

    async def fifo_deduct(self, product_name: str, quantity: int) -> list[dict[str, object]]:
        """Deduct oldest-expiry, sellable lots first (FEFO). Caller owns the txn.

        Lots that are **recalled** or **expired** today are never sold; if the
        remaining sellable stock cannot cover ``quantity`` we raise a typed
        ``StockStateError`` (HTTP 410) so the client parks the line instead of
        busy-retrying:

          * recalled lot present  -> ``RecalledLotError``
          * expired lot present    -> ``ExpiredLotError``
          * no sellable stock      -> ``MissingLotError``
          * sellable but short     -> ``OverSellError``

        Returns the list of consumed lot snapshots for audit/receipt lines.
        """
        repo = BatchRepository(self.session)
        lots = sorted(
            await repo.get_lots_for_product(product_name),
            key=lambda l: (l.expiration_date or "", l.id),
        )
        today = date.today().isoformat()
        recalled_present = any(bool(l.recalled) for l in lots)
        expired_present = any(
            l.expiration_date and l.expiration_date < today for l in lots
        )
        sellable = [
            l
            for l in lots
            if not l.recalled and not (l.expiration_date and l.expiration_date < today)
        ]
        available = sum(lot.on_hand for lot in sellable)
        if available < quantity:
            if recalled_present and not expired_present:
                recalled_lot = next(l for l in lots if l.recalled)
                raise RecalledLotError(product_name, str(recalled_lot.lot_number))
            if expired_present:
                expired_lot = next(
                    l for l in lots if l.expiration_date and l.expiration_date < today
                )
                raise ExpiredLotError(
                    product_name, str(expired_lot.lot_number), str(expired_lot.expiration_date)
                )
            if available == 0:
                raise MissingLotError(product_name)
            raise OverSellError(product_name, available, quantity)

        consumed: list[dict[str, object]] = []
        remaining = quantity
        for lot in sellable:
            if remaining <= 0:
                break
            take = min(lot.on_hand, remaining)
            lot.on_hand -= take
            consumed.append(
                {
                    "lot_id": lot.id,
                    "lot_number": lot.lot_number,
                    "deducted": take,
                    "expiry_date": lot.expiration_date,
                }
            )
            remaining -= take
        return consumed

    async def low_stock(self, threshold_override: Optional[int] = None) -> list[ProductRead]:
        repo = BatchRepository(self.session)
        products = (await self.session.execute(
            select(Product).where(Product.reorder_threshold.is_not(None))
        )).scalars().all()
        result: list[ProductRead] = []
        for product in products:
            on_hand = await repo.sum_on_hand(product.name)
            threshold = threshold_override if threshold_override is not None else (
                product.reorder_threshold or 0
            )
            if on_hand <= threshold:
                result.append(ProductRead.model_validate(product))
        return result

    async def expiring_soon(self, days: int = 90) -> list[BatchRead]:
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=days)).isoformat()
        rows = (
            await self.session.execute(
                select(InventoryExtended)
                .where(
                    InventoryExtended.expiration_date <= cutoff,
                    InventoryExtended.expiration_date >= today,
                    InventoryExtended.on_hand > 0,
                )
                .order_by(InventoryExtended.expiration_date)
            )
        ).scalars().all()
        return [BatchRead.model_validate(row) for row in rows]

    async def stock_levels(
        self, low_stock_only: bool = False, expiring_days: int = 90
    ) -> list[StockLevelRead]:
        """Aggregate on-hand + reorder + expiring-soon per medicine (LEFT JOIN, no N+1)."""
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=expiring_days)).isoformat()
        agg_rows = (
            await self.session.execute(
                select(
                    Product.id.label("medicine_id"),
                    Product.name.label("name"),
                    func.coalesce(func.sum(InventoryExtended.on_hand), 0).label("on_hand"),
                    Product.reorder_threshold.label("reorder_threshold"),
                )
                .select_from(Product)
                .outerjoin(InventoryExtended, InventoryExtended.drug_name == Product.name)
                .where(Product.is_deleted == 0)
                .group_by(Product.id, Product.name, Product.reorder_threshold)
                .order_by(func.coalesce(func.sum(InventoryExtended.on_hand), 0).asc())
            )
        ).all()
        exp_map = {
            str(r._mapping["name"]): int(r._mapping["n"] or 0)
            for r in (
                await self.session.execute(
                    select(
                        InventoryExtended.drug_name.label("name"),
                        func.count().label("n"),
                    )
                    .where(
                        InventoryExtended.drug_name.is_not(None),
                        InventoryExtended.expiration_date >= today,
                        InventoryExtended.expiration_date <= cutoff,
                        InventoryExtended.on_hand > 0,
                    )
                    .group_by(InventoryExtended.drug_name)
                )
            ).all()
        }
        results: list[StockLevelRead] = []
        for r in agg_rows:
            m = r._mapping
            total = int(m["on_hand"] or 0)
            threshold = m["reorder_threshold"]
            is_low = threshold is not None and total <= threshold
            if low_stock_only and not is_low:
                continue
            results.append(
                StockLevelRead(
                    medicine_id=int(m["medicine_id"]),
                    name=m["name"],
                    total_on_hand=total,
                    reorder_threshold=threshold,
                    is_low_stock=is_low,
                    expiring_soon_count=exp_map.get(m["name"], 0),
                )
            )
        return results

    async def get_batch(self, batch_id: int) -> BatchRead:
        batch = await BatchRepository(self.session).get(batch_id)
        if batch is None:
            raise NotFoundError("Batch", batch_id)
        return BatchRead.model_validate(batch)

    async def adjust_batch(self, batch_id: int, data: BatchUpdate) -> BatchRead:
        if data.on_hand is not None and data.on_hand < 0:
            raise ValidationError(
                "Batch.on_hand cannot be negative", details={"on_hand": data.on_hand}
            )
        repo = BatchRepository(self.session)
        batch = await repo.get(batch_id)
        if batch is None:
            raise NotFoundError("Batch", batch_id)
        lock_name = batch.drug_name or f"lot:{batch.id}"
        # Acquire the per-drug lock so this RMW cannot interleave with a concurrent
        # FIFO checkout (same registry PosService.process_checkout uses).
        # repo.adjust performs the commit; the lock alone serialises against checkout.
        async with acquire_drug_lock(lock_name):
            batch = await repo.adjust(batch, data)
        return BatchRead.model_validate(batch)
