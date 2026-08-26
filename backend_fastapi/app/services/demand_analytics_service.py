"""Demand Analytics service: item velocity, revenue, and reorder intelligence."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import DemandAnalyticsRepository
from app.shared.schemas import DemandAnalyticsItem, DemandAnalyticsSummary

_TWO_DP = Decimal("0.01")


class DemandAnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compute(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: Optional[str] = None,
        min_sales: Optional[int] = None,
        sort_by: str = "total_quantity",
        lead_time_days: int = 7,
    ) -> DemandAnalyticsSummary:
        if end_date is None:
            end_date = date.today().isoformat()
        if start_date is None:
            start_date = (date.today() - timedelta(days=30)).isoformat()

        rows = await DemandAnalyticsRepository(self.session).demand_aggregates(
            start_date, end_date, category
        )
        days = max(
            1,
            (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
            + 1,
        )

        raw: list[dict[str, Any]] = []
        for r in rows:
            pos_units = int(r["pos_units"] or 0)
            dispense_units = int(r["dispense_units"] or 0)
            total_qty = pos_units + dispense_units
            total_rev = (
                Decimal(str(r["pos_rev"] or 0)) + Decimal(str(r["dispense_rev"] or 0))
            ).quantize(_TWO_DP)
            unit_price = Decimal(str(r["unit_price"] or 0)).quantize(_TWO_DP)
            on_hand = int(r["current_on_hand"] or 0)
            avg_daily = round(total_qty / days, 2)
            reorder = round(avg_daily * lead_time_days - on_hand, 2)
            raw.append(
                {
                    "product_id": r["product_id"],
                    "product_name": r["product_name"],
                    "ndc_code": r["ndc_code"],
                    "unit_price": unit_price,
                    "total_qty": total_qty,
                    "total_rev": total_rev,
                    "avg_daily": avg_daily,
                    "on_hand": on_hand,
                    "reorder": reorder,
                }
            )

        if min_sales is not None:
            raw = [x for x in raw if x["total_qty"] >= min_sales]

        # Velocity classification: top 20% = FAST, middle 50% = MODERATE,
        # remainder of movers = SLOW, zero demand = NON_MOVING.
        non_zero = sorted(
            [x for x in raw if x["total_qty"] > 0],
            key=lambda x: x["total_qty"],
            reverse=True,
        )
        n = len(non_zero)
        fast_cut = math.ceil(0.2 * n)
        mod_cut = fast_cut + math.floor(0.5 * n)
        for idx, x in enumerate(non_zero):
            if idx < fast_cut:
                x["velocity"] = "FAST_MOVING"
            elif idx < mod_cut:
                x["velocity"] = "MODERATE_MOVING"
            else:
                x["velocity"] = "SLOW_MOVING"
        for x in raw:
            if x["total_qty"] == 0:
                x["velocity"] = "NON_MOVING"

        items = [
            DemandAnalyticsItem(
                product_id=x["product_id"],
                product_name=x["product_name"],
                ndc_code=x["ndc_code"],
                unit_price=x["unit_price"],
                total_quantity_demanded=x["total_qty"],
                total_revenue=x["total_rev"],
                avg_daily_consumption=x["avg_daily"],
                velocity_category=x["velocity"],
                reorder_suggestion=x["reorder"],
                current_on_hand_stock=x["on_hand"],
            )
            for x in raw
        ]

        key_map = {
            "total_quantity": lambda it: it.total_quantity_demanded,
            "total_revenue": lambda it: it.total_revenue,
            "avg_daily_consumption": lambda it: it.avg_daily_consumption,
        }
        items.sort(key=key_map.get(sort_by, key_map["total_quantity"]), reverse=True)

        total_items = sum(it.total_quantity_demanded for it in items)
        total_rev = sum((it.total_revenue for it in items), Decimal("0")).quantize(_TWO_DP)
        top = max(items, key=lambda it: it.total_quantity_demanded) if items else None
        slow_count = sum(
            1 for it in items if it.velocity_category in ("SLOW_MOVING", "NON_MOVING")
        )
        return DemandAnalyticsSummary(
            window_start=start_date,
            window_end=end_date,
            total_items_sold_dispensed=total_items,
            total_revenue=total_rev,
            top_demanded_product=top.product_name if top else None,
            slow_non_moving_count=slow_count,
            items=items,
        )
