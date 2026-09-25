"""Receiving log routes: global view of all inventory receipt entries.

GET  /api/v1/receiving-log            — paginated list (date + vendor filters)
GET  /api/v1/receiving-log/vendors    — distinct vendor names for filter dropdown
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import (
    CurrentUser,
    PaginatedReceivingLog,
    ReceivingLogRead,
)

router = APIRouter(prefix="/api/v1/receiving-log", tags=["receiving-log"])


@router.get("", response_model=PaginatedReceivingLog)
async def list_receiving_log(
    date: Optional[str] = Query(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter by date_received (YYYY-MM-DD).",
    ),
    vendor: Optional[str] = Query(default=None, min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> PaginatedReceivingLog:
    """List all receiving-log entries across every vendor.

    Mirrors the legacy ``get_all_receiving_log(filter_date)`` from
    ``archive/database.py``.  When ``date`` is provided the server matches
    rows whose ``date_received`` starts with that day (handles both
    ``YYYY-MM-DD`` and full-timestamp formats).  ``vendor`` does a case-
    insensitive substring match on ``vendor_name``.
    """
    offset = (page - 1) * page_size
    where_clauses: list[str] = []
    params: dict[str, object] = {}

    if date:
        where_clauses.append("date_received LIKE :date_prefix")
        params["date_prefix"] = f"{date}%"
    if vendor:
        where_clauses.append("LOWER(vendor_name) LIKE :vendor")
        params["vendor"] = f"%{vendor.lower()}%"

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_row = await session.execute(
        text(f"SELECT COUNT(*) FROM receiving_log {where_sql}"),
        params,
    )
    total = count_row.scalar_one()

    rows = await session.execute(
        text(f"""
            SELECT id, vendor_name, product_name, date_received,
                   quantity, total_cost, barcode, lot_number
            FROM receiving_log {where_sql}
            ORDER BY date_received DESC, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset},
    )
    items = [ReceivingLogRead(**dict(r._mapping)) for r in rows.fetchall()]

    return PaginatedReceivingLog(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/vendors", response_model=list[str])
async def list_receiving_log_vendors(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Return distinct vendor names present in the receiving log."""
    rows = await session.execute(
        text("SELECT DISTINCT vendor_name FROM receiving_log "
             "WHERE vendor_name != '' AND vendor_name != 'N/A' "
             "ORDER BY vendor_name")
    )
    return [r[0] for r in rows.fetchall() if r[0]]
