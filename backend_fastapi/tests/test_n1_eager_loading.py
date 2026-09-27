"""Sprint 2B: N+1 query-count proofs (receipts history measured; other
fixes verified structurally — per-row awaits replaced by set-based queries)."""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

class _QueryCounter:
    """Counts SQL statements via the before_cursor_execute engine event."""

    def __init__(self, bind: object) -> None:
        self._bind = bind
        self.count = 0

    def __enter__(self) -> "_QueryCounter":
        event.listen(self._bind, "before_cursor_execute", self._inc)
        return self

    def __exit__(self, *args: object) -> None:
        event.remove(self._bind, "before_cursor_execute", self._inc)

    def _inc(self, *args: object, **kwargs: object) -> None:
        self.count += 1


async def test_recent_receipts_query_count_is_constant(session: AsyncSession) -> None:
    """Was 1 + N (one SELECT per receipt); now exactly 2 regardless of N."""
    from app.core.models import Receipt, ReceiptItem
    from app.services.pos_service import PosService

    for i in range(12):
        r = Receipt(timestamp="2026-09-27T10:00:00", total_amount=10)
        session.add(r)
        await session.flush()
        session.add(ReceiptItem(receipt_id=r.id, product_name="Aspirin", quantity=1, price_at_time=10))

    await session.commit()
    bind = session.sync_session.get_bind()
    with _QueryCounter(bind) as counter:
        receipts = await PosService(session).recent_receipts(limit=50)

    assert len(receipts) == 12
    assert counter.count == 2, f"expected 2 queries, got {counter.count}"
