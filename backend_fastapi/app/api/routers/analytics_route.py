"""Demand Analytics routes: item velocity, revenue, and reorder intelligence."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.services.demand_analytics_service import DemandAnalyticsService
from app.shared.schemas import CurrentUser, DemandAnalyticsSummary

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
