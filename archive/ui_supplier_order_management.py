"""
ui_supplier_order_management.py — Supplier & Purchase-Order Management for PharmacyPro.

PART 1: Infrastructure (preamble, TypedDicts, ``SupplierObserver``,
``SupplierCrudManager``, ``PoCrudManager``).

The accompanying UI layer (dialogs + ``SupplierOrderManagementFrame`` +
``setup_supplier_order_tab``) is introduced in a subsequent chunk per the build
plan; this module imports cleanly and is ``py_compile``-clean on its own.

Conventions (mirroring ``ui_pos_retail`` / ``ui_inventory_management``):
  * DB reads/writes go through ``SqliteWALConnection`` (WAL, busy_timeout,
    exponential-backoff retry on ``sqlite3.OperationalError``).
  * Shared cross-cutting reads/receipts delegate to the ``database`` layer
    (``get_next_po_number``, ``get_products_below_reorder_threshold``,
    ``receive_po_items``) which are ``@_db_fallback``-delegated to the DBAPI.
  * ``native_accel.fuzzy_search`` / ``generate_batch_barcodes`` power the
    supplier search and receipt-time barcode pre-generation, with a pure-python
    difflib fallback preserved for environments without rapidfuzz.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Callable, TypedDict

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n
import database
import audit_log
import barcode_logic
from native_accel import fuzzy_search, generate_batch_barcodes, _native_accel_loaded

try:
    from ndc_dictionary import barcode_lookup, ndc_lookup, name_lookup
    HAS_NDC = True
except ImportError:
    HAS_NDC = False
    log.warning("ndc_dictionary not available; product lookup will be limited")
from ui_navigation import (
    COLOR_CARD_BG, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
    COLOR_ACCENT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SIDEBAR_BG, COLOR_SIDEBAR_HOVER,
)

# ── AsyncUI (optional — graceful fallback to synchronous) ─────────────────
try:
    from async_ui import AsyncUI
    HAS_ASYNC: bool = True
except ImportError:  # pragma: no cover
    AsyncUI = None  # type: ignore[assignment]
    HAS_ASYNC = False
    logging.getLogger("ui_supplier_order_management").warning(
        "async_ui not available; DB ops run synchronously")

# ── native_accel guard (fuzzy search + batch barcodes, python fallback) ─────
try:
    _HAS_NATIVE_ACCEL: bool = bool(_native_accel_loaded())
except Exception:  # pragma: no cover — native_accel is pure-python fallback otherwise
    _HAS_NATIVE_ACCEL = False

log = logging.getLogger("ui_supplier_order_management")

# ── SqliteWALConnection (imported, NOT duplicated) ──────────────────────────
try:
    from ui_pos_retail import SqliteWALConnection
except ImportError:  # pragma: no cover
    SqliteWALConnection = None  # type: ignore[assignment]
    log.warning("SqliteWALConnection not importable from ui_pos_retail; DB ops fail loudly")


# ═════════════════════════════════════════════════════════════════════════════
#  TypedDicts  (§5.2 — mirror the column sets the managers actually select)
# ═════════════════════════════════════════════════════════════════════════════


class SupplierRow(TypedDict, total=False):
    id: int
    name: str
    contact_name: str
    contact_email: str
    contact_phone: str
    address: str
    tax_id: str
    preferred: int
    sku: str
    min_stock_level: int
    lead_time_days: int
    edi_endpoint: str
    performance_notes: str


class PoRow(TypedDict, total=False):
    id: int
    po_number: str
    vendor_id: int
    vendor_name: str
    status: str
    created_at: str
    submitted_at: str
    received_at: str
    closed_at: str
    total_cost: float
    notes: str


class PoItemRow(TypedDict, total=False):
    id: int
    po_id: int
    line_number: int
    product_name: str
    quantity: int
    unit_price: float
    line_total: float
    status: str
    internal_barcodes: str


_SUPPLIER_FIELDS: tuple[str, ...] = (
    "id", "name", "contact_name", "contact_email", "contact_phone", "address",
    "tax_id", "preferred", "sku", "min_stock_level", "lead_time_days", "edi_endpoint",
    "performance_notes",
)
_PO_FIELDS: tuple[str, ...] = (
    "id", "po_number", "vendor_id", "vendor_name", "status", "created_at",
    "submitted_at", "received_at", "closed_at", "total_cost", "notes",
)
_PO_ITEM_FIELDS: tuple[str, ...] = (
    "id", "po_id", "line_number", "product_name", "quantity", "unit_price",
    "line_total", "status", "internal_barcodes",
)


def _supplier_row(row: tuple) -> SupplierRow:
    return SupplierRow(**dict(zip(_SUPPLIER_FIELDS, row)))  # type: ignore[arg-type]


def _po_row(row: tuple) -> PoRow:
    return PoRow(**dict(zip(_PO_FIELDS, row)))  # type: ignore[arg-type]


def _po_item_row(row: tuple) -> PoItemRow:
    return PoItemRow(**dict(zip(_PO_ITEM_FIELDS, row)))  # type: ignore[arg-type]


# Purchase-order lifecycle state machine: current → {legal next states}.
# ``Received`` is reached only through the inventory-receipt path.
PO_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Submitted", "Cancelled"},
    "Submitted": {"Draft", "Received", "Cancelled"},
    "Received": {"Closed"},
}

PO_STATUS_KEYS: dict[str, str] = {
    "Draft": "po_status_draft",
    "Submitted": "submitted",
    "Received": "po_status_received",
    "Closed": "closed",
    "Cancelled": "cancelled",
}


# ═════════════════════════════════════════════════════════════════════════════
#  Observer  (§5.3 — identical contract to InventoryObserver)
# ═════════════════════════════════════════════════════════════════════════════


class SupplierObserver:
    """Observer for supplier / PO state-change notifications.

    Mirrors ``InventoryObserver``: subscribers register a
    ``callback(event, data_dict)`` invoked best-effort on every event.

    Events (§5.3):
      * ``suppliers_changed``     — any supplier create/update/delete/flag
      * ``purchase_orders_changed`` — PO create/status/transition
      * ``po_item_added``          — a line item was appended to a PO
      * ``po_item_removed``        — a line item was deleted from a PO
    """

    def __init__(self) -> None:
        self._observers: list[Callable[[str, dict[str, Any]], None]] = []

    def register(self, callback: Callable[[str, dict[str, Any]], None]) -> int:
        self._observers.append(callback)
        return len(self._observers) - 1

    def unregister(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        try:
            self._observers.remove(callback)
        except ValueError:
            pass

    def notify(self, event: str, data: dict[str, Any]) -> None:
        for observer in list(self._observers):
            try:
                observer(event, data)
            except Exception as exc:  # noqa: BLE001 — observer isolation
                log.error("Supplier observer error on '%s': %s", event, exc)


# ═════════════════════════════════════════════════════════════════════════════
#  Pure-python fuzzy fallback (used only when native_accel is unavailable)
# ═════════════════════════════════════════════════════════════════════════════


def _fuzzy_fallback(query: str, choices: list[str],
                    cutoff: float = 60.0) -> list[tuple[str, float, int]]:
    """difflib fallback mirroring ``native_accel.fuzzy_search`` output shape."""
    if not query or not choices:
        return []
    scored: list[tuple[float, str, int]] = []
    ql = query.lower()
    for idx, choice in enumerate(choices):
        ratio = SequenceMatcher(None, ql, str(choice).lower()).ratio() * 100.0
        if ratio >= cutoff:
            scored.append((ratio, choice, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(choice, round(score, 2), idx) for score, choice, idx in scored[:len(choices)]]


# ═════════════════════════════════════════════════════════════════════════════
#  SupplierCrudManager  (§5.4)
# ═════════════════════════════════════════════════════════════════════════════


class SupplierCrudManager:
    """Async-capable CRUD over the ``suppliers`` table.

    Every query runs through ``SqliteWALConnection`` (WAL reads + busy_timeout
    + exponential backoff on ``sqlite3.OperationalError``).  All mutating
    methods emit ``SupplierObserver`` events + ``audit_log`` entries.
    """

    def __init__(self, db_path: str | None = None,
                 observer: SupplierObserver | None = None) -> None:
        self._db_path: str = db_path or database.get_db_path()
        self._observer: SupplierObserver = observer or SupplierObserver()

    @property
    def observer(self) -> SupplierObserver:
        return self._observer

    def load_all(self) -> list[SupplierRow]:
        """All suppliers ordered by name (preferred flag is a badge, not sort)."""
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(f"""
                SELECT {", ".join(_SUPPLIER_FIELDS)}
                FROM suppliers ORDER BY name ASC
            """)
            rows = cur.fetchall()
        return [_supplier_row(r) for r in rows]

    def search(self, query: str, cutoff: float = 60.0) -> list[SupplierRow]:
        """Typo-tolerant supplier search; results returned in ranked order.

        Uses ``native_accel.fuzzy_search`` when available, else a pure-python
        difflib scorer — identical ``(choice, score, index)`` contract.
        """
        all_rows = self.load_all()
        if not query:
            return all_rows
        choices = [r["name"] for r in all_rows]
        if _HAS_NATIVE_ACCEL:
            matches = fuzzy_search(query, choices, limit=len(choices), cutoff=cutoff)
        else:
            matches = _fuzzy_fallback(query, choices, cutoff=cutoff)
        return [all_rows[idx] for _, _, idx in matches]

    def get_by_id(self, supplier_id: int) -> SupplierRow | None:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(f"""
                SELECT {", ".join(_SUPPLIER_FIELDS)}
                FROM suppliers WHERE id = ?
            """, (supplier_id,))
            row = cur.fetchone()
        return _supplier_row(row) if row else None

    def create(self, supplier: dict[str, Any]) -> int:
        """Insert a supplier; ``ValueError`` on duplicate name."""
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        try:
            with SqliteWALConnection(self._db_path) as (conn, cur):
                cur.execute("BEGIN TRANSACTION")
                cur.execute("""
                    INSERT INTO suppliers
                        (name, contact_name, contact_email, contact_phone, address,
                         tax_id, preferred, sku, min_stock_level, lead_time_days,
                         edi_endpoint, performance_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    supplier["name"], supplier.get("contact_name", ""),
                    supplier.get("contact_email", ""), supplier.get("contact_phone", ""),
                    supplier.get("address", ""), supplier.get("tax_id", ""),
                    int(supplier.get("preferred", 0) or 0),
                    supplier.get("sku", ""), int(supplier.get("min_stock_level", 0) or 0),
                    int(supplier.get("lead_time_days", 0) or 0),
                    supplier.get("edi_endpoint", ""), supplier.get("performance_notes", ""),
                ))
                supplier_id = cur.lastrowid
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Supplier '{supplier['name']}' already exists")

        audit_log.log_action("SUPPLIER_CREATE",
                             f"Supplier '{supplier['name']}' (id={supplier_id}) created.")
        self._observer.notify("suppliers_changed",
                              {"action": "create", "supplier_id": supplier_id})
        return supplier_id

    def update(self, supplier_id: int, supplier: dict[str, Any]) -> bool:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        try:
            with SqliteWALConnection(self._db_path) as (conn, cur):
                cur.execute("BEGIN TRANSACTION")
                cur.execute("""
                    UPDATE suppliers SET
                        name = ?, contact_name = ?, contact_email = ?, contact_phone = ?,
                        address = ?, tax_id = ?, preferred = ?, sku = ?, min_stock_level = ?,
                        lead_time_days = ?, edi_endpoint = ?, performance_notes = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (
                    supplier["name"], supplier.get("contact_name", ""),
                    supplier.get("contact_email", ""), supplier.get("contact_phone", ""),
                    supplier.get("address", ""), supplier.get("tax_id", ""),
                    int(supplier.get("preferred", 0) or 0),
                    supplier.get("sku", ""), int(supplier.get("min_stock_level", 0) or 0),
                    int(supplier.get("lead_time_days", 0) or 0),
                    supplier.get("edi_endpoint", ""), supplier.get("performance_notes", ""),
                    supplier_id,
                ))
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Supplier '{supplier['name']}' already exists")

        audit_log.log_action("SUPPLIER_UPDATE",
                             f"Supplier id={supplier_id} ('{supplier['name']}') updated.")
        self._observer.notify("suppliers_changed",
                              {"action": "update", "supplier_id": supplier_id})
        return True

    def delete(self, supplier_id: int) -> bool:
        """Delete a supplier; ``ValueError`` if it is flagged preferred."""
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("SELECT preferred, name FROM suppliers WHERE id = ?", (supplier_id,))
            row = cur.fetchone()
            if row is None:
                return False
            if row[0]:
                raise ValueError(
                    f"Preferred supplier '{row[1]}' cannot be deleted; demote first")
            cur.execute("BEGIN TRANSACTION")
            cur.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
            conn.commit()

        audit_log.log_action("SUPPLIER_DELETE",
                             f"Supplier id={supplier_id} ('{row[1]}') deleted.")
        self._observer.notify("suppliers_changed",
                              {"action": "delete", "supplier_id": supplier_id})
        return True

    def set_preferred(self, supplier_id: int) -> None:
        """Promote one supplier to preferred, clearing all others."""
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("UPDATE suppliers SET preferred = 0")
            cur.execute(
                "UPDATE suppliers SET preferred = 1, updated_at = datetime('now') WHERE id = ?",
                (supplier_id,),
            )
            conn.commit()
        audit_log.log_action("SUPPLIER_PREFER",
                             f"Supplier id={supplier_id} marked preferred.")
        self._observer.notify("suppliers_changed",
                              {"action": "preferred", "supplier_id": supplier_id})


# ═════════════════════════════════════════════════════════════════════════════
#  PoCrudManager  (§5.5)
# ═════════════════════════════════════════════════════════════════════════════


class PoCrudManager:
    """CRUD over ``purchase_orders`` + ``po_items`` via ``SqliteWALConnection``.

    Lifecycle state machine enforced here AND in the DB layer:
    ``Draft → Submitted → Received → Closed``.  The ``Received`` transition
    delegates to ``database.receive_po_items`` (§6 flow, implemented in the
    database layer with its own retry loop on ``sqlite3.OperationalError``).
    """

    def __init__(self, db_path: str | None = None,
                 supplier_mgr: SupplierCrudManager | None = None,
                 observer: SupplierObserver | None = None) -> None:
        self._db_path: str = db_path or database.get_db_path()
        self._supplier_mgr: SupplierCrudManager = supplier_mgr or SupplierCrudManager(
            db_path=self._db_path)
        self._observer: SupplierObserver = observer or SupplierObserver()

    @property
    def observer(self) -> SupplierObserver:
        return self._observer

    def load_all(self, status_filter: str | None = None) -> list[PoRow]:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        cols = ", ".join(f"purchase_orders.{f}" for f in _PO_FIELDS)
        sql = f"""
            SELECT {cols}
            FROM purchase_orders
            LEFT JOIN suppliers s ON s.id = purchase_orders.vendor_id
        """
        params: tuple[Any, ...] = ()
        if status_filter:
            sql += " WHERE purchase_orders.status = ?"
            params = (status_filter,)
        sql += " ORDER BY purchase_orders.created_at DESC"
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_po_row(r) for r in rows]

    def get_by_id(self, po_id: int) -> tuple[PoRow | None, list[PoItemRow]]:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(f"""
                SELECT {", ".join(_PO_FIELDS)}
                FROM purchase_orders WHERE id = ?
            """, (po_id,))
            po_row = cur.fetchone()
            cur.execute(f"""
                SELECT {", ".join(_PO_ITEM_FIELDS)}
                FROM po_items WHERE po_id = ? ORDER BY line_number ASC
            """, (po_id,))
            item_rows = cur.fetchall()
        po = _po_row(po_row) if po_row else None
        items = [_po_item_row(r) for r in item_rows]
        return po, items

    def create(self, vendor_id: int, notes: str = "") -> int:
        """Create an empty Draft PO (line items added via ``add_item``)."""
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        po_number = database.get_next_po_number()
        vendor_name = ""
        sup = self._supplier_mgr.get_by_id(vendor_id)
        if sup is not None:
            vendor_name = sup.get("name", "") or ""
        try:
            with SqliteWALConnection(self._db_path) as (conn, cur):
                cur.execute("BEGIN TRANSACTION")
                cur.execute("""
                    INSERT INTO purchase_orders
                        (po_number, vendor_id, vendor_name, status, notes)
                    VALUES (?, ?, ?, 'Draft', ?)
                """, (po_number, vendor_id, vendor_name, notes))
                po_id = cur.lastrowid
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"PO number {po_number} already exists")

        audit_log.log_action("PO_CREATE", f"PO #{po_number} (id={po_id}) created for "
                            f"vendor '{vendor_name}'.")
        self._observer.notify("purchase_orders_changed",
                              {"action": "create", "po_id": po_id})
        return po_id

    def add_item(self, po_id: int, item: dict[str, Any]) -> int:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        qty = int(item.get("quantity", 0))
        unit_price = float(item.get("unit_price", 0.0))
        line_total = qty * unit_price
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("SELECT COALESCE(MAX(line_number), 0) FROM po_items WHERE po_id = ?",
                        (po_id,))
            max_line = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO po_items
                    (po_id, line_number, product_name, vendor_sku, quantity, unit_price,
                     line_total, mfg_barcode, expiry_date, mfg_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (po_id, max_line + 1, item.get("product_name", ""),
                  item.get("vendor_sku", ""), qty, unit_price, line_total,
                  item.get("mfg_barcode", ""), item.get("expiry_date", ""),
                  item.get("mfg_date", "")))
            item_id = cur.lastrowid
            conn.commit()
        self.update_totals(po_id)
        self._observer.notify("po_item_added",
                              {"action": "add", "po_id": po_id, "item_id": item_id})
        return item_id

    def update_item(self, item_id: int, quantity: int, unit_price: float) -> bool:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        line_total = quantity * unit_price
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("""
                UPDATE po_items SET quantity = ?, unit_price = ?, line_total = ?
                WHERE id = ?
            """, (quantity, unit_price, line_total, item_id))
            cur.execute("SELECT po_id FROM po_items WHERE id = ?", (item_id,))
            po_id = cur.fetchone()[0]
            conn.commit()
        self.update_totals(po_id)
        self._observer.notify("purchase_orders_changed",
                              {"action": "update_item", "item_id": item_id})
        return True

    def delete_item(self, item_id: int) -> bool:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("SELECT po_id, line_number FROM po_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                return False
            po_id, line_num = row
            cur.execute("DELETE FROM po_items WHERE id = ?", (item_id,))
            cur.execute("""
                UPDATE po_items SET line_number = line_number - 1
                WHERE po_id = ? AND line_number > ?
            """, (po_id, line_num))
            conn.commit()
        self.update_totals(po_id)
        self._observer.notify("po_item_removed",
                              {"action": "delete", "item_id": item_id})
        return True

    def update_totals(self, po_id: int) -> None:
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("""
                UPDATE purchase_orders
                SET subtotal = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = ?), 0),
                    tax_amount = 0.0,
                    total_cost = COALESCE((SELECT SUM(line_total) FROM po_items WHERE po_id = ?), 0)
                WHERE id = ?
            """, (po_id, po_id, po_id))
            conn.commit()
        audit_log.log_action("PO_TOTALS", f"PO id={po_id} totals recomputed.")

    def transition(self, po_id: int, new_status: str,
                   receipt_data: dict[str, Any] | None = None) -> Any:
        """Validate + apply a lifecycle transition.

        Legal legs: Draft→Submitted, Submitted→Draft, Submitted→Received,
        Received→Closed.  The ``Received`` leg triggers the inventory-receipt
        path; when ``receipt_data`` is supplied (per-item received qty / lot /
        expiry from the receive wizard) it is honoured via
        ``_receive_with_data``, otherwise the default full-receipt
        ``database.receive_po_items`` is used.  All other legs just flip the
        status timestamp columns.  Raises ``ValueError`` on an illegal
        transition.
        """
        po, _ = self.get_by_id(po_id)
        if po is None:
            raise ValueError(f"Purchase order {po_id} not found")
        current: str = po["status"] or "Draft"
        if new_status == current:
            return True
        if new_status not in PO_LEGAL_TRANSITIONS.get(current, set()):
            raise ValueError(f"Illegal PO transition: {current} → {new_status}")

        if new_status == "Received":
            # Inventory-update path (§6) — owns its own retry loop + audit.
            if receipt_data:
                self._receive_with_data(po_id, receipt_data)
            else:
                database.receive_po_items(po_id)
            self._observer.notify("purchase_orders_changed",
                                  {"action": "receive", "po_id": po_id, "po_number": po.get("po_number")})
            return True

        ts_col = {"Submitted": "submitted_at", "Draft": "created_at",
                  "Closed": "closed_at"}.get(new_status)
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            if ts_col:
                cur.execute(
                    f"UPDATE purchase_orders SET status = ?, {ts_col} = datetime('now') WHERE id = ?",
                    (new_status, po_id),
                )
            else:
                cur.execute("UPDATE purchase_orders SET status = ? WHERE id = ?",
                            (new_status, po_id))
            conn.commit()

        audit_log.log_action("PO_STATUS",
                             f"PO id={po_id} ({po.get('po_number')}) status changed: "
                             f"{current} → {new_status}.")
        self._observer.notify("purchase_orders_changed",
                              {"action": "transition", "po_id": po_id,
                               "old": current, "new": new_status})
        return True

    def _receive_with_data(self, po_id: int,
                           receipt_data: dict[str, Any]) -> dict[str, Any]:
        """Manager-level §6 receipt honoring per-item received qty / lot / expiry.

        ``receipt_data`` maps ``str(item_id)`` -> ``{"received_qty": int,
        "lot_number": str, "expiry_date": str}``; ``received_qty`` falls back
        to the PO line quantity when absent.  Mirrors ``database.receive_po_items``
        but is parameterized by the wizard's per-item capture (partial receipts
        + per-item expiry override).  The duplicate inventory-marking block is
        intentional — ``database.py`` is a sealed layer, so the receipt-data path
        lives here.  Returns the receive-summary dict (the ``purchase_orders_changed``
        notification is emitted by ``transition``).
        """
        import json
        if SqliteWALConnection is None:
            raise RuntimeError("SqliteWALConnection unavailable")
        po, _ = self.get_by_id(po_id)
        if po is None:
            raise ValueError(f"Purchase order {po_id} not found")
        vendor_name = po.get("vendor_name") or ""
        po_number = po.get("po_number") or ""
        date_received = datetime.now().strftime("%Y-%m-%d")

        # Line items WITH mfg metadata columns (get_by_id omits mfg_barcode/expiry/mfg_date).
        items: list[dict[str, Any]] = []
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(
                "SELECT id, product_name, quantity, unit_price, line_total, "
                "mfg_barcode, expiry_date, mfg_date FROM po_items WHERE po_id = ? "
                "ORDER BY line_number",
                (po_id,),
            )
            for (item_id, pname, qty, up, lt, mfg_bc, exp, mfg_date) in cur.fetchall():
                rd = receipt_data.get(str(item_id)) or {}
                try:
                    received_qty = int(rd.get("received_qty", qty))
                except (TypeError, ValueError):
                    raise ValueError(i18n.t("must_be_number"))
                if received_qty <= 0:
                    raise ValueError(
                        f"{i18n.t('product_name')} '{pname}': {i18n.t('qty_gt_zero')}")
                items.append({
                    "item_id": item_id, "product_name": pname,
                    "received_qty": received_qty, "unit_price": float(up or 0.0),
                    "line_total": float(lt or 0.0), "mfg_barcode": mfg_bc or "",
                    "expiry_date": str(rd.get("expiry_date") or exp or ""),
                    "mfg_date": mfg_date or "",
                    "lot_number": str(rd.get("lot_number") or ""),
                })
        if not items:
            raise ValueError(f"PO #{po_number} has no line items to receive")

        total_qty = sum(it["received_qty"] for it in items)
        all_barcodes = generate_batch_barcodes(vendor_name, total_qty)
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                offset = 0
                for it in items:
                    qc = it["received_qty"]
                    item_barcodes = all_barcodes[offset:offset + qc]
                    offset += qc
                    database.receive_inventory_atomically(
                        vendor_name=vendor_name,
                        product_name=it["product_name"],
                        date_received=date_received,
                        quantity=qc,
                        total_cost=it["line_total"],
                        tpl_price=it["unit_price"],
                        tpl_mfg_barcode=it["mfg_barcode"],
                        tpl_expiry=it["expiry_date"],
                        tpl_mfg_date=it["mfg_date"],
                        barcode_generator=barcode_logic.generate_internal_barcode,
                        pre_generated_barcodes=item_barcodes,
                    )
                with SqliteWALConnection(self._db_path) as (conn, cur):
                    cur.execute("BEGIN TRANSACTION")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    off2 = 0
                    for it in items:
                        qc = it["received_qty"]
                        item_barcodes = all_barcodes[off2:off2 + qc]
                        off2 += qc
                        cur.execute(
                            "UPDATE po_items SET status = 'Received', received_at = ?, "
                            "internal_barcodes = ? WHERE id = ?",
                            (now, json.dumps(item_barcodes), it["item_id"]),
                        )
                    cur.execute(
                        "UPDATE purchase_orders SET status = 'Received', "
                        "received_at = datetime('now') WHERE id = ?",
                        (po_id,),
                    )
                    conn.commit()
                audit_log.log_action(
                    "PO_RECEIVE",
                    f"PO #{po_number} (id={po_id}) received via wizard: "
                    f"{total_qty} box(es) for {len(items)} item(s).")
                return {"po_number": po_number, "vendor_name": vendor_name,
                        "box_count": total_qty, "items_received": len(items)}
            except ValueError as exc:
                last_error = exc
                break
            except sqlite3.OperationalError as exc:
                delay = 0.1 * (2 ** attempt)
                log.warning("_receive_with_data attempt %d/%d failed: %s",
                            attempt + 1, max_retries, exc)
                last_error = exc
                time.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to receive PO #{po_id}")

    def compute_low_stock_groups(self) -> list[dict[str, Any]]:
        """Group below-reorder-threshold products by their preferred supplier.

        Returns ``[{"supplier": SupplierRow | None, "vendor_name": str,
        "items": [{"name","current_qty","threshold","suggested_qty",
                   "wholesale_price"}]}]``.  ``supplier`` is None when no
        registered supplier matches the product's ``vendor_name``; the caller
        (``auto_reorder``) creates an on-demand supplier for those.
        """
        low_rows = database.get_products_below_reorder_threshold()
        if not low_rows:
            return []

        suppliers = self._supplier_mgr.load_all()
        preferred_by_name: dict[str, SupplierRow] = {}
        all_by_name: dict[str, list[SupplierRow]] = defaultdict(list)
        for sup in suppliers:
            all_by_name[sup["name"]].append(sup)
            if sup.get("preferred"):
                preferred_by_name[sup["name"]] = sup

        groups: list[dict[str, Any]] = []
        for name, qty, min_threshold, vendor_name, wholesale_price in low_rows:
            sup = preferred_by_name.get(vendor_name)
            if sup is None:
                candidates = all_by_name.get(vendor_name)
                sup = candidates[0] if candidates else None
            key = (sup["name"] if sup else None) or vendor_name
            entry = next((g for g in groups if (g["supplier"]["name"] if g["supplier"] else None) == key), None)
            if entry is None:
                entry = {"supplier": sup, "vendor_name": vendor_name, "items": []}
                groups.append(entry)
            buffer_n = max(int(min_threshold or 0), 1)
            suggested_qty = int(min_threshold or 0) + buffer_n
            entry["items"].append({
                "name": name,
                "current_qty": int(qty or 0),
                "threshold": int(min_threshold or 0),
                "suggested_qty": suggested_qty,
                "wholesale_price": float(wholesale_price or 0.0),
            })
        return groups

    def auto_reorder(self) -> dict[str, Any]:
        """Draft a consolidated PO for every low-stock supplier group.

        Unassigned vendors get an on-demand supplier record (preferred=0).
        Returns ``{"po_count","item_count","low_stock_count","drafts": [...]}``.
        """
        groups = self.compute_low_stock_groups()
        drafts: list[dict[str, Any]] = []
        po_count = 0
        item_count = 0
        for group in groups:
            sup = group["supplier"]
            vendor_name = group["vendor_name"]
            if sup is None:
                sup_id = self._supplier_mgr.create({
                    "name": vendor_name, "preferred": 0,
                    "min_stock_level": 0, "lead_time_days": 0,
                    "performance_notes": "Unassigned (auto-reorder)",
                })
                sup = self._supplier_mgr.get_by_id(sup_id) or SupplierRow(
                    name=vendor_name, preferred=0)
            vendor_id = int(sup["id"]) if sup.get("id") else 0
            line_items: list[dict[str, Any]] = []
            for it in group["items"]:
                line_items.append({
                    "product_name": it["name"],
                    "quantity": it["suggested_qty"],
                    "unit_price": it["wholesale_price"],
                    "vendor_sku": sup.get("sku", "") or "",
                    "mfg_barcode": "", "expiry_date": "", "mfg_date": "",
                })
            po_id = self.create(vendor_id, notes=i18n.t("generate_auto_reorder"))
            for li in line_items:
                self.add_item(po_id, li)
                item_count += 1
            po, _ = self.get_by_id(po_id)
            drafts.append({"po_id": po_id, "po_number": po["po_number"] if po else ""})
            po_count += 1

        audit_log.log_action("AUTO_REORDER",
                             f"Auto-reorder drafted {po_count} PO(s), {item_count} item(s).")
        if po_count:
            self._observer.notify("purchase_orders_changed",
                                  {"action": "auto_reorder", "drafts": drafts})
        return {
            "po_count": po_count,
            "item_count": item_count,
            "low_stock_count": len(groups),
            "drafts": drafts,
        }

# ═════════════════════════════════════════════════════════════════════════════
#  PART 2: Data Entry Dialogs (§5.6–§5.8)
#  Modal ``ctk.CTkToplevel`` bridges between user input and the CRUD managers.
# ═════════════════════════════════════════════════════════════════════════════


class SupplierDialog(ctk.CTkToplevel):
    """Create or Update a Supplier — modal bridge to ``SupplierCrudManager`` (§5.6)."""

    def __init__(self, parent: Any, manager: SupplierCrudManager,
                 supplier_id: int | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._supplier_id = supplier_id
        is_edit = supplier_id is not None
        self.title(i18n.t("edit_supplier") if is_edit else i18n.t("add_supplier"))
        self.geometry("420x520")
        self.transient(parent)
        self._form = ctk.CTkFrame(self)
        self._form.pack(fill="both", expand=True, padx=20, pady=20)
        self._form.grid_columnconfigure(1, weight=1)

        self._fields: list[tuple[str, str, bool]] = [
            ("name", i18n.t("name"), True),
            ("contact_name", i18n.t("contact_name"), False),
            ("contact_phone", i18n.t("contact_phone"), False),
            ("contact_email", i18n.t("contact_email"), False),
            ("address", i18n.t("supplier_address"), False),
            ("tax_id", i18n.t("tax_id"), False),
        ]
        self._entries: dict[str, ctk.CTkEntry] = {}
        for row_idx, (key, label, required) in enumerate(self._fields):
            ctk.CTkLabel(self._form, text=f"{label}:{' *' if required else ''}") \
                .grid(row=row_idx, column=0, padx=10, pady=6, sticky="w")
            entry = ctk.CTkEntry(self._form, placeholder_text=label)
            entry.grid(row=row_idx, column=1, padx=10, pady=6, sticky="ew")
            self._entries[key] = entry

        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btns, text=i18n.t("save"), width=100,
                      command=self._on_save).pack(side="left", padx=5)
        ctk.CTkButton(btns, text=i18n.t("cancel"), width=100,
                      command=self._on_cancel).pack(side="right", padx=5)

        if is_edit:
            data = manager.get_by_id(supplier_id)
            if data:
                self._prefill(dict(data))
        self._entries["name"].focus_set()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _prefill(self, data: dict[str, Any]) -> None:
        for key, _, _ in self._fields:
            self._entries[key].delete(0, "end")
            self._entries[key].insert(0, str(data.get(key, "") or ""))

    def _on_save(self) -> None:
        supplier: dict[str, Any] = {
            key: self._entries[key].get() for key, _, _ in self._fields
        }
        if not supplier["name"].strip():
            messagebox.showerror(i18n.t("error"), i18n.t("all_fields_required"))
            return
        try:
            if self._supplier_id is None:
                self._manager.create(supplier)
            else:
                self._manager.update(self._supplier_id, supplier)
        except ValueError as exc:
            messagebox.showerror(i18n.t("error"), str(exc))
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


class PoItemDialog(ctk.CTkToplevel):
    """Add or edit a PO line item — modal bridge to ``PoCrudManager`` (§5.7)."""

    def __init__(self, parent: Any, manager: PoCrudManager, po_id: int,
                 item_id: int | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._po_id = po_id
        self._item_id = item_id
        is_edit = item_id is not None
        self.title(i18n.t("po_item_dialog_title_edit") if is_edit
                   else i18n.t("po_item_dialog_title_add"))
        self.geometry("460x340")
        self.transient(parent)

        self._form = ctk.CTkFrame(self)
        self._form.pack(fill="both", expand=True, padx=20, pady=20)
        self._form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._form, text=i18n.t("product_id") + ":") \
            .grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self._product_id = ctk.CTkEntry(self._form, placeholder_text=i18n.t("product_id"))
        self._product_id.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        ctk.CTkButton(self._form, text=i18n.t("look_up"), width=80,
                      command=self._on_lookup) \
            .grid(row=0, column=2, padx=10, pady=6)

        ctk.CTkLabel(self._form, text=i18n.t("product_name") + ":") \
            .grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self._product_name = ctk.CTkEntry(self._form, placeholder_text=i18n.t("product_name"))
        self._product_name.grid(row=1, column=1, columnspan=2, padx=10, pady=6, sticky="ew")
        self._product_name.configure(state="disabled")

        ctk.CTkLabel(self._form, text=i18n.t("quantity") + ":") \
            .grid(row=2, column=0, padx=10, pady=6, sticky="w")
        self._qty_var = ctk.StringVar(value="1")
        self._qty = ctk.CTkEntry(self._form, width=120, textvariable=self._qty_var)
        self._qty.grid(row=2, column=1, padx=10, pady=6, sticky="w")
        self._qty_var.trace_add("write", self._recalc)

        ctk.CTkLabel(self._form, text=i18n.t("unit_cost") + ":") \
            .grid(row=3, column=0, padx=10, pady=6, sticky="w")
        self._price_var = ctk.StringVar(value="0.00")
        self._price = ctk.CTkEntry(self._form, width=120, textvariable=self._price_var)
        self._price.grid(row=3, column=1, padx=10, pady=6, sticky="w")
        self._price_var.trace_add("write", self._recalc)

        self._line_total_lbl = ctk.CTkLabel(self._form, text=f"{i18n.t('line_total')}: 0.00")
        self._line_total_lbl.grid(row=4, column=0, columnspan=2, padx=10, pady=6, sticky="w")

        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btns, text=i18n.t("save"), width=100, command=self._on_save) \
            .pack(side="left", padx=5)
        ctk.CTkButton(btns, text=i18n.t("cancel"), width=100, command=self._on_cancel) \
            .pack(side="right", padx=5)

        if is_edit:
            _, items = manager.get_by_id(po_id)
            target = next((it for it in items if it["id"] == item_id), None)
            if target:
                item = dict(target)
                self._product_id.insert(0, item.get("mfg_barcode", "") or "")
                self._product_name.configure(state="normal")
                self._product_name.insert(0, item.get("product_name", "") or "")
                self._product_name.configure(state="disabled")
                self._qty_var.set(str(item.get("quantity", 1)))
                self._price_var.set(f"{item.get('unit_price', 0.0):.2f}")
        self._recalc()
        self._product_id.focus_set()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _recalc(self, *_: Any) -> None:
        try:
            qty = int(self._qty_var.get())
        except ValueError:
            qty = 0
        try:
            price = float(self._price_var.get())
        except ValueError:
            price = 0.0
        self._line_total_lbl.configure(
            text=f"{i18n.t('line_total')}: {qty * price:.2f}")

    def _on_lookup(self) -> None:
        """Look up product info by ID/barcode via ndc_dictionary and populate the form."""
        query = self._product_id.get().strip()
        if not query:
            messagebox.showwarning(i18n.t("look_up"),
                                   i18n.t("enter_product_id_to_lookup"), parent=self)
            return

        if not HAS_NDC:
            messagebox.showwarning(i18n.t("look_up"),
                                   i18n.t("lookup_not_implemented"), parent=self)
            return

        try:
            # Strategy 1: manufacturer barcode lookup
            result = barcode_lookup(query)
            if result is None:
                # Strategy 2: NDC code lookup
                result = ndc_lookup(query)
            if result is None:
                # Strategy 3: fuzzy name match
                matches = name_lookup(query)
                if matches:
                    result = matches[0]

            if result:
                self._product_id.delete(0, "end")
                self._product_id.insert(0, result.get("manufacturer_barcode") or result.get("ndc_code", ""))

                self._product_name.configure(state="normal")
                self._product_name.delete(0, "end")
                self._product_name.insert(0, result.get("drug_name", ""))
                self._product_name.configure(state="disabled")

                awp = result.get("awp")
                if awp:
                    self._price_var.set(f"{float(awp):.2f}")

                self._recalc()
            else:
                messagebox.showinfo(i18n.t("look_up"),
                                    i18n.t("product_not_found"), parent=self)
        except Exception as e:
            log.error("PoItemDialog._on_lookup failed: %s", e)
            messagebox.showerror(i18n.t("error"),
                                 f"{i18n.t('lookup_failed')}: {e}", parent=self)

    def _on_save(self) -> None:
        try:
            qty = int(self._qty_var.get())
            price = float(self._price_var.get())
        except ValueError:
            messagebox.showerror(i18n.t("error"), i18n.t("must_be_number"))
            return
        if qty <= 0:
            messagebox.showerror(i18n.t("error"), i18n.t("qty_gt_zero"))
            return
        if price < 0:
            messagebox.showerror(i18n.t("error"), i18n.t("invalid_price"))
            return
        product_id = self._product_id.get().strip()
        product_name = self._product_name.get().strip() or product_id or "—"
        try:
            if self._item_id is None:
                self._manager.add_item(self._po_id, {
                    "product_name": product_name,
                    "vendor_sku": "",
                    "quantity": qty,
                    "unit_price": price,
                    "line_total": qty * price,
                    "mfg_barcode": product_id,
                    "expiry_date": "",
                    "mfg_date": "",
                })
            else:
                self._manager.update_item(self._item_id, qty, price)
        except ValueError as exc:
            messagebox.showerror(i18n.t("error"), str(exc))
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


class ReceivePoDialog(ctk.CTkToplevel):
    """Wizard: transition Submitted -> Received with per-item receipt data (§5.8)."""

    def __init__(self, parent: Any, manager: PoCrudManager, po_id: int) -> None:
        super().__init__(parent)
        self._manager = manager
        self._po_id = po_id
        self.title(i18n.t("receive_po_wizard"))
        self.geometry("620x560")
        self.transient(parent)

        po, items = manager.get_by_id(po_id)
        self._items = items or []
        po_number = po.get("po_number", "") if po else f"#{po_id}"
        ctk.CTkLabel(self, text=f"{i18n.t('receive_po_wizard')} — {po_number}") \
            .pack(padx=20, pady=(20, 10), anchor="w")

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=20, pady=10)

        self._rows: list[tuple[int, ctk.CTkEntry, ctk.CTkEntry, ctk.CTkEntry]] = []
        for it in self._items:
            item = dict(it)
            item_id = int(item.get("id") or 0)
            frame = ctk.CTkFrame(self._scroll)
            frame.pack(fill="x", pady=6)
            ctk.CTkLabel(frame, text=item.get("product_name", "") or "—") \
                .pack(anchor="w")
            ctk.CTkLabel(frame,
                         text=f"{i18n.t('expected_qty')}: {item.get('quantity', 0)}",
                         text_color=("gray60", "gray70")) \
                .pack(anchor="w")
            bot = ctk.CTkFrame(frame)
            bot.pack(fill="x", pady=(4, 0), anchor="w")
            ctk.CTkLabel(bot, text=i18n.t("received_qty")) \
                .pack(side="left", padx=(0, 4))
            rcv = ctk.CTkEntry(bot, width=80, justify="center")
            rcv.insert(0, str(item.get("quantity", 0)))
            rcv.pack(side="left", padx=4)
            ctk.CTkLabel(bot, text=i18n.t("lot_number")) \
                .pack(side="left", padx=(14, 4))
            lot = ctk.CTkEntry(bot, width=110)
            lot.pack(side="left", padx=4)
            ctk.CTkLabel(bot, text=i18n.t("expiry_date")) \
                .pack(side="left", padx=(14, 4))
            exp = ctk.CTkEntry(bot, width=115)
            exp.insert(0, item.get("expiry_date", "") or "")
            exp.pack(side="left", padx=4)
            self._rows.append((item_id, rcv, lot, exp))

        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btns, text=i18n.t("confirm_receipt"), width=160,
                      command=self._on_confirm) \
            .pack(anchor="e")
        ctk.CTkButton(btns, text=i18n.t("cancel"), width=100,
                      command=self._on_cancel) \
            .pack(anchor="e", padx=(8, 0))

        self.focus_set()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_confirm(self) -> None:
        receipt_data: dict[str, dict[str, Any]] = {}
        for item_id, rcv, lot, exp in self._rows:
            raw = rcv.get().strip()
            try:
                received_qty = int(raw) if raw else 0
            except ValueError:
                messagebox.showerror(i18n.t("error"), i18n.t("must_be_number"))
                return
            if received_qty < 0:
                messagebox.showerror(i18n.t("error"), i18n.t("qty_gt_zero"))
                return
            expiry = exp.get().strip()
            if expiry:
                try:
                    datetime.strptime(expiry, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror(i18n.t("error"), i18n.t("invalid_date"))
                    return
            receipt_data[str(item_id)] = {
                "received_qty": received_qty,
                "lot_number": lot.get().strip(),
                "expiry_date": expiry,
            }
        try:
            self._manager.transition(self._po_id, "Received",
                                     receipt_data=receipt_data)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            messagebox.showerror(i18n.t("error"), str(exc))
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
#  PART 3: Dual-Pane Management Frame (§5.8) + tab setup
# ═════════════════════════════════════════════════════════════════════════════


class SupplierOrderManagementFrame(ctk.CTkFrame):
    """Dual-pane Supplier & Purchase-Order management surface (§5.8).

    Left pane  — Suppliers Treeview + Add / Edit / Delete / Set-Preferred.
    Right pane — Purchase Orders Treeview (status-filtered via CTkOptionMenu)
                 + New PO / Auto-Reorder / Edit PO-Items / Receive Order.

    Both panes auto-refresh through the shared ``SupplierObserver`` whenever a
    CRUD manager mutates state, so dialogs close → trees reflect the change.
    """

    def __init__(self, parent: Any, app: Any = None, db_path: str | None = None,
                 **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.app = app
        self._db_path = db_path

        # Single observer shared by both managers + this frame.
        self._observer = SupplierObserver()
        self._observer.register(self._on_observer_event)
        self._supplier_mgr = SupplierCrudManager(db_path=db_path, observer=self._observer)
        self._po_mgr = PoCrudManager(db_path=db_path, supplier_mgr=self._supplier_mgr,
                                     observer=self._observer)

        self._build_toolbar()
        self._paned = ttk.PanedWindow(self, orient="horizontal")
        self._paned.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self._left = ctk.CTkFrame(self._paned, fg_color="transparent")
        self._right = ctk.CTkFrame(self._paned, fg_color="transparent")
        self._paned.add(self._left, weight=1)
        self._paned.add(self._right, weight=1)
        self._build_left(self._left)
        self._build_right(self._right)

        self._status_bar = ctk.CTkLabel(self, text="", anchor="w")
        self._status_bar.pack(fill="x", padx=10, pady=(0, 6))

        self.refresh()

    # ── observer ────────────────────────────────────────────────────────
    def _on_observer_event(self, event: str, data: dict[str, Any]) -> None:
        try:
            if event == "suppliers_changed":
                self.refresh_suppliers()
            elif event in ("purchase_orders_changed", "po_item_added",
                           "po_item_removed"):
                self.refresh_pos()
            self._update_status_bar()
        except Exception as exc:  # noqa: BLE001 — observer isolation
            log.error("SupplierOrderManagementFrame observer error: %s", exc)

    # ── toolbar ────────────────────────────────────────────────────────
    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(bar, text=i18n.t("supplier_order_title"),
                     font=ctk.CTkFont(weight="bold")).pack(side="left", anchor="w")
        ctk.CTkButton(bar, text=i18n.t("refresh"), width=90,
                      command=self.refresh).pack(side="right", padx=4)

    # ── left pane (suppliers) ───────────────────────────────────────────
    def _build_left(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(parent, text=i18n.t("suppliers"),
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        tree_container = ctk.CTkFrame(parent)
        tree_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        tree_container.grid_propagate(False)
        tree_container.configure(height=220)
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)
        self._tree_suppliers = ttk.Treeview(
            tree_container, columns=("id", "name", "contact", "phone"),
            show="headings", height=12)
        for col, key in (("id", "id"), ("name", "name"),
                         ("contact", "contact_name"), ("phone", "contact_phone")):
            self._tree_suppliers.heading(col, text=i18n.t(key))
            self._tree_suppliers.column(col, width=120, minwidth=60)
        self._tree_suppliers.column("id", width=50)
        vsb = ttk.Scrollbar(tree_container, orient="vertical",
                             command=self._tree_suppliers.yview)
        self._tree_suppliers.configure(yscrollcommand=vsb.set)
        self._tree_suppliers.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree_suppliers.tag_configure("preferred", background="#fff9c4")
        self._tree_suppliers.bind("<<TreeviewSelect>>", self._on_supplier_select)

        btns = ctk.CTkFrame(parent)
        btns.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(btns, text=i18n.t("add_supplier"),
                      command=self._on_add_supplier).pack(side="left", padx=4)
        self._btn_edit = ctk.CTkButton(btns, text=i18n.t("edit_supplier"),
                                       command=self._on_edit_supplier,
                                       state="disabled")
        self._btn_edit.pack(side="left", padx=4)
        self._btn_del = ctk.CTkButton(btns, text=i18n.t("delete_supplier"),
                                      command=self._on_delete_supplier,
                                      state="disabled")
        self._btn_del.pack(side="left", padx=4)
        ctk.CTkButton(btns, text=i18n.t("set_preferred"),
                      command=self._on_set_preferred).pack(side="left", padx=4)

    # ── right pane (purchase orders) ────────────────────────────────────
    def _build_right(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(header, text=i18n.t("purchase_orders"),
                     font=ctk.CTkFont(weight="bold")).pack(side="left", anchor="w")
        self._filter_to_status: dict[str, str | None] = {
            i18n.t("all"): None,
            i18n.t("po_status_draft"): "Draft",
            i18n.t("submitted"): "Submitted",
            i18n.t("po_status_received"): "Received",
            i18n.t("closed"): "Closed",
            i18n.t("cancelled"): "Cancelled",
        }
        self._status_menu = ctk.CTkOptionMenu(
            header, width=150, values=list(self._filter_to_status.keys()),
            command=lambda *_: self.refresh_pos())
        self._status_menu.pack(side="right", anchor="e")

        tree_container = ctk.CTkFrame(parent)
        tree_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        tree_container.grid_propagate(False)
        tree_container.configure(height=220)
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)
        self._tree_pos = ttk.Treeview(
            tree_container,
            columns=("poid", "vendor", "date", "status", "total", "expected"),
            show="headings", height=12)
        for col, key in (("poid", "po_id"), ("vendor", "supplier"),
                         ("date", "date"), ("status", "status"),
                         ("total", "total"), ("expected", "expected_qty")):
            self._tree_pos.heading(col, text=i18n.t(key))
            self._tree_pos.column(col, width=120, minwidth=60)
        self._tree_pos.column("poid", width=100)
        self._tree_pos.column("date", width=110)
        self._tree_pos.column("status", width=90)
        vsb = ttk.Scrollbar(tree_container, orient="vertical",
                            command=self._tree_pos.yview)
        self._tree_pos.configure(yscrollcommand=vsb.set)
        self._tree_pos.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree_pos.bind("<<TreeviewSelect>>", self._on_po_select)

        btns = ctk.CTkFrame(parent)
        btns.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(btns, text=i18n.t("new_po"),
                      command=self._on_new_po).pack(side="left", padx=4)
        ctk.CTkButton(btns, text=i18n.t("auto_reorder"),
                      command=self._on_auto_reorder).pack(side="left", padx=4)
        self._btn_edit_po = ctk.CTkButton(btns, text=i18n.t("edit_po_items"),
                                          command=self._on_edit_po_items,
                                          state="disabled")
        self._btn_edit_po.pack(side="left", padx=4)
        self._btn_receive = ctk.CTkButton(btns, text=i18n.t("receive_po"),
                                          command=self._on_receive_order,
                                          state="disabled")
        self._btn_receive.pack(side="left", padx=4)

    # ── selection state ────────────────────────────────────────────────
    def _on_supplier_select(self, *_: Any) -> None:
        sel = bool(self._tree_suppliers.selection())
        self._btn_edit.configure(state=("normal" if sel else "disabled"))
        self._btn_del.configure(state=("normal" if sel else "disabled"))

    def _on_po_select(self, *_: Any) -> None:
        sel = self._tree_pos.selection()
        enabled = bool(sel)
        self._btn_edit_po.configure(state=("normal" if enabled else "disabled"))
        self._btn_receive.configure(state="disabled")
        if sel:
            po, _ = self._po_mgr.get_by_id(int(sel[0]))
            if po and po.get("status") == "Submitted":
                self._btn_receive.configure(state="normal")

    # ── button handlers ─────────────────────────────────────────────────
    def _on_add_supplier(self) -> None:
        SupplierDialog(self, self._supplier_mgr, None)

    def _on_edit_supplier(self) -> None:
        sel = self._tree_suppliers.selection()
        if not sel:
            return
        SupplierDialog(self, self._supplier_mgr, int(sel[0]))

    def _on_delete_supplier(self) -> None:
        sel = self._tree_suppliers.selection()
        if not sel:
            return
        try:
            self._supplier_mgr.delete(int(sel[0]))
        except ValueError as exc:
            messagebox.showerror(i18n.t("error"), str(exc))

    def _on_set_preferred(self) -> None:
        sel = self._tree_suppliers.selection()
        if not sel:
            messagebox.showwarning(i18n.t("set_preferred"), i18n.t("select_a_supplier"))
            return
        self._supplier_mgr.set_preferred(int(sel[0]))

    def _on_new_po(self) -> None:
        sel = self._tree_suppliers.selection()
        if not sel:
            messagebox.showwarning(i18n.t("new_po"), i18n.t("select_a_supplier"))
            return
        self._po_mgr.create(vendor_id=int(sel[0]), notes="")

    def _on_auto_reorder(self) -> None:
        self._po_mgr.auto_reorder()

    def _on_edit_po_items(self) -> None:
        sel = self._tree_pos.selection()
        if not sel:
            messagebox.showinfo(i18n.t("edit_po_items"), i18n.t("select_a_po"))
            return
        PoItemDialog(self, self._po_mgr, int(sel[0]), None)

    def _on_receive_order(self) -> None:
        sel = self._tree_pos.selection()
        if not sel:
            messagebox.showinfo(i18n.t("receive_po"), i18n.t("select_a_po"))
            return
        ReceivePoDialog(self, self._po_mgr, int(sel[0]))

    # ── data load ──────────────────────────────────────────────────────
    def refresh(self) -> None:
        self.refresh_suppliers()
        self.refresh_pos()
        self._update_status_bar()

    def refresh_suppliers(self) -> None:
        self._tree_suppliers.delete(*self._tree_suppliers.get_children())
        for s in self._supplier_mgr.load_all():
            tags = ("preferred",) if s.get("preferred") else ()
            self._tree_suppliers.insert("", "end", iid=str(s["id"]),
                                        values=(s["id"], s["name"],
                                                s.get("contact_name", ""),
                                                s.get("contact_phone", "")),
                                        tags=tags)
        self._on_supplier_select()

    def refresh_pos(self) -> None:
        self._tree_pos.delete(*self._tree_pos.get_children())
        status = self._filter_to_status.get(self._status_menu.get())
        for po in self._po_mgr.load_all(status_filter=status):
            _, items = self._po_mgr.get_by_id(po["id"])
            expected = sum(int(it.get("quantity", 0)) for it in items)
            self._tree_pos.insert("", "end", iid=str(po["id"]),
                                  values=(po.get("po_number", ""),
                                          po.get("vendor_name", ""),
                                          po.get("created_at", ""),
                                          i18n.t(PO_STATUS_KEYS.get(po["status"], "po_status_draft")),
                                          f"{po.get('total_cost', 0.0):.2f}",
                                          expected))
        self._on_po_select()

    def _update_status_bar(self) -> None:
        try:
            sups = len(self._supplier_mgr.load_all())
            pos = len(self._po_mgr.load_all())
            self._status_bar.configure(
                text=f"Suppliers: {sups}   Purchase Orders: {pos}")
        except Exception as exc:  # noqa: BLE001
            log.error("status bar update failed: %s", exc)

    # ── debug (§10.2) ──────────────────────────────────────────────────
    def _debug_layout_geometry(self) -> dict[str, Any]:
        """Print pane + Treeview runtime geometry to stdout (§5.8 / §10.2).

        Returns a dict of layout issues: zero-dimension Treeviews (crushed)
        and off-screen clipping (child x+width exceeds the top-level window).
        """
        self.update_idletasks()
        top = self.winfo_toplevel()
        root_w = top.winfo_width()
        results: dict[str, Any] = {"issues": []}
        for name, pane in (("left", self._left), ("right", self._right)):
            try:
                w, h = pane.winfo_width(), pane.winfo_height()
                print(f"[debug] {name} pane: {w}x{h}")
                if w + pane.winfo_x() > root_w and w > 0:
                    results["issues"].append(
                        f"{name} pane clipped off-screen "
                        f"(x+w={w + pane.winfo_x()} > root {root_w})")
            except Exception as exc:  # noqa: BLE001
                results["issues"].append(f"{name} pane size read failed: {exc}")
        for name, tree in (("suppliers", self._tree_suppliers),
                           ("pos", self._tree_pos)):
            try:
                print(f"[debug] {name} tree: {tree.winfo_geometry()} "
                      f"(w={tree.winfo_width()}, h={tree.winfo_height()})")
                if tree.winfo_width() <= 0 or tree.winfo_height() <= 0:
                    results["issues"].append(f"{name} tree has zero dimensions (crushed)")
                if tree.winfo_width() + tree.winfo_x() > root_w and tree.winfo_width() > 0:
                    results["issues"].append(f"{name} tree clipped off-screen")
            except Exception as exc:  # noqa: BLE001
                results["issues"].append(f"{name} tree read failed: {exc}")
        if results["issues"]:
            print("[debug] layout issues:", results["issues"])
        return results


def setup_supplier_order_tab(self: Any, parent: Any = None) -> SupplierOrderManagementFrame:
    """Attach the Supplier & Order Management tab.

    Caller (``main_app._wire_rx_extensions`` → ``_patched_init``) must first
    run ``self.tab_supplier_order = self.tab_view.add(i18n.t("supplier_order_title"))``;
    this mirrors ``setup_inventory_management_tab`` / ``setup_status_dashboard_tab``
    (TabViewCompat ``.add`` returns the content frame which we pack into).
    """
    if parent is None:
        parent = self.tab_supplier_order
    frame = SupplierOrderManagementFrame(parent, app=self, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    self.supplier_order_frame = frame
    self._refresh_supplier_order_tab = frame.refresh
    if hasattr(frame, "refresh"):
        frame.refresh()
    return frame
