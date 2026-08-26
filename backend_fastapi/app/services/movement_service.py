"""Movement History service: shapes the unified stock ledger for the API layer."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import InventoryMovementRepository
from app.shared.schemas import MovementLogItem, MovementLogResponse


class MovementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_movements(
        self,
        *,
        product_id: Optional[int] = None,
        batch_number: Optional[str] = None,
        movement_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> MovementLogResponse:
        rows, total = await InventoryMovementRepository(self.session).list_movements(
            product_id=product_id,
            batch_number=batch_number,
            movement_type=movement_type,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
        start = (max(1, page) - 1) * page_size
        items: list[MovementLogItem] = []
        for i, row in enumerate(rows):
            items.append(
                MovementLogItem(
                    id=start + i + 1,
                    timestamp=str(row["ts"]),
                    product_id=int(row["product_id"]) if row.get("product_id") else None,
                    product_name=str(row.get("product_name", "")),
                    ndc_code=str(row["ndc_code"]) if row.get("ndc_code") else None,
                    batch_number=str(row.get("batch_number") or ""),
                    movement_type=str(row.get("movement_type", "")),
                    quantity_change=int(row.get("quantity_change") or 0),
                    remaining_stock_snapshot=(
                        int(row["remaining_stock_snapshot"])
                        if row.get("remaining_stock_snapshot")
                        else None
                    ),
                    reference_id=int(row["reference_id"]) if row.get("reference_id") else None,
                    user_name=str(row["user_name"]) if row.get("user_name") else None,
                )
            )
        return MovementLogResponse(
            items=items, total=total, page=page, page_size=page_size
        )
