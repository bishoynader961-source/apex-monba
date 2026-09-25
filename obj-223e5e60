"""Vendor Management routes.

GET  /api/v1/vendors                  — list all active vendors
POST /api/v1/vendors                  — create a new vendor
GET  /api/v1/vendors/{id}             — get a single vendor
PUT  /api/v1/vendors/{id}             — update vendor (partial)
GET  /api/v1/vendors/{id}/items       — list products sourced from vendor
GET  /api/v1/vendors/{id}/purchases   — purchase history for vendor
POST /api/v1/vendors/receive          — receive a shipment: increments stock,
                                        updates balance_due, logs to audit
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import (
    CurrentUser,
    PurchaseHistoryRead,
    ReceiveShipmentPayload,
    VendorCreate,
    VendorItemRead,
    VendorRead,
    VendorUpdate,
)

router = APIRouter(prefix="/api/v1/vendors", tags=["vendors"])


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[VendorRead])
async def list_vendors(
    active_only: bool = Query(True),
    q: Optional[str] = Query(None),
    _auth: CurrentUser = Depends(require_permission("vendors.read")),
    session: AsyncSession = Depends(get_session),
) -> list[VendorRead]:
    """List all vendors, optionally filtered by active status and search term."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if active_only:
        clauses.append("is_active = 1")
    if q:
        clauses.append("LOWER(company_name) LIKE :q")
        params["q"] = f"%{q.lower()}%"

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await session.execute(
        text(f"""
            SELECT id, company_name, contact_phone, contact_email, tax_id,
                   balance_due, is_active, address, notes, created_at
            FROM vendors {where}
            ORDER BY company_name
        """),
        params,
    )
    return [VendorRead(**dict(row._mapping)) for row in rows]


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    _auth: CurrentUser = Depends(require_permission("vendors.write")),
    session: AsyncSession = Depends(get_session),
) -> VendorRead:
    """Create a new vendor."""
    vendor_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with session.begin():
        await session.execute(
            text("""
                INSERT INTO vendors
                    (id, company_name, contact_phone, contact_email, tax_id,
                     balance_due, is_active, address, notes, created_at, updated_at)
                VALUES
                    (:id, :company_name, :contact_phone, :contact_email, :tax_id,
                     0, 1, :address, :notes, :created_at, :created_at)
            """),
            {
                "id": vendor_id,
                "company_name": payload.company_name,
                "contact_phone": payload.contact_phone,
                "contact_email": payload.contact_email,
                "tax_id": payload.tax_id,
                "address": payload.address,
                "notes": payload.notes,
                "created_at": now,
            },
        )

    row = await session.execute(
        text("SELECT * FROM vendors WHERE id = :id"), {"id": vendor_id}
    )
    vendor = row.mappings().first()
    if not vendor:
        raise HTTPException(status_code=500, detail="Failed to create vendor")
    return VendorRead(**dict(vendor))


@router.get("/{vendor_id}", response_model=VendorRead)
async def get_vendor(
    vendor_id: str,
    _auth: CurrentUser = Depends(require_permission("vendors.read")),
    session: AsyncSession = Depends(get_session),
) -> VendorRead:
    row = await session.execute(
        text("SELECT * FROM vendors WHERE id = :id"), {"id": vendor_id}
    )
    vendor = row.mappings().first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return VendorRead(**dict(vendor))


@router.put("/{vendor_id}", response_model=VendorRead)
async def update_vendor(
    vendor_id: str,
    payload: VendorUpdate,
    _auth: CurrentUser = Depends(require_permission("vendors.write")),
    session: AsyncSession = Depends(get_session),
) -> VendorRead:
    """Update vendor fields (partial — only sent fields are applied)."""
    now = datetime.now(timezone.utc).isoformat()
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with session.begin():
        result = await session.execute(
            text("SELECT id FROM vendors WHERE id = :id"), {"id": vendor_id}
        )
        if not result.first():
            raise HTTPException(status_code=404, detail="Vendor not found")

        set_clauses = [f"{k} = :{k}" for k in updates]
        set_clauses.append("updated_at = :now")
        updates["now"] = now
        updates["id"] = vendor_id

        await session.execute(
            text(f"UPDATE vendors SET {', '.join(set_clauses)} WHERE id = :id"),
            updates,
        )

    row = await session.execute(
        text("SELECT * FROM vendors WHERE id = :id"), {"id": vendor_id}
    )
    mapped = row.mappings().first()
    if mapped is None:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return VendorRead(**dict(mapped))


