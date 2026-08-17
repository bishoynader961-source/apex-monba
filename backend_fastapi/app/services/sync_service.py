"""Multi-terminal merge-sync hub (C.1).

The hub is the single authoritative writer of stock across terminals. It ingests
each terminal's committed sales (FIFO by ``local_seq``), dedups globally on
``client_txn_id`` (exact-once), and applies additive stock deductions to the
hub ``sync_inventory``. A deduction that would drive ``on_hand`` below zero is a
true cross-terminal over-sell — it is **recorded but flagged** (never
auto-merged) so a manager can reconcile against the physical count.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Discrepancy, SyncOutbox
from app.core.repositories import SyncRepository
from app.shared.exceptions import NotFoundError, ValidationError
from app.shared.schemas import SyncPushEntry, SyncPushResult, DiscrepancyRead

_OVER_SELL_REASON = "OVER_SOLD_CROSS_TERMINAL"


class SyncService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def push(self, entries: list[SyncPushEntry]) -> SyncPushResult:
        repo = SyncRepository(self.session)
        accepted = deduped = over_sells = 0
        merge_seq = await repo.max_merge_seq()

        # Process in (device_id, local_seq) order so the global replay is stable
        # even when many terminals push in one batch.
        ordered = sorted(entries, key=lambda e: (e.device_id, e.local_seq))
        for e in ordered:
            if await repo.find_by_client_txn_id(e.client_txn_id) is not None:
                deduped += 1  # exact-once: same sale already merged
                continue
            merge_seq += 1
            await repo.insert_merged(
                e.device_id, e.local_seq, e.client_txn_id, json.dumps(e.payload), merge_seq
            )
            accepted += 1
            if await self._apply_deltas(repo, e.payload):
                over_sells += 1
                await repo.insert_discrepancy(
                    _OVER_SELL_REASON,
                    e.device_id,
                    e.local_seq,
                    e.client_txn_id,
                    f"over-sell detected while applying {e.client_txn_id}",
                )
        await self.session.commit()
        return SyncPushResult(
            accepted=accepted, deduped=deduped, over_sells=over_sells, merge_seq_max=merge_seq
        )

    async def _apply_deltas(self, repo: SyncRepository, payload: Any) -> bool:
        """Apply additive stock deductions. Returns True if any over-sell occurred."""
        items = (payload or {}).get("items") or []
        over = False
        for item in items:
            name = item.get("product_name")
            qty = int(item.get("quantity", 0) or 0)
            if not name or qty <= 0:
                continue
            on_hand = await repo.get_on_hand(name)
            if on_hand is None:
                on_hand = 0
            if on_hand < qty:
                over = True
                await repo.set_on_hand(name, 0)  # clamp; physical cannot go negative
            else:
                await repo.set_on_hand(name, on_hand - qty)
        return over

    async def list_discrepancies(self, unresolved_only: bool = True) -> list[DiscrepancyRead]:
        """Persisted discrepancies surfaced for manager review (A4)."""
        repo = SyncRepository(self.session)
        rows = await repo.get_discrepancies(unresolved_only)
        return [DiscrepancyRead.model_validate(d) for d in rows]

    async def resolve_discrepancy(self, discrepancy_id: int) -> DiscrepancyRead:
        repo = SyncRepository(self.session)
        disc = await repo.resolve_discrepancy(discrepancy_id)
        if disc is None:
            raise NotFoundError("Discrepancy", discrepancy_id)
        return DiscrepancyRead.model_validate(disc)
