"""Dashboard metrics route.

GET /api/v1/dashboard/metrics  — KPI cards + low-stock alerts + recent activity
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import CurrentUser

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate KPI data, low-stock items, and recent audit activity."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total products
    r = await session.execute(text("SELECT COUNT(*) FROM products WHERE deleted = 0 OR deleted IS NULL"))
    total_products = r.scalar() or 0

    # Total inventory value
    r = await session.execute(text("SELECT COALESCE(SUM(price * quantity_on_hand), 0) FROM products WHERE deleted = 0 OR deleted IS NULL"))
    total_inventory_value = str(r.scalar() or 0)

    # Today's sales (receipts)
    r = await session.execute(
        text("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM receipts WHERE created_at >= :today"),
        {"today": today_start.isoformat()},
    )
    row = r.fetchone()
    today_receipts = row[0] if row else 0
    today_revenue = str(row[1] if row else 0)

    # Low-stock items (quantity_on_hand <= reorder_threshold, both non-null and positive threshold)
    r = await session.execute(text("""
        SELECT name, quantity_on_hand, reorder_threshold, internal_unique_barcode
        FROM products
        WHERE (deleted = 0 OR deleted IS NULL)
          AND reorder_threshold IS NOT NULL
          AND reorder_threshold > 0
          AND quantity_on_hand <= reorder_threshold
        ORDER BY quantity_on_hand ASC
        LIMIT 20
    """))
    low_stock = [
        {"name": row[0], "on_hand": row[1], "threshold": row[2], "barcode": row[3]}
        for row in r.fetchall()
    ]

    # Expiring soon (within 90 days)
    expiry_90 = (now + timedelta(days=90)).isoformat()
    r = await session.execute(text("""
        SELECT name, quantity_on_hand, expiry_date, internal_unique_barcode
        FROM products
        WHERE (deleted = 0 OR deleted IS NULL)
          AND expiry_date IS NOT NULL
          AND expiry_date != ''
          AND expiry_date <= :cutoff
        ORDER BY expiry_date ASC
        LIMIT 20
    """), {"cutoff": expiry_90})
    expiring_soon = [
        {"name": row[0], "on_hand": row[1], "expiry": row[2], "barcode": row[3]}
        for row in r.fetchall()
    ]

    # Active patients
    r = await session.execute(text("SELECT COUNT(*) FROM patients"))
    active_patients = r.scalar() or 0

    # Pending Rx count (status = 'pending' in rx_queue or dispenses table)
    try:
        r = await session.execute(text("SELECT COUNT(*) FROM dispenses WHERE status = 'pending'"))
        pending_rx_count = r.scalar() or 0
    except Exception:
        pending_rx_count = 0

    # Recent activity (last 15 audit entries)
    r = await session.execute(text("""
        SELECT action, details, created_at
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT 15
    """))
    recent_activity = [
        {"action": row[0], "details": row[1], "time": str(row[2]) if row[2] else ""}
        for row in r.fetchall()
    ]

    return {
        "total_products": total_products,
        "total_inventory_value": total_inventory_value,
        "today_receipts": today_receipts,
        "today_revenue": today_revenue,
        "active_patients": active_patients,
        "pending_rx_count": pending_rx_count,
        "low_stock": low_stock,
        "expiring_soon": expiring_soon,
        "recent_activity": recent_activity,
    }


@router.get("/analytics")
async def get_dashboard_analytics(
    _auth: CurrentUser = Depends(require_permission("analytics.read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mock analytics payload for the dashboard.

    Returns a static summary that satisfies the frontend expectations for the
    `/api/v1/dashboard/analytics` endpoint. In a real implementation this would
    aggregate various KPI data similar to ``get_dashboard_metrics`` but for
    simplicity we provide deterministic mock data.
    """
    # Example static data – can be expanded as needed.
    return {
        "total_sales": 12456.78,
        "total_customers": 342,
        "top_items": [
            {"product_name": "Aspirin", "total_quantity": 120, "total_revenue": 360.0},
            {"product_name": "Ibuprofen", "total_quantity": 95, "total_revenue": 285.0},
        ],
    }
