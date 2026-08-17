"""
ui_inventory_management.py — Full CRUD inventory management interface for PharmacyPro.

Provides an InventoryManagementFrame with a central Treeview data grid for real-time
stock monitoring, supporting full CRUD operations on the serialized products table.
Includes visual indicators for low-stock and expiring-soon items, asynchronous
database operations via AsyncUI thread pool, SQLite WAL-mode connections with retry,
and an Observer pattern for decoupled state management.

Layout (3-row grid):
  Row 0 (fixed height): Toolbar — title, search entry, CRUD buttons, refresh, filter selector
  Row 1 (expands):      Central Treeview data grid (10 columns) + vertical scrollbar
  Row 2 (fixed height): Status bar — total items, low-stock, expiring, last refreshed
"""
from __future__ import annotations

import logging
from typing import Any

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n
from ui_helpers import apply_treeview_style
from ui_navigation import (
    COLOR_CARD_BG, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
)

# RBAC middleware (authz imports only `database`; no UI import cycle).
import authz
import auth_session

log = logging.getLogger("ui_inventory_management")

# ── AsyncUI (optional — graceful fallback to synchronous) ──
try:
    from async_ui import AsyncUI
    HAS_ASYNC: bool = True
except ImportError:
    AsyncUI = None  # type: ignore[assignment]
    HAS_ASYNC = False
    log.warning("async_ui not available; background tasks will run synchronously")


import sqlite3
import time
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Any, Callable, TypedDict

# ═════════════════════════════════════════════════════════════════════════════
#  SQLite WAL Connection Context Manager
# ═════════════════════════════════════════════════════════════════════════════


