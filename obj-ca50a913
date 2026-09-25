"""Alerts route: aggregated inventory alert counts for the dashboard banner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("")
async def get_alerts(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return aggregated alert counts for the dashboard banner.

    Alert categories:
      - expired: batches whose expiry_date is in the past
      - critical: batches expiring within 30 days
      - warning: batches expiring within 90 days
      - low_stock: products at or below their reorder threshold
    """
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_30 = (today + timedelta(days=30)).isoformat()
    cutoff_90 = (today + timedelta(days=90)).isoformat()
    today_str = today.isoformat()

    # Expired batches (expiry < today, still in stock)
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM inventory_extended
            WHERE expiration_date < :today
              AND on_hand > 0
        """),
        {"today": today_str},
    )
    expired = r.scalar() or 0

    # Critical: expiring within 30 days (but not already expired)
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM inventory_extended
            WHERE expiration_date >= :today
              AND expiration_date <= :cutoff
              AND on_hand > 0
        """),
        {"today": today_str, "cutoff": cutoff_30},
    )
    critical = r.scalar() or 0

    # Warning: expiring within 31-90 days
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM inventory_extended
            WHERE expiration_date > :cutoff_30
              AND expiration_date <= :cutoff_90
              AND on_hand > 0
        """),
        {"cutoff_30": cutoff_30, "cutoff_90": cutoff_90},
    )
    warning = r.scalar() or 0

    # Low stock products
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM products p
            JOIN inventory_extended ie ON ie.drug_name = p.name
            WHERE (p.deleted = 0 OR p.deleted IS NULL)
              AND p.reorder_threshold IS NOT NULL
              AND p.reorder_threshold > 0
              AND ie.on_hand <= p.reorder_threshold
        """)
    )
    low_stock = r.scalar() or 0

    # Total active products for context
    r = await session.execute(
        text("SELECT COUNT(*) FROM products WHERE deleted = 0 OR deleted IS NULL")
    )
    total_products = r.scalar() or 0

    return {
        "expired": expired,
        "critical": critical,
        "warning": warning,
        "low_stock": low_stock,
        "total_products": total_products,
        "checked_at": now.isoformat(),
    }
