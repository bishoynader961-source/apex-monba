"""Purchase Order service: CRUD + lifecycle management + auto-reorder."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Product, PurchaseOrder, PurchaseOrderItem
from app.shared.exceptions import AppException, NotFoundError
from app.shared.logging_config import get_logger

# Import barcode generator for PO receipt
import uuid


def _generate_internal_barcode(vendor_name: str = "GEN") -> str:
    prefix = (vendor_name[:3] if vendor_name and vendor_name != "N/A" else "GEN").upper()
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
try:
    from native_accel import generate_batch_barcodes
    HAS_NATIVE_ACCEL = True
except ImportError:
    HAS_NATIVE_ACCEL = False
    def generate_batch_barcodes(vendor_name: str, qty: int) -> list[str]:
        prefix = (vendor_name[:3] if vendor_name else "GEN").upper()
        return [f"{prefix}-{_generate_internal_barcode(vendor_name).split('-')[1]}" for _ in range(qty)]
from app.shared.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderItemRead,
    PurchaseOrderRead,
    PurchaseOrderUpdate,
)

logger = get_logger("po")

_VALID_TRANSITIONS = {
    "Draft": "Submitted",
    "Submitted": "Received",
    "Received": "Closed",
}


class PurchaseOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _next_po_number(self) -> str:
        year = datetime.now(timezone.utc).year
        result = await self.session.execute(
            select(PurchaseOrder).where(PurchaseOrder.po_number.like(f"PO-{year}-%")).order_by(PurchaseOrder.id.desc()).limit(1)
        )
        last = result.scalar_one_or_none()
        if last:
            try:
                seq = int(last.po_number.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"PO-{year}-{seq:05d}"

    async def _recalc_totals(self, po_id: int) -> None:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            return
        result = await self.session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id)
        )
        items = result.scalars().all()
        subtotal = sum(i.line_total for i in items)
        po.subtotal = Decimal(str(subtotal)).quantize(Decimal("0.01"))
        po.total_cost = po.subtotal + po.tax_amount

    async def list_pos(self, status_filter: str = "") -> list[PurchaseOrderRead]:
        stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.desc())
        if status_filter:
            stmt = stmt.where(PurchaseOrder.status == status_filter)
        result = await self.session.execute(stmt)
        pos = result.scalars().all()
        out: list[PurchaseOrderRead] = []
        for po in pos:
            items_result = await self.session.execute(
                select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id).order_by(PurchaseOrderItem.line_number)
            )
            items = items_result.scalars().all()
            out.append(PurchaseOrderRead(
                id=po.id, po_number=po.po_number, vendor_id=po.vendor_id,
                vendor_name=po.vendor_name, status=po.status, notes=po.notes,
                subtotal=po.subtotal, tax_amount=po.tax_amount, total_cost=po.total_cost,
                created_at=po.created_at, submitted_at=po.submitted_at,
                received_at=po.received_at, closed_at=po.closed_at, created_by=po.created_by,
                items=[PurchaseOrderItemRead.model_validate(i) for i in items],
            ))
        return out

    async def get_po(self, po_id: int) -> PurchaseOrderRead:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        items_result = await self.session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id).order_by(PurchaseOrderItem.line_number)
        )
        items = items_result.scalars().all()
        return PurchaseOrderRead(
            id=po.id, po_number=po.po_number, vendor_id=po.vendor_id,
            vendor_name=po.vendor_name, status=po.status, notes=po.notes,
            subtotal=po.subtotal, tax_amount=po.tax_amount, total_cost=po.total_cost,
            created_at=po.created_at, submitted_at=po.submitted_at,
            received_at=po.received_at, closed_at=po.closed_at, created_by=po.created_by,
            items=[PurchaseOrderItemRead.model_validate(i) for i in items],
        )

    async def create_po(self, payload: PurchaseOrderCreate, username: str) -> PurchaseOrderRead:
        po_number = await self._next_po_number()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        po = PurchaseOrder(
            po_number=po_number,
            vendor_id=payload.vendor_id,
            vendor_name=payload.vendor_name,
            notes=payload.notes,
            created_at=now,
            created_by=username,
        )
        self.session.add(po)
        await self.session.flush()
        for idx, item in enumerate(payload.items, 1):
            line_total = Decimal(str(item.quantity)) * item.unit_price
            po_item = PurchaseOrderItem(
                po_id=po.id,
                line_number=idx,
                product_name=item.product_name,
                vendor_sku=item.vendor_sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=Decimal(str(line_total)).quantize(Decimal("0.01")),
            )
            self.session.add(po_item)
        await self.session.flush()
        await self._recalc_totals(po.id)
        return await self.get_po(po.id)

    async def update_po(self, po_id: int, payload: PurchaseOrderUpdate) -> PurchaseOrderRead:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        if po.status != "Draft":
            raise AppException("Only Draft POs can be edited", status_code=400, error_code="po_not_draft")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(po, field, value)
        await self.session.flush()
        return await self.get_po(po_id)

    async def add_item(self, po_id: int, item: dict) -> PurchaseOrderRead:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        if po.status != "Draft":
            raise AppException("Only Draft POs can be edited", status_code=400, error_code="po_not_draft")
        result = await self.session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id)
        )
        existing = result.scalars().all()
        line_number = max((i.line_number for i in existing), default=0) + 1
        line_total = Decimal(str(item.get("quantity", 0))) * Decimal(str(item.get("unit_price", 0)))
        po_item = PurchaseOrderItem(
            po_id=po_id,
            line_number=line_number,
            product_name=item.get("product_name", ""),
            vendor_sku=item.get("vendor_sku", ""),
            quantity=item.get("quantity", 0),
            unit_price=Decimal(str(item.get("unit_price", 0))),
            line_total=Decimal(str(line_total)).quantize(Decimal("0.01")),
        )
        self.session.add(po_item)
        await self.session.flush()
        await self._recalc_totals(po_id)
        return await self.get_po(po_id)

    async def remove_item(self, po_id: int, item_id: int) -> PurchaseOrderRead:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        if po.status != "Draft":
            raise AppException("Only Draft POs can be edited", status_code=400, error_code="po_not_draft")
        item = await self.session.get(PurchaseOrderItem, item_id)
        if item is None or item.po_id != po_id:
            raise NotFoundError("PurchaseOrderItem", str(item_id))
        await self.session.delete(item)
        await self.session.flush()
        await self._recalc_totals(po_id)
        return await self.get_po(po_id)

    async def transition_status(self, po_id: int, username: str) -> PurchaseOrderRead:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        next_status = _VALID_TRANSITIONS.get(po.status)
        if next_status is None:
            raise AppException(f"Cannot transition from {po.status}", status_code=400, error_code="po_invalid_transition")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        po.status = next_status
        if next_status == "Submitted":
            po.submitted_at = now
        elif next_status == "Received":
            po.received_at = now
            # Receive items into inventory
            items_result = await self.session.execute(
                select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id)
            )
            items = items_result.scalars().all()
            for item in items:
                item.received_qty = item.quantity
                item.status = "Received"
                item.received_at = now
                # Add to inventory
                inv_result = await self.session.execute(
                    select(Product).where(Product.name == item.product_name)
                )
                inv = inv_result.scalar_one_or_none()
                if inv:
                    inv.quantity_on_hand += item.quantity
        elif next_status == "Closed":
            po.closed_at = now
        await self.session.flush()
        return await self.get_po(po_id)

    async def receive_po(self, po_id: int, items: list, username: str) -> PurchaseOrderRead:
        """Receive a PO with per-item received qty, lot number, and expiry date.
        
        Uses pre-generated barcodes from native_accel for batch barcode generation.
        """
        import json
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        if po.status not in ("Draft", "Submitted"):
            raise AppException(f"PO must be Draft or Submitted to receive", status_code=400, error_code="po_invalid_status")
        
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        date_received = now.split("T")[0]
        vendor_name = po.vendor_name or ""
        
        # Get PO items with metadata
        items_result = await self.session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id).order_by(PurchaseOrderItem.line_number)
        )
        po_items = items_result.scalars().all()
        
        # Build item map from request
        item_map = {str(i.item_id): i for i in items}
        
        # Calculate total quantity for barcode generation
        total_qty = sum(int(item_map.get(str(pi.id), {}).received_qty or pi.quantity) for pi in po_items)
        
        # Generate barcodes
        if HAS_NATIVE_ACCEL:
            from native_accel import generate_batch_barcodes
            all_barcodes = generate_batch_barcodes(vendor_name, total_qty)
        else:
            all_barcodes = generate_batch_barcodes(vendor_name, total_qty)
        
        barcode_offset = 0
        
        # Import inventory service for atomic receiving
        from app.services.inventory_service import InventoryService
        inv_service = InventoryService(self.session)
        
        for pi in po_items:
            req_item = item_map.get(str(pi.id))
            received_qty = req_item.received_qty if req_item and req_item.received_qty > 0 else pi.quantity
            lot_number = req_item.lot_number if req_item else ""
            expiry_date = req_item.expiry_date if req_item else ""
            mfg_date = req_item.mfg_date if req_item else ""
            
            if received_qty <= 0:
                continue
                
            item_barcodes = all_barcodes[barcode_offset:barcode_offset + received_qty]
            barcode_offset += received_qty
            
            # Update PO item
            pi.received_qty = received_qty
            pi.status = "Received"
            pi.received_at = now
            pi.internal_barcodes = json.dumps(item_barcodes)
            pi.lot_number = lot_number
            if expiry_date:
                pi.expiry_date = expiry_date
            if mfg_date:
                pi.mfg_date = mfg_date
            
            # Receive into inventory atomically
            await inv_service.receive_batch(
                product_name=pi.product_name,
                lot_number=lot_number,
                expiry_date=expiry_date,
                quantity=received_qty,
                unit_cost=float(pi.unit_price),
                supplier=vendor_name,
                ndc_code="",
            )
        
        po.status = "Received"
        po.received_at = now
        
        await self.session.flush()
        return await self.get_po(po_id)

    async def delete_po(self, po_id: int) -> None:
        po = await self.session.get(PurchaseOrder, po_id)
        if po is None:
            raise NotFoundError("PurchaseOrder", str(po_id))
        if po.status != "Draft":
            raise AppException("Only Draft POs can be deleted", status_code=400, error_code="po_not_draft")
        # Delete items first
        items_result = await self.session.execute(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po_id)
        )
        for item in items_result.scalars().all():
            await self.session.delete(item)
        await self.session.delete(po)
        await self.session.flush()

    # ── Auto-Reorder ────────────────────────────────────────────────────

    async def compute_low_stock_groups(self) -> list[dict[str, Any]]:
        """Group below-reorder-threshold products by their vendor_name.

        Returns ``[{"vendor_name": str, "items": [{"name", "current_qty",
        "threshold", "suggested_qty", "wholesale_price"}]}]``.
        """
        result = await self.session.execute(
            text(
                "SELECT p.name, ie.on_hand, p.reorder_threshold, p.vendor_name, "
                "p.wholesale_price "
                "FROM products p "
                "JOIN inventory_extended ie ON ie.drug_name = p.name "
                "WHERE (p.is_deleted = 0 OR p.is_deleted IS NULL) "
                "AND p.reorder_threshold IS NOT NULL AND p.reorder_threshold > 0 "
                "AND ie.on_hand <= p.reorder_threshold"
            )
        )
        low_rows = result.all()
        if not low_rows:
            return []

        groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"vendor_name": "", "items": []})
        for name, qty, threshold, vendor_name, wholesale_price in low_rows:
            vendor_key = vendor_name or "Unassigned"
            entry = groups[vendor_key]
            entry["vendor_name"] = vendor_key
            buffer_n = max(int(threshold or 0), 1)
            suggested_qty = int(threshold or 0) + buffer_n
            entry["items"].append({
                "name": name,
                "current_qty": int(qty or 0),
                "threshold": int(threshold or 0),
                "suggested_qty": suggested_qty,
                "wholesale_price": float(wholesale_price or 0.0),
            })
        return list(groups.values())

    async def auto_reorder(self, username: str = "system") -> dict[str, Any]:
        """Draft a consolidated PO for every low-stock supplier group.

        Returns ``{"po_count", "item_count", "low_stock_count", "drafts": [...]}``.
        """
        groups = await self.compute_low_stock_groups()
        drafts: list[dict[str, Any]] = []
        po_count = 0
        item_count = 0

        for group in groups:
            vendor_name = group["vendor_name"]
            po_number = await self._next_po_number()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")

            po = PurchaseOrder(
                po_number=po_number,
                vendor_name=vendor_name,
                notes="Auto-generated reorder (low stock)",
                created_at=now,
                created_by=username,
            )
            self.session.add(po)
            await self.session.flush()

            for idx, it in enumerate(group["items"], 1):
                line_total = Decimal(str(it["suggested_qty"])) * Decimal(str(it["wholesale_price"]))
                po_item = PurchaseOrderItem(
                    po_id=po.id,
                    line_number=idx,
                    product_name=it["name"],
                    vendor_sku="",
                    quantity=it["suggested_qty"],
                    unit_price=Decimal(str(it["wholesale_price"])).quantize(Decimal("0.01")),
                    line_total=Decimal(str(line_total)).quantize(Decimal("0.01")),
                )
                self.session.add(po_item)
                item_count += 1

            await self.session.flush()
            await self._recalc_totals(po.id)
            drafts.append({"po_id": po.id, "po_number": po_number})
            po_count += 1

        logger.info(
            "auto_reorder_complete po_count=%d item_count=%d low_stock_groups=%d",
            po_count, item_count, len(groups),
        )
        return {
            "po_count": po_count,
            "item_count": item_count,
            "low_stock_count": len(groups),
            "drafts": drafts,
        }