class SqliteWALConnection:
    """Context manager for SQLite connections with WAL mode and retry on lock.

    Enables ``PRAGMA journal_mode=WAL``, ``busy_timeout``, and
    ``synchronous=NORMAL`` so that reads and writes can proceed
    concurrently without blocking the UI thread.

    Usage::

        with SqliteWALConnection(db_path) as (conn, cur):
            cur.execute("SELECT ... WHERE col = ?", (val,))
            rows = cur.fetchall()
    """

    def __init__(self, db_path: str, max_retries: int = 3,
                 initial_delay: float = 0.1) -> None:
        self._db_path: str = db_path
        self._max_retries: int = max_retries
        self._initial_delay: float = initial_delay
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
        for attempt in range(self._max_retries):
            try:
                conn = sqlite3.connect(
                    self._db_path,
                    timeout=30.0,
                    isolation_level=None,
                    check_same_thread=False,
                )
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
                self._conn = conn
                return conn, conn.cursor()
            except sqlite3.OperationalError as exc:
                delay = self._initial_delay * (2 ** attempt)
                log.warning(
                    "SQLite WAL connect attempt %d/%d failed: %s — retrying in %.2fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                time.sleep(delay)
        raise sqlite3.OperationalError(
            f"Failed to acquire SQLite connection after {self._max_retries} attempts"
        )

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ═════════════════════════════════════════════════════════════════════════════
#  Inventory Observer (Observer Pattern)
# ═════════════════════════════════════════════════════════════════════════════


class InventoryObserver:
    """Observer pattern for inventory state change notifications.

    Decouples the CRUD manager from UI views: any subscriber can register
    a callback that receives ``(event_name, data_dict)``.
    """

    def __init__(self) -> None:
        self._observers: list[Callable[[str, dict[str, Any]], None]] = []

    def register(self, callback: Callable[[str, dict[str, Any]], None]) -> int:
        """Register *callback*; returns its slot index."""
        self._observers.append(callback)
        return len(self._observers) - 1

    def unregister(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Remove a previously-registered callback."""
        try:
            self._observers.remove(callback)
        except ValueError:
            pass

    def notify(self, event: str, data: dict[str, Any]) -> None:
        """Invoke every observer with *event* and *data*."""
        for observer in list(self._observers):
            try:
                observer(event, data)
            except Exception as exc:
                log.error("Inventory observer error on '%s': %s", event, exc)


# ═════════════════════════════════════════════════════════════════════════════
#  Data Structures
# ═════════════════════════════════════════════════════════════════════════════


class ProductRow(TypedDict, total=False):
    """Type definition for a product row dict returned by InventoryCrudManager."""

    id: int
    name: str
    price: float
    mfg_barcode: str
    int_barcode: str
    status: str
    expiry_date: str
    mfg_date: str
    vendor: str
    qty: int
    is_low_stock: bool
    is_expiring: bool


# ═════════════════════════════════════════════════════════════════════════════
#  CRUD Manager (Business Logic Layer)
# ═════════════════════════════════════════════════════════════════════════════


class InventoryCrudManager:
    """Async-capable CRUD operations for the ``products`` table.

    All database operations use ``SqliteWALConnection`` to ensure WAL-mode
    reads, busy_timeout, and exponential-backoff retry on lock contention.

    Methods are designed to be called from background threads via
    ``AsyncUI.run()`` — they are synchronous functions that return data
    to the calling thread.
    """

    def __init__(self, db_path: str | None = None) -> None:
        import database as _db
        self._db_path: str = db_path or _db.get_db_path()
        self._observer: InventoryObserver = InventoryObserver()

    @property
    def observer(self) -> InventoryObserver:
        return self._observer

    # ── Read operations ──────────────────────────────────────────

    def load_all(self, sort_by: str = "name") -> list[ProductRow]:
        """Load all in-stock product boxes.

        Time complexity: O(n) where n = total in-stock product rows.
        The SQL ``ORDER BY`` sorts at the database level (O(n log n)
        using index/b-tree, but this is handled by SQLite internally).
        """
        valid_sorts = {
            "expiry_date": "expiry_date ASC, name ASC",
            "manufacture_date": "manufacture_date DESC, name ASC",
            "name": "name ASC, expiry_date ASC",
            "vendor": "vendor_name ASC, name ASC",
            "price": "price ASC, name ASC",
        }
        order = valid_sorts.get(sort_by, "name ASC, expiry_date ASC")

        config = barcode_logic.load_config()
        low_threshold = config.get("low_stock_threshold", 5)
        expiry_days = config.get("expiry_alarm_days", 50)

        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(f"""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                ORDER BY {order}
            """)
            rows = cur.fetchall()

        return self._process_rows(rows, low_threshold, expiry_days)

    def search(self, query: str, sort_by: str = "name") -> list[ProductRow]:
        """Search products by name, barcodes, vendor, or expiry.

        Time complexity: O(n) for LIKE scan over in-stock rows (no full-text index).
        If the database has indexes on name/manufacturer_barcode, the LIKE
        predicate is O(log n) per column.
        """
        valid_sorts = {
            "expiry_date": "expiry_date ASC, name ASC",
            "manufacture_date": "manufacture_date DESC, name ASC",
            "name": "name ASC, expiry_date ASC",
            "vendor": "vendor_name ASC, name ASC",
            "price": "price ASC, name ASC",
        }
        order = valid_sorts.get(sort_by, "name ASC, expiry_date ASC")
        like_q = f"%{query}%"

        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute(f"""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products
                WHERE status = 'In Stock'
                  AND (name LIKE ? OR manufacturer_barcode LIKE ?
                       OR internal_unique_barcode LIKE ?
                       OR vendor_name LIKE ? OR expiry_date LIKE ?)
                ORDER BY {order}
            """, (like_q, like_q, like_q, like_q, like_q))
            rows = cur.fetchall()

        config = barcode_logic.load_config()
        low_threshold = config.get("low_stock_threshold", 5)
        expiry_days = config.get("expiry_alarm_days", 50)
        return self._process_rows(rows, low_threshold, expiry_days)

    def get_by_id(self, product_id: int) -> ProductRow | None:
        """Fetch a single product row by ID.  O(1) indexed lookup."""
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("""
                SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
                       status, expiry_date, manufacture_date, vendor_name
                FROM products WHERE id = ?
            """, (product_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row, {}, set(), date.today(), 0, 1)

    # ── Write operations ─────────────────────────────────────────

    def create(self, product: dict[str, Any]) -> int:
        """Insert a new product box. Returns the new product ID.

        Time complexity: O(1) — single INSERT.
        Generates ``internal_unique_barcode`` via
        ``barcode_logic.generate_internal_barcode(vendor_name)``.
        """
        vendor = product.get("vendor", "N/A") or "N/A"
        internal_bc = barcode_logic.generate_internal_barcode(vendor)
        expiry = product.get("expiry_date", "") or ""
        mfg = product.get("manufacture_date", "") or ""

        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("""
                INSERT INTO products
                    (name, price, manufacturer_barcode, internal_unique_barcode,
                     status, expiry_date, manufacture_date, vendor_name,
                     dea_schedule, wholesale_price, reorder_threshold)
                VALUES (?, ?, ?, ?, 'In Stock', ?, ?, ?, ?, ?, ?)
            """, (
                product["name"],
                float(product["price"]),
                product["manufacturer_barcode"],
                internal_bc,
                expiry,
                mfg,
                vendor,
                product.get("dea_schedule", "OTC"),
                product.get("wholesale_price", 0.0),
                product.get("reorder_threshold", 0),
            ))
            product_id = cur.lastrowid

            # Log shipment to receiving_log (mirrors database.add_product pattern)
            today = datetime.now().strftime("%Y-%m-%d")
            cur.execute("""
                INSERT INTO receiving_log
                    (vendor_name, product_name, date_received, quantity, total_cost, barcode)
                VALUES (?, ?, ?, 1, ?, ?)
            """, (vendor, product["name"], today, float(product["price"]), internal_bc))
            conn.commit()

        audit_log.log_action(
            "INVENTORY_ADD",
            f"Product '{product['name']}' (id={product_id}, barcode={internal_bc}) added.",
        )
        self._observer.notify("inventory_changed", {
            "action": "create",
            "product_id": product_id,
            "product": product,
        })
        return product_id

    def update(self, product_id: int, product: dict[str, Any]) -> bool:
        """Update an existing product box.

        Time complexity: O(1) — single UPDATE + optional cascade to
        ``receiving_log`` (one UPDATE per matching row, O(m) where m =
        shipments referencing this barcode).
        """
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("BEGIN TRANSACTION")
            cur.execute("""
                UPDATE products SET
                    name = ?, price = ?, manufacturer_barcode = ?,
                    internal_unique_barcode = ?, expiry_date = ?, manufacture_date = ?,
                    status = ?, vendor_name = ?, dea_schedule = ?,
                    wholesale_price = ?, reorder_threshold = ?
                WHERE id = ?
            """, (
                product["name"],
                float(product["price"]),
                product["manufacturer_barcode"],
                product["internal_barcode"],
                product.get("expiry_date", "") or "",
                product.get("manufacture_date", "") or "",
                product["status"],
                product.get("vendor", "N/A"),
                product.get("dea_schedule", "OTC"),
                product.get("wholesale_price", 0.0),
                product.get("reorder_threshold", 0),
                product_id,
            ))
            # Cascade vendor/name/price to receiving_log (mirrors database.update_product_full)
            cur.execute("""
                UPDATE receiving_log SET vendor_name = ?, product_name = ?
                WHERE barcode = ? AND barcode != ''
            """, (
                product.get("vendor", "N/A"),
                product["name"],
                product["internal_barcode"],
            ))
            cur.execute("""
                UPDATE receiving_log SET total_cost = ? * quantity
                WHERE barcode = ? AND barcode != ''
            """, (float(product["price"]), product["internal_barcode"]))
            conn.commit()

        audit_log.log_action(
            "INVENTORY_UPDATE",
            f"Product id={product_id} updated (name='{product['name']}', price={product['price']}).",
        )
        self._observer.notify("inventory_changed", {
            "action": "update",
            "product_id": product_id,
            "product": product,
        })
        return True

    def delete(self, product_id: int) -> bool:
        """Delete a product box by ID.

        Time complexity: O(1) — single indexed DELETE.
        """
        with SqliteWALConnection(self._db_path) as (conn, cur):
            cur.execute("DELETE FROM products WHERE id = ?", (product_id,))

        audit_log.log_action(
            "INVENTORY_DELETE",
            f"Product id={product_id} deleted from inventory.",
        )
        self._observer.notify("inventory_changed", {
            "action": "delete",
            "product_id": product_id,
        })
        return True

    # ── Internal helpers ─────────────────────────────────────────

    def _process_rows(
        self,
        rows: list[tuple],
        low_threshold: int,
        expiry_days: int,
    ) -> list[ProductRow]:
        """Convert raw DB tuples to ProductRow dicts with qty, low-stock, and expiry flags.

        Time complexity: O(n) where n = len(rows) — single pass for qty map
        + single pass for dict construction.
        """
        qty_map: dict[str, int] = defaultdict(int)
        for row in rows:
            qty_map[row[1]] += 1  # row[1] = name

        low_stock_names = self._compute_low_stock_names(low_threshold)
        today = date.today()
        cutoff = today + timedelta(days=expiry_days)

        result: list[ProductRow] = []
        for row in rows:
            name = row[1] or "Unknown"
            result.append(self._row_to_dict(
                row, qty_map, low_stock_names, cutoff, qty_map[name], qty_map[name]
            ))
        return result

    def _row_to_dict(
        self,
        row: tuple,
        qty_map: dict[str, int],
        low_stock_names: set[str],
        exp_cutoff: date,
        qty_override: int,
    ) -> ProductRow:
        """Map a raw DB tuple to a ProductRow dict.  O(1) per row."""
        name = row[1] or "Unknown"
        expiry_raw = row[6] if len(row) > 6 else ""
        expiry_date_str = expiry_raw if expiry_raw else "N/A"
        is_expiring = False
        if expiry_raw:
            try:
                exp = date.fromisoformat(expiry_raw.replace("/", "-"))
                is_expiring = exp <= exp_cutoff
            except (ValueError, TypeError):
                is_expiring = False

        return ProductRow(
            id=row[0],
            name=name,
            price=float(row[2]) if row[2] is not None else 0.0,
            mfg_barcode=row[3] or "",
            int_barcode=row[4] or "",
            status=row[5] or "In Stock",
            expiry_date=expiry_date_str,
            mfg_date=row[7] if len(row) > 7 and row[7] else "N/A",
            vendor=row[8] if len(row) > 8 and row[8] else "N/A",
            qty=qty_override if qty_override else qty_map.get(name, 1),
            is_low_stock=name in low_stock_names,
            is_expiring=is_expiring,
        )

    def _compute_low_stock_names(self, threshold: int) -> set[str]:
        """Return the set of product names whose in-stock count is ≤ threshold.

        Time complexity: O(n) where n = total in-stock rows (GROUP BY COUNT).
        """
        try:
            rows = database.get_low_stock_products(threshold=threshold)
            return {r[0] for r in rows}
        except Exception as exc:
            log.warning("Low-stock computation failed, using empty set: %s", exc)
            return set()


# ═════════════════════════════════════════════════════════════════════════════
#  Product Editor Dialog (Add / Edit)
# ═════════════════════════════════════════════════════════════════════════════


class ProductEditorDialog(ctk.CTkToplevel):
    """Self-contained dialog for adding or editing a product box.

    When ``product_id`` is None, operates in Add mode: the Internal Barcode
    is auto-generated via ``barcode_logic.generate_internal_barcode()``
    after the form is submitted. When ``product_id`` is set, operates in
    Edit mode: the Internal Barcode field is read-only.

    On save, invokes the ``on_save`` callback with ``(product_id, product_dict)``.
    """

    def __init__(
        self,
        parent: Any,
        title: str,
        product_id: int | None = None,
        initial: dict[str, Any] | None = None,
        on_save: Callable[[int | None, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("480x620")
        self.resizable(False, False)
        self.grab_set()

        self._product_id: int | None = product_id
        self._on_save: Callable[[int | None, dict[str, Any]], None] | None = on_save
        initial = initial or {}

        self._vars: dict[str, ctk.StringVar] = {}
        self._build_form(initial)

    def _build_form(self, initial: dict[str, Any]) -> None:
        """Construct the form fields."""
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=20)
        form.grid_columnconfigure(1, weight=1)

        is_add_mode = self._product_id is None
        int_bc_default = (barcode_logic.generate_internal_barcode(
            initial.get("vendor", "N/A") or "N/A"
        ) if is_add_mode else initial.get("int_barcode", ""))

        fields: list[tuple[str, str, str, str, bool]] = [
            ("Name:", "name", i18n.t("name"), initial.get("name", ""), False),
            (i18n.t("price_label"), "price", i18n.t("price"),
             f"{float(initial.get('price', 0.0)):.2f}", False),
            ("Mfg Barcode:", "mfg_barcode", i18n.t("mfg_barcode"),
             initial.get("mfg_barcode", ""), False),
            ("Internal Barcode:", "int_barcode", i18n.t("internal_barcode"),
             int_bc_default, True),
            ("Expiry Date:", "expiry_date", i18n.t("expiry_date"),
             initial.get("expiry_date", ""), False),
            ("Mfg Date:", "mfg_date", i18n.t("mfg_date"),
             initial.get("mfg_date", ""), False),
            ("Vendor:", "vendor", i18n.t("vendor"),
             initial.get("vendor", "N/A"), False),
        ]

        for i, (label, key, placeholder, value, is_disabled) in enumerate(fields):
            ctk.CTkLabel(form, text=label, anchor="w").grid(
                row=i, column=0, padx=(0, 10), pady=5, sticky="w")
            var = ctk.StringVar(value=str(value))
            self._vars[key] = var
            entry = ctk.CTkEntry(form, textvariable=var, placeholder_text=placeholder)
            entry.grid(row=i, column=1, sticky="ew", pady=5)
            if is_disabled or key == "int_barcode":
                entry.configure(state="disabled")
                if key == "int_barcode":
                    ctk.CTkLabel(form, text="(Auto-Generated)", text_color="gray",
                                 font=ctk.CTkFont(size=11)).grid(
                        row=i, column=2, padx=(6, 0), pady=5, sticky="w")

        # Status
        status_row = len(fields)
        ctk.CTkLabel(form, text="Status:", anchor="w").grid(
            row=status_row, column=0, padx=(0, 10), pady=5, sticky="w")
        self._status_var = ctk.StringVar(value=initial.get("status", "In Stock"))
        ctk.CTkSegmentedButton(
            form, values=["In Stock", "Sold"], variable=self._status_var,
        ).grid(row=status_row, column=1, sticky="ew", pady=5)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            btn_frame, text=i18n.t("cancel"), width=100,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self.destroy,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_frame, text=i18n.t("save"), width=120,
            command=authz.require_permission("inventory.manage")(self._on_save_click),
        ).pack(side="right")

    def _on_save_click(self) -> None:
        """Validate inputs and invoke the on_save callback."""
        if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
            authz.access_denied("inventory.manage")
            return
        name = self._vars["name"].get().strip()
        price_str = self._vars["price"].get().strip()
        mfg_barcode = self._vars["mfg_barcode"].get().strip()
        int_barcode = self._vars["int_barcode"].get().strip()
        expiry = self._vars["expiry_date"].get().strip()
        mfg = self._vars["mfg_date"].get().strip()
        vendor = self._vars["vendor"].get().strip() or "N/A"
        status = self._status_var.get()

        if not name:
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_save_failed",
                                        error="Name is required."))
            return
        if not mfg_barcode:
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_save_failed",
                                        error="Manufacturer barcode is required."))
            return
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_save_failed",
                                        error="Price must be a valid number."))
            return

        if expiry and not self._validate_date(expiry):
            messagebox.showerror(i18n.t("error"), i18n.t("date_format_error"))
            return
        if mfg and not self._validate_date(mfg):
            messagebox.showerror(i18n.t("error"), i18n.t("date_format_error"))
            return
        if expiry and mfg:
            try:
                exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
                mfg_dt = datetime.strptime(mfg, "%Y-%m-%d")
                if mfg_dt >= exp_dt:
                    messagebox.showerror(i18n.t("error"),
                                          i18n.t("expiry_must_be_after_mfg"))
                    return
            except ValueError:
                pass

        product: dict[str, Any] = {
            "name": name,
            "price": price,
            "manufacturer_barcode": mfg_barcode,
            "internal_barcode": int_barcode,
            "expiry_date": expiry,
            "manufacture_date": mfg,
            "vendor": vendor,
            "status": status,
        }
        self.destroy()
        if self._on_save:
            self._on_save(self._product_id, product)

    @staticmethod
    def _validate_date(date_str: str) -> bool:
        """Validate that *date_str* matches YYYY-MM-DD.  O(1)."""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False


# ═════════════════════════════════════════════════════════════════════════════
#  Main Frame
# ═════════════════════════════════════════════════════════════════════════════


class InventoryManagementFrame(ctk.CTkFrame):
    """Full CRUD inventory management interface.

    Layout (3-row grid):
      Row 0 (fixed height): Toolbar — title, search, CRUD buttons, filter selector
      Row 1 (expands):      Central Treeview data grid + vertical scrollbar
      Row 2 (fixed height): Status bar — counts + last refreshed timestamp

    All database operations run asynchronously via AsyncUI to keep the
    UI mainloop responsive.  Visual indicators:
      - Low-stock rows: yellow background (≤ low_stock_threshold for drug name)
      - Expiring-soon rows: red background (expiry ≤ today + expiry_alarm_days)
    """

    _TREECOLUMNS: tuple[str, ...] = (
        "ID", "Name", "Price", "Mfg Barcode", "Int. Barcode",
        "Status", "Expiry", "Mfg Date", "Vendor", "Qty",
    )

    _FILTER_CHOICES: tuple[str, ...] = ("All", "Low Stock", "Expiring Soon", "Out of Stock")

    def __init__(self, parent: Any, app: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, fg_color=kwargs.pop("fg_color", "transparent"), **kwargs)
        self._app: Any = app
        self._crud: InventoryCrudManager = InventoryCrudManager()
        self._crud.observer.register(self._on_inventory_changed)

        # ── State ──
        self._rows: list[dict[str, Any]] = []
        self._current_sort: str = "name"
        self._sort_reverse: bool = False
        self._current_filter: str = "All"
        self._row_counter: int = 0

        # ── UI references (populated by _build_ui) ──
        self._tree: ttk.Treeview | None = None
        self._search_entry: ctk.CTkEntry | None = None
        self._btn_add: ctk.CTkButton | None = None
        self._btn_edit: ctk.CTkButton | None = None
        self._btn_delete: ctk.CTkButton | None = None
        self._status_labels: dict[str, ctk.CTkLabel] = {}

        self._build_ui()

    # ── Layout ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construct the full layout: toolbar, Treeview, and status bar."""
        self._configure_grid()
        self._build_toolbar()
        self._build_treeview()
        self._build_status_bar()
        self._bind_events()

    def _bind_events(self) -> None:
        """Wire up callbacks for toolbar buttons and Treeview events."""
        if self._search_entry is not None:
            self._search_entry.bind("<Return>", self._on_search)

        # The search button is the 3rd button in the left group (after entry)
        search_btn = self._toolbar.winfo_children()[0].winfo_children()
        if len(search_btn) >= 3:
            search_btn[2].configure(command=self._on_search)

        if self._btn_add is not None:
            self._btn_add.configure(command=authz.require_permission("inventory.manage")(self._on_add))
        if self._btn_edit is not None:
            self._btn_edit.configure(command=authz.require_permission("inventory.manage")(self._on_edit))
            self._btn_edit.configure(state="disabled")
        if self._btn_delete is not None:
            self._btn_delete.configure(command=authz.require_permission("inventory.manage")(self._on_delete))
            self._btn_delete.configure(state="disabled")

    def _configure_grid(self) -> None:
        """Set up the 3-row grid on this frame."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # toolbar
        self.grid_rowconfigure(1, weight=1)  # treeview
        self.grid_rowconfigure(2, weight=0)  # status bar

    def _build_toolbar(self) -> None:
        """Row 0 — title, search, CRUD buttons, refresh, and filter selector."""
        self._toolbar = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=8)
        toolbar = self._toolbar
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        toolbar.grid_propagate(False)
        toolbar.update_idletasks()
        toolbar.configure(height=60)

        toolbar.grid_columnconfigure(0, weight=1)

        # ── Left group: title + search ──
        left = ctk.CTkFrame(toolbar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        left.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            left, text=i18n.t("inventory_mgmt_title"),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self._search_entry = ctk.CTkEntry(
            left, width=260,
            placeholder_text=i18n.t("inventory_mgmt_search_placeholder"),
        )
        self._search_entry.grid(row=0, column=1, sticky="w", padx=(0, 8))

        ctk.CTkButton(
            left, text=i18n.t("inventory_mgmt_search_btn"), width=80,
        ).grid(row=0, column=2, sticky="w")

        ctk.CTkButton(
            left, text=i18n.t("inventory_mgmt_refresh"), width=80,
            fg_color="#6c757d", hover_color="#5a6268",
        ).grid(row=0, column=3, sticky="w", padx=(4, 0))

        # ── Right group: CRUD buttons ──
        right = ctk.CTkFrame(toolbar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=8, pady=12)

        self._btn_add = ctk.CTkButton(
            right, text=i18n.t("inventory_mgmt_add"), width=90,
            fg_color=COLOR_SUCCESS, hover_color="#059669",
        )
        self._btn_add.pack(side="left", padx=2)

        self._btn_edit = ctk.CTkButton(
            right, text=i18n.t("inventory_mgmt_edit"), width=80,
            fg_color=COLOR_WARNING, hover_color="#d97706",
        )
        self._btn_edit.pack(side="left", padx=2)

        self._btn_delete = ctk.CTkButton(
            right, text=i18n.t("inventory_mgmt_delete"), width=80,
            fg_color=COLOR_ERROR, hover_color="#b91c1c",
        )
        self._btn_delete.pack(side="left", padx=2)

        # ── Filter selector ──
        filter_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="e", padx=(0, 140), pady=12)

        ctk.CTkLabel(
            filter_frame, text="Filter:",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))

        self._filter_var: ctk.StringVar = ctk.StringVar(value="All")
        self._filter_segmented = ctk.CTkSegmentedButton(
            filter_frame,
            values=[
                i18n.t("inventory_mgmt_all"),
                i18n.t("inventory_mgmt_low_stock"),
                i18n.t("inventory_mgmt_expiring"),
                i18n.t("inventory_mgmt_out_of_stock"),
            ],
            variable=self._filter_var,
            width=220,
            command=self._on_filter_change,
        )
        self._filter_segmented.pack(side="left")

    def _build_treeview(self) -> None:
        """Row 1 — central Treeview data grid with vertical scrollbar."""
        tree_container = ctk.CTkFrame(self, fg_color="transparent")
        tree_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tree_container, columns=self._TREECOLUMNS,
            show="headings", height=15,
        )
        apply_treeview_style(self._tree)

        # Row striping tags (configured once at tree level)
        self._tree.tag_configure("odd", background="#2D2D2D", foreground="#FFFFFF")
        self._tree.tag_configure("even", background="#1E1E1E", foreground="#FFFFFF")

        # Column configuration: all stretchable, with min widths
        col_widths: dict[str, int] = {
            "ID": 50, "Name": 160, "Price": 80, "Mfg Barcode": 120,
            "Int. Barcode": 130, "Status": 90, "Expiry": 95,
            "Mfg Date": 95, "Vendor": 120, "Qty": 55,
        }
        for col in self._TREECOLUMNS:
            w = col_widths.get(col, 80)
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._on_header_click(c))
            self._tree.column(col, width=w, minwidth=w, anchor="w", stretch=True)

        # Price and Qty columns right-aligned
        self._tree.column("Price", anchor="e")
        self._tree.column("Qty", anchor="center")
        self._tree.column("ID", anchor="center")
        self._tree.column("Status", anchor="center")
        self._tree.column("Expiry", anchor="center")
        self._tree.column("Mfg Date", anchor="center")

        self._tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(tree_container, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns", padx=(0, 2))

        # Event bindings
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", self._on_row_double_click)

    def _build_status_bar(self) -> None:
        """Row 2 — status bar with counts and refresh timestamp."""
        self._status_bar = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG,
                                       corner_radius=8, height=36)
        status_bar = self._status_bar
        status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        status_bar.grid_propagate(False)

        label_specs: list[tuple[str, str]] = [
            ("total", i18n.t("inventory_mgmt_total_items", count=0)),
            ("low", i18n.t("inventory_mgmt_low_stock_count", count=0)),
            ("exp", i18n.t("inventory_mgmt_expiring_count", count=0)),
        ]
        for key, default_text in label_specs:
            lbl = ctk.CTkLabel(
                status_bar, text=default_text,
                font=ctk.CTkFont(size=12),
                text_color=COLOR_TEXT_SECONDARY,
            )
            lbl.pack(side="left", padx=14)
            self._status_labels[key] = lbl

        self._refresh_time_label = ctk.CTkLabel(
            status_bar,
            text=i18n.t("inventory_mgmt_last_refresh",
                        time="00:00:00"),
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._refresh_time_label.pack(side="right", padx=14)

    # ── Async helpers ──────────────────────────────────────────

    def _init_async(self) -> None:
        """Bind AsyncUI root if available so callbacks marshal to the main thread."""
        if not HAS_ASYNC:
            return
        try:
            mgr = AsyncUI.get()  # type: ignore[union-attr]
            if mgr._root is None:
                root = self.winfo_toplevel()
                mgr.init(root)
        except Exception as exc:
            log.debug("AsyncUI init deferred: %s", exc)

    def _run_async(
        self,
        func: Callable,
        callback: Callable[[Any, Any], None],
        args: tuple = (),
    ) -> None:
        """Submit *func* to AsyncUI thread pool; marshal *callback* to main thread."""
        if HAS_ASYNC and AsyncUI is not None:
            try:
                mgr = AsyncUI.get()  # type: ignore[union-attr]
                if mgr._root is not None:
                    mgr.run(func=func, callback=callback, args=args)
                    return
            except Exception as exc:
                log.debug("AsyncUI run unavailable, falling back to sync: %s", exc)
        self._run_sync(func, callback, args)

    def _run_sync(
        self,
        func: Callable,
        callback: Callable[[Any, Any], None],
        args: tuple = (),
    ) -> None:
        """Run *func* synchronously and invoke *callback* via after(0) on main thread."""
        try:
            result = func(*args) if args else func()
        except Exception as exc:
            result = None
            log.error("Sync task error: %s", exc)
        self.after(0, lambda: callback(result, None))

    # ── Load & Display ──────────────────────────────────────────

    def _load_inventory(self, sort_by: str | None = None) -> None:
        """Submit inventory load to background thread."""
        sort_by = sort_by or self._current_sort
        self._set_loading(True)
        self._run_async(
            func=self._crud.load_all,
            callback=self._on_load_done,
            args=(sort_by,),
        )

    def _on_load_done(self, rows: list[dict[str, Any]] | None, error: Any) -> None:
        """Callback (main thread): populate Treeview with loaded rows."""
        self._set_loading(False)
        if error:
            log.error("Load inventory failed: %s", error)
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_load_error", error=str(error)))
            return
        if rows is None:
            rows = []
        self._rows = rows
        self._populate_tree(rows)
        self._refresh_status_bar()

    def _populate_tree(self, rows: list[dict[str, Any]]) -> None:
        """Populate the Treeview with rows.

        Time complexity: O(n) where n = len(rows) for Treeview insertion,
        plus O(n) for row counter + tag assignment. Total: O(n).
        Sorting is done at the SQL level (O(n log n) in SQLite).
        """
        for item in self._tree.get_children():
            self._tree.delete(item)

        self._row_counter = 0
        for row in rows:
            self._row_counter += 1
            tag = "even" if self._row_counter % 2 == 0 else "odd"
            tags: list[str] = [tag]

            # Visual indicators: red (expiring) takes priority over yellow (low stock)
            if row.get("is_expiring"):
                tags.append("expiring")
            elif row.get("is_low_stock"):
                tags.append("low_stock")

            price_str = self.app.currency.fmt(row['price'])
            iid = f"prod_{row['id']}"
            self._tree.insert("", "end", iid=iid, values=(
                row["id"],
                row["name"],
                price_str,
                row["mfg_barcode"],
                row["int_barcode"],
                row["status"],
                row["expiry_date"],
                row["mfg_date"],
                row["vendor"],
                row["qty"],
            ), tags=tuple(tags))

    def _refresh_status_bar(self) -> None:
        """Update status bar counts from current ``self._rows``."""
        total = len(self._rows)
        low = sum(1 for r in self._rows if r.get("is_low_stock") and not r.get("is_expiring"))
        exp = sum(1 for r in self._rows if r.get("is_expiring"))
        self._status_labels["total"].configure(
            text=i18n.t("inventory_mgmt_total_items", count=total))
        self._status_labels["low"].configure(
            text=i18n.t("inventory_mgmt_low_stock_count", count=low))
        self._status_labels["exp"].configure(
            text=i18n.t("inventory_mgmt_expiring_count", count=exp))
        self._refresh_time_label.configure(
            text=i18n.t("inventory_mgmt_last_refresh",
                        time=datetime.now().strftime("%H:%M:%S")))

    def _set_loading(self, loading: bool) -> None:
        """Toggle toolbar button states during async operations."""
        state = "disabled" if loading else "normal"
        self._btn_add.configure(state=state)
        self._btn_edit.configure(state=state)
        self._btn_delete.configure(state=state)

    # ── Observer callback ──────────────────────────────────────

    def _on_inventory_changed(self, event: str, data: dict[str, Any]) -> None:
        """Observer callback: reload Treeview + status bar after any CRUD mutation."""
        action = data.get("action", "")
        log.info("Inventory changed: %s", action)
        self._load_inventory(self._current_sort)

    # ── Search ──────────────────────────────────────────────────

    def _on_search(self, event: Any | None = None) -> None:
        """Submit search query to background thread."""
        query = self._search_entry.get().strip()
        if not query:
            self._load_inventory(self._current_sort)
            return
        self._set_loading(True)
        self._run_async(
            func=self._crud.search,
            callback=self._on_search_done,
            args=(query, self._current_sort),
        )

    def _on_search_done(self, rows: list[dict[str, Any]] | None, error: Any) -> None:
        """Callback (main thread): populate Treeview with search results."""
        self._set_loading(False)
        if error:
            log.error("Search failed: %s", error)
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_load_error", error=str(error)))
            return
        if rows is None:
            rows = []
        self._rows = rows
        self._populate_tree(rows)
        self._refresh_status_bar()

    # ── CRUD handlers ──────────────────────────────────────────

    def _on_add(self) -> None:
        """Open the editor in Add mode."""
        if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
            authz.access_denied("inventory.manage")
            return
        ProductEditorDialog(
            self,
            title=i18n.t("inventory_mgmt_add"),
            product_id=None,
            on_save=self._on_save_done,
        )

    def _on_edit(self) -> None:
        """Open the editor in Edit mode for the selected row."""
        if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
            authz.access_denied("inventory.manage")
            return
        row = self._get_selected_row()
        if not row:
            messagebox.showwarning(i18n.t("info"),
                                   i18n.t("inventory_mgmt_empty_selection"))
            return
        initial = dict(row)
        ProductEditorDialog(
            self,
            title=i18n.t("inventory_mgmt_edit"),
            product_id=row["id"],
            initial=initial,
            on_save=self._on_save_done,
        )

    def _on_delete(self) -> None:
        """Delete the selected product box (with admin PIN confirmation)."""
        if not authz.check_permission(auth_session.current_user_id(), "inventory.manage"):
            authz.access_denied("inventory.manage")
            return
        row = self._get_selected_row()
        if not row:
            messagebox.showwarning(i18n.t("info"),
                                   i18n.t("inventory_mgmt_empty_selection"))
            return

        dialog = ctk.CTkInputDialog(
            text=i18n.t("inventory_mgmt_delete_prompt"),
            title=i18n.t("inventory_mgmt_confirm_delete"),
        )
        pin = dialog.get_input()
        if pin is None:
            return  # user cancelled
        if pin != "1234":
            messagebox.showerror(i18n.t("error"), i18n.t("inventory_mgmt_invalid_pin"))
            return

        self._set_loading(True)
        self._run_async(
            func=self._crud.delete,
            callback=self._on_crud_done,
            args=(row["id"],),
        )

    def _on_save_done(self, product_id: int | None, product: dict[str, Any]) -> None:
        """Callback for Add/Edit save — dispatch to background CRUD operation."""
        self._set_loading(True)
        if product_id is None:
            self._run_async(
                func=self._crud.create,
                callback=self._on_crud_done,
                args=(product,),
            )
        else:
            self._run_async(
                func=self._crud.update,
                callback=self._on_crud_done,
                args=(product_id, product),
            )

    def _on_crud_done(self, result: Any, error: Any) -> None:
        """Callback (main thread): handle CRUD completion."""
        self._set_loading(False)
        if error:
            log.error("CRUD operation failed: %s", error)
            messagebox.showerror(i18n.t("error"),
                                 i18n.t("inventory_mgmt_save_failed", error=str(error)))
            return

        if isinstance(result, int):
            messagebox.showinfo(i18n.t("success"),
                                i18n.t("inventory_mgmt_product_added",
                                       id=result))
        elif isinstance(result, bool):
            if not result:
                messagebox.showinfo(i18n.t("success"),
                                    i18n.t("inventory_mgmt_deleted"))
        self._load_inventory(self._current_sort)

    # ── Sort & Filter ──────────────────────────────────────────

    _SORT_KEY_MAP: dict[str, str] = {
        "ID": "id", "Name": "name", "Price": "price",
        "Mfg Barcode": "mfg_barcode", "Int. Barcode": "int_barcode",
        "Status": "status", "Expiry": "expiry_date",
        "Mfg Date": "mfg_date", "Vendor": "vendor", "Qty": "qty",
    }

    def _on_header_click(self, col: str) -> None:
        """Click-to-sort on a Treeview column header.

        Time complexity: O(n log n) — the actual sorting is delegated to
        SQLite's ORDER BY in ``_crud.load_all`` / ``_crud.search``.
        """
        sort_key = self._SORT_KEY_MAP.get(col, "name")
        if self._current_sort == sort_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._current_sort = sort_key
            self._sort_reverse = False
        self._apply_sort_icons()
        self._load_inventory(sort_key)

    def _apply_sort_icons(self) -> None:
        """Update column header arrows (▲ ascending, ▼ descending)."""
        for col in self._TREECOLUMNS:
            txt = self._tree.heading(col, "text")
            clean = txt.replace(" \u25b2", "").replace(" \u25bc", "")
            if col == self._current_sort:
                mapped = self._SORT_KEY_MAP.get(col, "")
                if mapped == self._current_sort:
                    arrow = " \u25b2" if not self._sort_reverse else " \u25bc"
                    self._tree.heading(col, text=clean + arrow)
                else:
                    self._tree.heading(col, text=clean)
            else:
                self._tree.heading(col, text=clean)

    def _on_filter_change(self, choice: str | None = None) -> None:
        """Apply a filter to the currently loaded rows and re-populate the Treeview."""
        if choice is None:
            choice = self._filter_var.get()
        self._current_filter = choice

        if choice == i18n.t("inventory_mgmt_all"):
            filtered = self._rows
        elif choice == i18n.t("inventory_mgmt_low_stock"):
            filtered = [r for r in self._rows if r.get("is_low_stock") and not r.get("is_expiring")]
        elif choice == i18n.t("inventory_mgmt_expiring"):
            filtered = [r for r in self._rows if r.get("is_expiring")]
        elif choice == i18n.t("inventory_mgmt_out_of_stock"):
            filtered = [r for r in self._rows if r.get("status") == "Sold"]
        else:
            filtered = self._rows

        self._populate_tree(filtered)

    # ── Tree selection ─────────────────────────────────────────

    def _on_tree_select(self, event: Any | None = None) -> None:
        """Enable Edit/Delete buttons when a row is selected."""
        selected = self._tree.selection()
        if selected:
            self._btn_edit.configure(state="normal")
            self._btn_delete.configure(state="normal")
        else:
            self._btn_edit.configure(state="disabled")
            self._btn_delete.configure(state="disabled")

    def _on_row_double_click(self, event: Any | None = None) -> None:
        """Double-click a row → open Edit dialog."""
        if self._get_selected_row():
            self._on_edit()

    def _get_selected_row(self) -> dict[str, Any] | None:
        """Return the currently selected product row as a dict, or None."""
        if self._tree is None:
            return None
        selected = self._tree.selection()
        if not selected:
            return None
        iid = selected[0]
        if not iid.startswith("prod_"):
            return None
        product_id = int(iid[len("prod_"):])
        for row in self._rows:
            if row["id"] == product_id:
                return row
        return None

    # ── Debug ──────────────────────────────────────────────────

    def _debug_layout_geometry(self) -> dict[str, Any]:
        """Programmatically assert layout integrity.

        Checks (VERIFICATION_CHECKLIST Protocol II.A):
        - Toolbar height > 0.
        - Status bar height > 0.
        - Treeview has non-zero dimensions.
        - No child widget extends past the root window width.

        Returns a dict of measured dimensions and any issues found.
        """
        self.update_idletasks()
        root = self.winfo_toplevel()
        root_w = root.winfo_width()
        root_h = root.winfo_height()

        results: dict[str, Any] = {
            "root_width": root_w,
            "root_height": root_h,
            "issues": [],
        }

        toolbar_h = self._toolbar.winfo_height()
        results["toolbar_height"] = toolbar_h
        if toolbar_h <= 0:
            results["issues"].append("Toolbar has zero height")

        status_h = self._status_bar.winfo_height()
        results["status_bar_height"] = status_h
        if status_h <= 0:
            results["issues"].append("Status bar has zero height")

        tree_w = self._tree.winfo_width()
        tree_h = self._tree.winfo_height()
        results["tree"] = {"width": tree_w, "height": tree_h}
        if tree_w <= 0 or tree_h <= 0:
            results["issues"].append("Treeview has zero dimensions")

        for child in root.winfo_children():
            x = child.winfo_x()
            w = child.winfo_width()
            if x + w > root_w + 5:
                results["issues"].append(
                    f"Off-screen: {child.__class__.__name__} "
                    f"x={x} w={w} (root={root_w})"
                )

        if results["issues"]:
            log.warning("Layout geometry issues: %s", results["issues"])
        else:
            log.debug("Layout geometry OK: %s", results)
        return results

    # ── Public API ─────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload Treeview from database and re-read config."""
        self._load_inventory(self._current_sort)

    def get_selected_product_id(self) -> int | None:
        """Return the product ID of the selected row, or None."""
        row = self._get_selected_row()
        return row["id"] if row else None


# ═════════════════════════════════════════════════════════════════════════════
#  Tab setup (called by main_app.py via monkey-patch)
# ═════════════════════════════════════════════════════════════════════════════


def setup_inventory_management_tab(self: Any, parent: Any = None) -> InventoryManagementFrame:
    """Tab-setup function attached to PharmacyApp via monkey-patch.

    Adds the Inventory Management tab to ``self.tab_view`` and exposes
    ``self.inventory_mgmt_frame`` for refresh on tab activation.
    """
    if parent is None:
        parent = self.tab_inventory_mgmt

    frame = InventoryManagementFrame(parent, app=self, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    self.inventory_mgmt_frame = frame
    self._refresh_inventory_mgmt_tab = frame.refresh

    return frame