@router.get("/{vendor_id}/items", response_model=list[VendorItemRead])
async def get_vendor_items(
    vendor_id: str,
    _auth: CurrentUser = Depends(require_permission("vendors.read")),
    session: AsyncSession = Depends(get_session),
) -> list[VendorItemRead]:
    """List all products sourced from this vendor."""
    rows = await session.execute(
        text("""
            SELECT id, vendor_id, product_name, unit_cost, sku, is_primary
            FROM vendor_items WHERE vendor_id = :vendor_id
            ORDER BY product_name
        """),
        {"vendor_id": vendor_id},
    )
    return [VendorItemRead(**dict(r._mapping)) for r in rows]


@router.get("/{vendor_id}/purchases", response_model=list[PurchaseHistoryRead])
async def get_vendor_purchases(
    vendor_id: str,
    limit: int = Query(50, ge=1, le=200),
    _auth: CurrentUser = Depends(require_permission("vendors.read")),
    session: AsyncSession = Depends(get_session),
) -> list[PurchaseHistoryRead]:
    """Purchase history for a specific vendor."""
    rows = await session.execute(
        text("""
            SELECT id, vendor_id, product_name, quantity, unit_cost, total_cost,
                   invoice_ref, received_date, received_by, notes, created_at
            FROM purchase_history WHERE vendor_id = :vendor_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"vendor_id": vendor_id, "limit": limit},
    )
    return [PurchaseHistoryRead(**dict(r._mapping)) for r in rows]


@router.post("/receive", status_code=status.HTTP_201_CREATED)
async def receive_shipment(
    payload: ReceiveShipmentPayload,
    current_user: CurrentUser = Depends(require_permission("vendors.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Receive a supplier shipment.

    Atomically:
    1. Validates vendor exists.
    2. Inserts N rows into ``products`` (serialized -- 1 row per box).
    3. Increments ``vendors.balance_due`` by total cost.
    4. Creates a ``purchase_history`` record.
    5. Writes an audit log entry.
    """
    total_cost = Decimal(str(payload.unit_cost)) * payload.quantity
    now = datetime.now(timezone.utc).isoformat()
    received_date = payload.received_date or datetime.now(timezone.utc).date().isoformat()

    async with session.begin():
        vendor_row = await session.execute(
            text("SELECT company_name FROM vendors WHERE id = :id AND is_active = 1"),
            {"id": payload.vendor_id},
        )
        vendor = vendor_row.mappings().first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found or inactive")

        vendor_name = vendor["company_name"]
        prefix = vendor_name[:3].upper() if vendor_name else "GEN"

        for _ in range(payload.quantity):
            internal_barcode = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
            await session.execute(
                text("""
                    INSERT INTO products
                        (name, price, manufacturer_barcode, internal_unique_barcode,
                         vendor_name, status, expiry_date, manufacture_date, category)
                    VALUES
                        (:name, :price, '', :barcode, :vendor, 'In Stock', '', '', 'Uncategorized')
                """),
                {
                    "name": payload.product_name,
                    "price": float(payload.unit_cost),
                    "barcode": internal_barcode,
                    "vendor": vendor_name,
                },
            )

        await session.execute(
            text("UPDATE vendors SET balance_due = balance_due + :amount WHERE id = :id"),
            {"amount": float(total_cost), "id": payload.vendor_id},
        )

        await session.execute(
            text("""
                INSERT INTO purchase_history
                    (vendor_id, product_name, quantity, unit_cost, total_cost,
                     invoice_ref, received_date, received_by, notes, created_at)
                VALUES
                    (:vendor_id, :product_name, :qty, :unit_cost, :total_cost,
                     :invoice_ref, :received_date, :received_by, :notes, :now)
            """),
            {
                "vendor_id": payload.vendor_id,
                "product_name": payload.product_name,
                "qty": payload.quantity,
                "unit_cost": float(payload.unit_cost),
                "total_cost": float(total_cost),
                "invoice_ref": payload.invoice_ref,
                "received_date": received_date,
                "received_by": current_user.username,
                "notes": payload.notes,
                "now": now,
            },
        )

        await session.execute(
            text("""
                INSERT INTO audit_logs
                    (user_id, action, resource, details, timestamp)
                VALUES
                    (:user_id, 'VENDOR_RECEIVE', 'purchase_history',
                     :details, :timestamp)
            """),
            {
                "user_id": current_user.id,
                "details": (
                    f"Received {payload.quantity} x {payload.product_name} "
                    f"from {vendor_name} | invoice={payload.invoice_ref} | "
                    f"total=${float(total_cost):.2f}"
                ),
                "timestamp": now,
            },
        )

    return {
        "message": (
            f"Received {payload.quantity} unit(s) of '{payload.product_name}' "
            f"from '{vendor_name}'. Balance due updated to include ${float(total_cost):.2f}."
        ),
        "units_inserted": payload.quantity,
        "total_cost": float(total_cost),
        "invoice_ref": payload.invoice_ref,
    }
