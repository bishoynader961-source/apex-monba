"""Inventory business logic: receiving, FIFO deduction, low-stock + expiry alerts."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import InventoryExtended, Product, SyncInventory
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
from app.shared.schemas import (
    BatchRead,
    BatchUpdate,
    ProductPage,
    ProductRead,
    StockLevelPage,
    StockLevelRead,
)


def today_iso() -> str:
    """Local calendar date as ISO string — the app's expiry-date convention.

    All ``expiration_date`` values are stored as naive local ISO dates, so every
    expiry comparison uses the local calendar (not UTC) to decide sellability
    (audit L7). Single helper so the semantic is defined in exactly one place.
    """
    return date.today().isoformat()


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
        today = today_iso()
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

    async def get_expired_lot(self, product_name: str) -> Optional[str]:
        """Return the expiration date of the first expired lot for a product, or None.

        Mirror of the fifo_deduct sellability predicate (recalled/expired lots are
        never sellable); used by POS checkout to fail loudly when expired stock
        is still on the shelf instead of silently skipping it (D8 critical fix).
        """
        today = today_iso()
        for lot in await BatchRepository(self.session).get_lots_for_product(product_name):
            if lot.expiration_date and lot.expiration_date < today:
                return str(lot.expiration_date)
        return None

    async def return_stock(self, product_name: str, quantity: int) -> None:
        """Restock ``quantity`` of ``product_name`` for a refund (B5).

        Adds back to the oldest lot (preserving FEFO ordering) or creates a generic
        restock lot when none exists, and bumps the hub-authoritative on_hand.
        """
        if quantity <= 0:
            return
        lots = sorted(
            await BatchRepository(self.session).get_lots_for_product(product_name),
            key=lambda l: (l.expiration_date or "", l.id),
        )
        target = lots[0] if lots else None
        if target is None:
            self.session.add(InventoryExtended(drug_name=product_name, on_hand=quantity))
        else:
            target.on_hand += quantity
        await self.session.execute(
            update(SyncInventory)
            .where(SyncInventory.product_name == product_name)
            .values(on_hand=SyncInventory.on_hand + quantity)
        )

    async def low_stock(
        self,
        threshold_override: Optional[int] = None,
        limit: int = 200,
        cursor: Optional[int] = None,
    ) -> ProductPage:
        """Low-stock products, filtered and limited in SQL (audit M9).

        Previously the grouped LEFT JOIN loaded every threshold product and the
        comparison ran in Python. Keyset pagination: pass the previous page's
        ``next_cursor`` back as ``cursor``; at most ``limit`` rows are read.
        """
        total_on_hand = func.coalesce(func.sum(InventoryExtended.on_hand), 0)
        threshold_expr = (
            func.coalesce(Product.reorder_threshold, 0)
            if threshold_override is None
            else threshold_override
        )
        stmt = (
            select(Product)
            .select_from(Product)
            .outerjoin(InventoryExtended, InventoryExtended.drug_name == Product.name)
            .where(Product.reorder_threshold.is_not(None))
            .group_by(Product.id)
            .having(total_on_hand <= threshold_expr)
            .order_by(Product.id.asc())
            .limit(limit + 1)
        )
        if cursor is not None:
            stmt = stmt.where(Product.id > cursor)
        rows = list((await self.session.execute(stmt)).scalars())
        next_cursor: Optional[int] = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = rows[-1].id
        return ProductPage(
            items=[ProductRead.model_validate(p) for p in rows],
            next_cursor=next_cursor,
        )

    async def expiring_soon(self, days: int = 90) -> list[BatchRead]:
        today = today_iso()
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
        self,
        low_stock_only: bool = False,
        expiring_days: int = 90,
        limit: int = 200,
        cursor: Optional[int] = None,
    ) -> StockLevelPage:
        """Aggregate on-hand + reorder + expiring-soon per medicine (audit M9).

        The low-stock filter and LIMIT run in SQL, and the expiring-soon count
        is computed only for the returned page. Keyset pagination ordered by
        ``Product.id``; the previous page's ``next_cursor`` goes back in as
        ``cursor``.
        """
        today = today_iso()
        cutoff = (date.today() + timedelta(days=expiring_days)).isoformat()
        total_on_hand = func.coalesce(func.sum(InventoryExtended.on_hand), 0)
        stmt = (
            select(
                Product.id.label("medicine_id"),
                Product.name.label("name"),
                total_on_hand.label("on_hand"),
                Product.reorder_threshold.label("reorder_threshold"),
            )
            .select_from(Product)
            .outerjoin(InventoryExtended, InventoryExtended.drug_name == Product.name)
            .where(Product.is_deleted == 0)
            .group_by(Product.id, Product.name, Product.reorder_threshold)
            .order_by(Product.id.asc())
            .limit(limit + 1)
        )
        if cursor is not None:
            stmt = stmt.where(Product.id > cursor)
        if low_stock_only:
            stmt = stmt.having(
                Product.reorder_threshold.is_not(None),
                total_on_hand <= Product.reorder_threshold,
            )
        agg_rows = list((await self.session.execute(stmt)).all())
        next_cursor: Optional[int] = None
        if len(agg_rows) > limit:
            agg_rows = agg_rows[:limit]
            next_cursor = int(agg_rows[-1]._mapping["medicine_id"])
        page_names = [str(r._mapping["name"]) for r in agg_rows]
        exp_map: dict[str, int] = {}
        if page_names:
            exp_map = {
                str(r._mapping["name"]): int(r._mapping["n"] or 0)
                for r in (
                    await self.session.execute(
                        select(
                            InventoryExtended.drug_name.label("name"),
                            func.count().label("n"),
                        )
                        .where(
                            InventoryExtended.drug_name.in_(page_names),
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
        return StockLevelPage(items=results, next_cursor=next_cursor)

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

    async def batch_mark_expired(self, batch_ids: list[int]) -> dict[str, object]:
        """Mark multiple batches as expired (on_hand = 0)."""
        from app.core.models import InventoryExtended
        updated = 0
        for batch_id in batch_ids:
            batch = await BatchRepository(self.session).get(batch_id)
            if batch and batch.on_hand > 0:
                batch.on_hand = 0
                updated += 1
        await self.session.commit()
        return {"updated": updated, "total_requested": len(batch_ids)}

    async def batch_adjust_price(self, medicine_ids: list[int], price_change_pct: float) -> dict[str, object]:
        """Adjust price for multiple medicines by percentage.

        Decimal arithmetic with ROUND_HALF_UP cents (audit L1) — float math
        here produced prices like 10.10 * 1.15 -> 11.615000000000002.
        """
        from app.core.models import Product
        from sqlalchemy import select
        updated = 0
        pct = Decimal(str(price_change_pct))
        for med_id in medicine_ids:
            product = await self.session.get(Product, med_id)
            if product:
                current_price = Decimal(str(product.price or 0))
                new_price = (current_price * (1 + pct / 100)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                product.price = float(new_price)
                updated += 1
        await self.session.commit()
        return {"updated": updated, "total_requested": len(medicine_ids), "price_change_pct": price_change_pct}
