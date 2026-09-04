"""Demand Analytics routes: item velocity, revenue, and reorder intelligence."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.demand_analytics_service import DemandAnalyticsService
from app.shared.schemas import (
    CurrentUser,
    DemandAnalyticsSummary,
    TopSellingItem,
    TopSellingResponse,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/demand", response_model=DemandAnalyticsSummary)
async def demand_analytics(
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    category: Optional[str] = Query(default=None, min_length=1),
    min_sales: Optional[int] = Query(default=None, ge=0),
    sort_by: str = Query("total_quantity", pattern="^(total_quantity|total_revenue|avg_daily_consumption)$"),
    lead_time_days: int = Query(7, ge=0),
    _auth: CurrentUser = Depends(require_permission("analytics.read")),
    session: AsyncSession = Depends(get_session),
) -> DemandAnalyticsSummary:
    """Per-item consumption velocity + revenue over a date window.

    ``total_quantity_demanded`` = POS sold units + clinical dispense units.
    Items are classified FAST/MODERATE/SLOW/NON-MOVING by demand percentile and
    ranked by ``sort_by``. RBAC-gated by ``analytics.read``.
    """
    return await DemandAnalyticsService(session).compute(
        start_date=start_date,
        end_date=end_date,
        category=category,
        min_sales=min_sales,
        sort_by=sort_by,
        lead_time_days=lead_time_days,
    )


@router.get("/top-selling", response_model=TopSellingResponse)
async def top_selling(
    period: Optional[str] = Query(default=None, pattern="^(day|week|month)$"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(10, ge=1, le=50),
    _auth: CurrentUser = Depends(require_permission("analytics.read")),
    session: AsyncSession = Depends(get_session),
) -> TopSellingResponse:
    """Top-selling items across POS receipts and clinical dispenses.

    Aggregates ``receipt_items`` + ``dispenses`` by ``product_name`` over the
    date window and returns the top ``limit`` items ranked by total quantity.
    """
    if end_date is None:
        end_date = date.today().isoformat()
    if start_date is None:
        # period shortcuts so the frontend Day/Week/Month toggle works
        period_offsets = {"day": 1, "week": 7, "month": 30}
        offset = period_offsets.get(period or "month", 30)
        start_date = (date.today() - timedelta(days=offset)).isoformat()

    from sqlalchemy import text

    rows = await session.execute(
        text("""
            SELECT product_name, SUM(quantity) AS total_qty,
                   SUM(price_at_time * quantity) AS total_rev, 'combined' AS source
            FROM (
                SELECT ri.product_name, ri.quantity, ri.price_at_time
                FROM receipt_items ri
                JOIN receipts r ON r.id = ri.receipt_id
                WHERE ri.product_name != ''
                  AND (:start_date IS NULL OR r.timestamp >= :start_date)
                  AND (:end_date IS NULL OR r.timestamp <= :end_date || ' 23:59:59')
                UNION ALL
                SELECT d.product_name, d.quantity, d.price_at_time
                FROM dispenses d
                WHERE d.product_name != ''
                  AND (:start_date IS NULL OR d.fill_date >= :start_date)
                  AND (:end_date IS NULL OR d.fill_date <= :end_date)
            )
            GROUP BY product_name
            ORDER BY total_qty DESC
            LIMIT :limit
        """),
        {"start_date": start_date, "end_date": end_date, "limit": limit},
    )

    items: list[TopSellingItem] = []
    for i, row in enumerate(rows.mappings(), start=1):
        items.append(
            TopSellingItem(
                rank=i,
                product_name=row["product_name"],
                total_quantity=int(row["total_qty"] or 0),
                total_revenue=Decimal(str(row["total_rev"] or 0)),
                source=row["source"],
            )
        )

    return TopSellingResponse(
        window_start=start_date,
        window_end=end_date,
        items=items,
    )
