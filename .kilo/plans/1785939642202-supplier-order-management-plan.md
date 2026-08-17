# Implementation Plan — Supplier Order Management Module

> **Status:** Planning — Implementation-Ready
> **Scope:** New module `archive/ui_supplier_order_management.py` + supporting schema/DB layers for pharmaceutical supplier CRUD, automated safety-stock reorder (auto-reorder PO generation), and purchase-order lifecycle (Draft → Submitted → Received → Closed) tied to the SQLite backend.
> **Current date:** 2026-08-05 (per system clock)
> **Target Python:** 3.12+ (type-annotated `X | None` syntax)
> **Plan file:** `.kilo/plans/1785939642202-supplier-order-management-plan.md`

---

## 1. Context & Existing-Convention Baseline

The codebase is a monolithic CustomTkinter desktop suite in `archive/`. Phase-16 modules are wired via **monkey-patch** in `main_app.py:_wire_rx_extensions()` (NOT by editing `ui.py`/`ui_navigation.py`). Each new tab follows a fixed pattern; this plan mirrors it exactly.

### Proven patterns to reuse (file:line)
| Concern | Source | Reuse approach |
|---|---|---|
| `SqliteWALConnection` (WAL + busy_timeout=30000 + exp-backoff on `sqlite3.OperationalError` in `__enter__`) | `ui_pos_retail.py:136`, duplicated at `ui_inventory_management.py:53` | **Import from `ui_pos_retail`** (DRY; Surgical Editing Protocol §II). Avoids a 3rd copy. |
| `AsyncUI` singleton (ThreadPoolExecutor, `root.after()` marshaling) | `async_ui.py:45` | `from async_ui import AsyncUI` with `try/except ImportError → HAS_ASYNC=False` guard (matches `ui_pos_retail.py:51-57`). |
| Observer pattern | `ui_pos_retail.CartObserver:192`, `ui_inventory_management.InventoryObserver:113` | New `SupplierObserver` with identical `register/unregister/notify(event, data)` shape. |
| Dialogs | `ui_inventory_management.ProductEditorDialog:485` | `SupplierEditorDialog` + `PoDetailDialog` mirror this: `ctk.CTkToplevel`, `grab_set`, `StringVar` form, `_validate_*` helpers, `on_save` callback. |
| Layout geometry audit | `ui_pos_retail._debug_layout_geometry:1168`, `ui_inventory_management._debug_layout_geometry:1248` | Copy the assertion contract: `update_idletasks()` → measure `winfo_width()/winfo_x()` → log + return issues. |
| `native_accel` | `native_accel.py` (exists) | `fuzzy_search(query, choices, cutoff=60)` for supplier search; `generate_batch_barcodes(vendor, qty)` for receipt-time pre-gen. |
| `audit_log` | `audit_log.py` | `audit_log.log_action(action, details, user_pin="")` for PO state transitions + auto-reorder. |
| `i18n` | `i18n.py` | `i18n.t(key, **kwargs)` for **all** user-facing strings. |
| Tab wiring | `main_app.py:58` (`_wire_rx_extensions`), `ui_navigation._NAV_ICONS:338` | Append icon + tab + `setup_*_tab` call + `on_tab_change` refresh branch. |

### Critical schema reality (verified)
- `products` table columns: `id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name, dea_schedule, wholesale_price, reorder_threshold` (`init_db` ALTER migration at `database.py:94-103`; `db.py:389`).
- **There is NO `suppliers` table** and **NO `purchase_orders`/`po_items` table.** These must be created by a new migration in `database.init_db()` + `db.init_db()`.
- `database.get_low_stock_products(threshold=5)` (`database.py:1209`) uses a **global** threshold. Auto-reorder must use the **per-product** `reorder_threshold` column → a new `get_products_below_reorder_threshold()` function.
- `database.receive_inventory_atomically(...)` (`database.py:754`) already accepts `pre_generated_barcodes` and auto-calls `native_accel.generate_batch_barcodes()` when `None` (`database.py:761-766`; `db.py:849-854`). The new module reuses this directly on PO→Received.
- `database.get_all_vendors()` (`database.py:821`) derives vendors from `receiving_log.vendor_name` — used for suppliers backfill migration.

### i18n gap analysis (locales/en.json)
**Already present (reuse, no change):** `suppliers`, `add_supplier`, `contact_name`, `contact_email`, `contact_phone`, `supplier_address`, `min_stock_level`, `lead_time_days`, `supplier_sku`, `generate_po`, `check_reorder`, `po_number`, `po_status`, `draft`("Draft"), `received`("Received"), `sent`("Sent"), `acknowledged`("Acknowledged"), `total_cost`, `date_received`, `quantity`, `add`, `remove`, `save`, `cancel`, `search`, `error`, `success`, `info`, `name`, `price`, `vendor`, `status`, `notes`.

**MISSING — must add to `locales/en.json`** (non-English files fall back to English automatically via `i18n.t()`):
```
"supplier_order_title": "Supplier & Order Management"
"supplier_editor_title": "Edit Supplier"
"add_supplier_title": "Add Supplier"
"submitted": "Submitted"
"closed": "Closed"
"performance_notes": "Performance Notes"
"preferred_vendor": "Preferred Vendor"
"unit_price": "Unit Price"
"line_items": "Line Items"
"generate_auto_reorder": "Generate Auto-Reorder PO"
"auto_reorder_success": "Auto-reorder drafts created for {count} supplier(s), {items} item(s)."
"auto_reorder_no_items": "No products are currently below their reorder threshold."
"po_detail_title": "Purchase Order Details"
"receive_po": "Receive PO"
"submit_po": "Submit PO"
"close_po": "Close PO"
"draft_po": "Draft PO"
"po_transition": "PO {po} status changed: {old} → {new}"
"po_status_draft": "Draft"
"po_status_submitted": "Submitted"
"po_status_received": "Received"
"po_status_closed": "Closed"
"search_suppliers": "Search suppliers..."
"save_supplier": "Save Supplier"
"save_po": "Save PO"
"po_qty": "Qty"
"po_line_total": "Line Total"
"po_total": "PO Total"
"preferred": "Preferred"
"po_received_success": "PO #{po} received: {count} boxes added to inventory."
"po_no_line_items": "Add at least one line item before receiving."
"supplier_deleted": "Supplier '{name}' deleted."
```

---

## 2. Assumptions & Design Decisions (stated explicitly)

1. **Suppliers = new table.** The requirement for "contact info, preferred vendor tags, performance notes" cannot be served by free-text `vendor_name`. A dedicated `suppliers` table is mandatory.
2. **POs = new tables (`purchase_orders` + `po_items`).** `receiving_log` is append-only and has no state machine; the Draft→Submitted→Received→Closed lifecycle requires a stateful `purchase_orders` table plus a `po_items` child table.
3. **Product↔supplier link = name match.** Existing `products.vendor_name` is free text. Products link to a supplier by `supplier.name == products.vendor_name` (no FK migration on `products` — too risky for serialized-box data; deferred to a future migration).
4. **Low-stock = per-product `reorder_threshold`.** In-stock box count per drug name `COUNT(*)` compared to that drug's `MIN(reorder_threshold)`. `get_low_stock_products()` (global threshold) is **not** used for auto-reorder.
5. **PO canonical state strings:** `Draft`, `Submitted`, `Received`, `Closed` (exact, per requirement). DB stores these verbatim; UI renders via `i18n.t("po_status_<lower>")`.
6. **SqliteWALConnection imported from `ui_pos_retail`** (not duplicated). If import fails at runtime, module defines a local alias — see §4.
7. **Autosave vs explicit:** Supplier edits are saved explicitly via Save button (matches `ProductEditorDialog`). PO items are edited inline on the form and persisted with Save PO. State transitions (Submit/Receive/Close) are explicit buttons with `messagebox` confirmation.
8. **Scope boundary:** No new tabs beyond the single "Supplier & Order Management" tab. No changes to existing receive tab, checkout, label engine, or `ui.py`.

---

## 3. Schema (new tables) — add to `database.init_db()` (sqlite) and `db.init_db()` (SQLAlchemy)

### `suppliers`
```sql
CREATE TABLE IF NOT EXISTS suppliers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL UNIQUE,
    contact_name     TEXT DEFAULT '',
    contact_email    TEXT DEFAULT '',
    contact_phone    TEXT DEFAULT '',
    address          TEXT DEFAULT '',
    preferred        INTEGER DEFAULT 0,        -- 0/1 boolean
    sku              TEXT DEFAULT '',
    min_stock_level  INTEGER DEFAULT 0,
    lead_time_days   INTEGER DEFAULT 0,
    edi_endpoint     TEXT DEFAULT '',
    edi_api_key      TEXT DEFAULT '',
    performance_notes TEXT DEFAULT '',
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_suppliers_preferred ON suppliers(preferred);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
```

### `purchase_orders`
```sql
CREATE TABLE IF NOT EXISTS purchase_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number    TEXT NOT NULL UNIQUE,
    vendor_id    INTEGER NOT NULL REFERENCES suppliers(id),
    vendor_name  TEXT NOT NULL,                 -- denormalized for offline/rollback safety
    status       TEXT NOT NULL DEFAULT 'Draft', -- Draft|Submitted|Received|Closed
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    submitted_at TEXT,
    received_at  TEXT,
    closed_at    TEXT,
    subtotal     REAL DEFAULT 0.0,
    tax_amount   REAL DEFAULT 0.0,
    total_cost   REAL DEFAULT 0.0,
    notes        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_po_vendor ON purchase_orders(vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_created ON purchase_orders(created_at);
```

### `po_items`
```sql
CREATE TABLE IF NOT EXISTS po_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id         INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    line_number   INTEGER NOT NULL,
    product_name  TEXT NOT NULL,
    vendor_sku    TEXT DEFAULT '',
    quantity      INTEGER NOT NULL DEFAULT 1,
    unit_price    REAL NOT NULL DEFAULT 0.0,
    line_total    REAL NOT NULL DEFAULT 0.0,
    status        TEXT DEFAULT 'Pending',        -- Pending|Received
    internal_barcodes TEXT DEFAULT '',         -- JSON list of pre-generated barcodes on receive
    received_at   TEXT,
    mfg_barcode   TEXT DEFAULT '',
    expiry_date   TEXT DEFAULT '',
    mfg_date      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_po_items_po_id ON po_items(po_id);
```

### Backfill migration (idempotent)
In `init_db()`, after table creation:
```python
# Populate suppliers from existing vendor_name values not yet registered
existing = {row[0] for row in _fetch("SELECT name FROM suppliers")}
for vendor in get_all_vendors():                  # database.py:821 — distinct vendor_name
    if vendor not in existing and vendor and vendor != "N/A":
        _insert_supplier_dialect(vendor)         # INSERT OR IGNORE with preferred=0
```
> **Note:** `init_db()` must avoid recursion (it calls `get_all_vendors` which itself opens a connection). Implement backfill as a **separate function** `migrate_suppliers_from_vendors()` called from `init_db()` after tables exist, using the **same open connection** (cursor passed in), not a new `get_all_vendors()` call. See §4.

---

## 4. Database Layer Additions

### 4.1 `database.py` (sqlite3 path) — add `@_db_fallback` functions

| Function | Signature | Purpose |
|---|---|---|
| `get_suppliers()` | `-> list[tuple]` | `SELECT id,name,contact_name,contact_email,contact_phone,address,preferred,sku,min_stock_level,lead_time_days,edi_endpoint,performance_notes FROM suppliers ORDER BY name ASC` |
| `get_supplier_by_id(supplier_id: int)` | `-> tuple \| None` | `SELECT ... WHERE id = ?` |
| `add_supplier(name, contact_name="", contact_email="", contact_phone="", address="", preferred=0, sku="", min_stock_level=0, lead_time_days=0, edi_endpoint="", performance_notes="")` | `-> int` | INSERT, return lastrowid; `UNIQUE` name → on IntegrityError raise `ValueError`. |
| `update_supplier(supplier_id, name, contact_name, contact_email, contact_phone, address, preferred, sku, min_stock_level, lead_time_days, edi_endpoint, performance_notes)` | `-> bool` | UPDATE WHERE id=?. |
| `delete_supplier(supplier_id)` | `-> bool` | DELETE WHERE id=? AND preferred=0 (block deletion of preferred). |
| `get_purchase_orders(status_filter=None)` | `-> list[tuple]` | SELECT ... JOIN suppliers; optional `WHERE status = ?`; ORDER BY created_at DESC. |
| `get_po_by_id(po_id)` | `-> tuple \| None` | SELECT single PO + vendor name. |
| `get_po_items(po_id)` | `-> list[tuple]` | SELECT line_number, product_name, vendor_sku, quantity, unit_price, line_total, status, ... ORDER BY line_number. |
| `get_next_po_number()` | `-> str` | `SELECT MAX(po_number) FROM purchase_orders` → increment; format `PO-{YYYY}-{NNNN}`. |
| `add_purchase_order(vendor_id, vendor_name, items: list[dict], notes="")` | `-> int` | INSERT PO + INSERT po_items rows in one transaction; compute subtotal/tax/total; return po_id. |
| `update_po_status(po_id, status)` | `-> bool` | UPDATE status + set `<status>_at` timestamp columns. **Must validate transition legality** (Draft→Submitted→Received→Closed only). |
| `add_po_item(po_id, product_name, quantity, unit_price, **rest)` | `-> int` | INSERT one po_item. |
| `update_po_item(item_id, quantity, unit_price)` | `-> bool` | UPDATE. |
| `delete_po_item(item_id)` | `-> bool` | DELETE (renumber line_numbers). |
| `update_po_totals(po_id)` | `-> None` | Recompute subtotal/sum(line_total)/tax from items. |
| `get_products_below_reorder_threshold()` | `-> list[tuple]` | **Auto-reorder core.** Returns `(name, qty, min_threshold, vendor_name, wholesale_price)` for drugs where `COUNT(*) ≤ MIN(reorder_threshold)` AND `reorder_threshold > 0`. |
| `receive_po_items(po_id, vendor_name, date_received, barcodes_by_item, price_map, expiry_map, mfg_map, barcode_generator)` | `-> list[str]` | Calls `receive_inventory_atomically()` per item with `pre_generated_barcodes`; updates po_items.status='Received' + `received_at` + `internal_barcodes`; sets PO.status='Received'. Single transaction. |

### 4.2 `db.py` (SQLAlchemy path)
Mirror the above inside the `class Database:` / `get_session()` text()-based pattern (see `db.py:844` `receive_inventory_atomically` template). Each function uses `with get_session() as s: s.execute(text(...))`. The `@_db_fallback` decorator in `database.py` transparently delegates; no change to `database.py` callers.

### 4.3 SqliteWALConnection reuse
```python
try:
    from ui_pos_retail import SqliteWALConnection
except ImportError:  # ui_pos_retail may be lazily loaded
    # Inline fallback identical to ui_pos_retail.py:136
    from ui_pos_retail import SqliteWALConnection  # re-exported alias not guaranteed → define inline
```
> **Decision:** Prefer `from ui_pos_retail import SqliteWALConnection`. Flag that `ui_inventory_management.py` duplicates it; recommend a future refactor to a shared `core_db.py`, but that is **out of scope** for this task (Surgical Editing: don't touch unrelated dead code).

---

## 5. Module: `archive/ui_supplier_order_management.py`

### 5.1 Module preamble (mirrors `ui_pos_retail.py:27-57` + `ui_inventory_management.py:15-46`)
```python
from __future__ import annotations
import logging, sqlite3, time, json, os
from datetime import datetime
from typing import Any, Callable, TypedDict
from collections import defaultdict

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n, database, audit_log, barcode_logic
from native_accel import fuzzy_search, generate_batch_barcodes, _native_accel_loaded

try:
    from ui_pos_retail import SqliteWALConnection
except ImportError:
    SqliteWALConnection = None  # type: ignore[assignment]
    log.warning("ui_pos_retail.SqliteWALConnection not importable; DB ops will fail loudly")

try:
    from async_ui import AsyncUI
    HAS_ASYNC: bool = True
except ImportError:
    AsyncUI = None  # type: ignore[assignment]
    HAS_ASYNC = False
    log.warning("async_ui not available; DB ops will run synchronously")

log = logging.getLogger("ui_supplier_order_management")
```

### 5.2 TypedDicts
- `SupplierRow(TypedDict)`: id, name, contact_name, contact_email, contact_phone, address, preferred(bool), sku, min_stock_level(int), lead_time_days(int), edi_endpoint, performance_notes.
- `PoRow(TypedDict)`: id, po_number, vendor_id, vendor_name, status, created_at, submitted_at, received_at, closed_at, total_cost(float), notes.
- `PoItemRow(TypedDict)`: id, po_id, line_number, product_name, quantity(int), unit_price(float), line_total(float), status, internal_barcodes(str).

### 5.3 `SupplierObserver` (Observer pattern)
Identical shape to `InventoryObserver` (`ui_inventory_management.py:113`). Events: `"suppliers_changed"`, `"purchase_orders_changed"`, `"po_item_added"`, `"po_item_removed"`.

### 5.4 `SupplierCrudManager`
Async-capable (methods run in AsyncUI workers). Self-contained DB helper using `SqliteWALConnection`:
- `load_all() -> list[SupplierRow]` — `SELECT ... FROM suppliers ORDER BY name`.
- `search(query, cutoff=60) -> list[SupplierRow]` — loads names, runs `fuzzy_search(query, [r["name"] ...], cutoff)` → returns matched rows **in ranked order**. (Pure-Python difflib fallback inside native_accel if rapidfuzz absent.)
- `get_by_id(supplier_id) -> SupplierRow | None`.
- `create(supplier: dict) -> int` — INSERT, `UNIQUE` guard, `audit_log.log_action("SUPPLIER_CREATE", ...)`.
- `update(supplier_id, supplier: dict) -> bool` — UPDATE + `audit_log.log_action("SUPPLIER_UPDATE", ...)`.
- `delete(supplier_id) -> bool` — DELETE + `audit_log.log_action("SUPPLIER_DELETE", ...)`.
- `set_preferred(supplier_id) -> None` — sets `preferred=1` on one, clears others (single preferred vendor). `audit_log`.

### 5.5 `PoCrudManager`
All ops use `SqliteWALConnection` + exponential backoff (inherited via context manager). Observer notifications on every mutate.
- `load_all(status_filter=None) -> list[PoRow]` — JOIN suppliers.
- `get_by_id(po_id) -> tuple[PoRow, list[PoItemRow]]`.
- `create(vendor_id, notes) -> int` — `get_next_po_number()`, INSERT PO + empty items, status=Draft.
- `add_item(po_id, item: dict) -> int` — INSERT po_item; `update_po_totals(po_id)`.
- `update_item(item_id, qty, unit_price) -> bool`.
- `delete_item(item_id) -> bool` — DELETE + renumber.
- `transition(po_id, new_status) -> bool` — **state-machine guard**: legal only Draft→Submitted→Received→Closed. Updates `<status>_at`. On `Received`: calls the **inventory-update path** (§6). `audit_log.log_action("PO_STATUS", ...)` for every transition.
- `compute_low_stock_groups() -> list[dict]` — queries `get_products_below_reorder_threshold()`, groups by vendor_name, picks the **preferred supplier** per vendor if one exists (else first supplier matching name), computes suggested qty = threshold + buffer (buffer = `max(threshold, 1)`). Returns `[{supplier, items: [{name, current_qty, threshold, suggested_qty, wholesale_price}]}]`.
- `auto_reorder() -> dict` — for each group: create a Draft PO with line items; returns summary `{po_count, item_count, low_stock_count}`. `audit_log.log_action("AUTO_REORDER", ...)`.

### 5.6 `SupplierEditorDialog(ctk.CTkToplevel)`  [DONE — implemented as `SupplierDialog`]
Mirror `ProductEditorDialog` (`ui_inventory_management.py:485-649`):
- `__init__(parent, title, supplier_id=None, initial=None, on_save=callback)`.
- `_build_form()` — scrollable form: Name, Contact Name, Email, Phone, Address, Preferred (checkbox), SKU, Min Stock Level (int), Lead Time (days, int), EDI Endpoint, Performance Notes (multiline Text).
- `_on_save_click()` — validate Name (required), Email (basic regex), numeric fields; build dict; `grab_release`; invoke `on_save(supplier_id, dict)`.
- `_validate_int(value) -> bool` helper.

### 5.7 `PoDetailDialog(ctk.CTkToplevel)`  [DONE — split into `PoItemDialog` + `ReceivePoDialog`; full PO-detail editor deferred to Chunk 3]
- `__init__(parent, po: PoRow, items: list[PoItemRow], manager: PoCrudManager, on_save, on_close)`.
- Line-item builder: a `ttk.Treeview` (columns: #0=product, qty, unit_price, line_total, status, received) with inline-edit entry overlay OR a simple grid of `CTkEntry` rows. **Recommendation:** editable Treeview via double-click opens a small `CTkEntry` popup for qty/unit_price — matches the "line-item builder" requirement without over-engineering.
- Toolbar buttons: **Add Item**, **Delete Item**, **Save PO**, **Submit PO**, **Receive PO**, **Close PO**.
- Status transition buttons enabled/disabled per current state (state-machine enforcement at UI + DB layer).
- On **Receive PO** (§6): disable buttons, dispatch `manager.receive_and_update_inventory(po_id)` to AsyncUI; on done, close dialog + notify observer.

### 5.8 `SupplierOrderManagementFrame(ctk.CTkFrame)` — dual pane

Layout (grid on the frame; mirrors `ui_inventory_management` 3-row but **dual-pane** as required):
```
Row 0 (fixed):  Top toolbar — title + refresh + "Generate Auto-Reorder PO" button
Row 1 (expands): SplitPane (ttk.PanedWindow horizontal) → 
                  Left  (weight 1): Suppliers pane
                  Right (weight 1): Purchase Orders pane
Row 2 (fixed):  Status bar — counts + low-stock alert badge
```

**Left Pane (Suppliers)** — `pack_propagate(False)` on panes per AGENTS.md §Protocol II.B:
- Toolbar: Search entry (`fuzzy_search` via `_on_supplier_search`, cutoff=60, live on `<KeyRelease>`), Add/Edit/Delete buttons, "Preferred" filter toggle.
- `ttk.Treeview` columns: Name, Contact, Email, Phone, Preferred (badge), Lead Time, Performance Notes. Vertical scrollbar. Double-click → `SupplierEditorDialog` (edit). Row tags: preferred=highlight.
- `grid_propagate(False)` on the tree container with a min-height.

**Right Pane (Purchase Orders):**
- Toolbar: PO search, status filter combobox (Draft/Submitted/Received/Closed/All).
- `ttk.Treeview` columns: PO#, Vendor, Status (badge), Items, Total, Created, Updated. Vertical scrollbar. Double-click → `PoDetailDialog`.
- Below the tree: a **line-item builder card** — a small form to add a new line item to the currently-open Draft PO (Product name Entry + Qty Spinbox + Unit Price Entry + Add button). `grid_columnconfigure` for elasticity; wraps text in "Performance Notes"/"Product name" via Treeview `heading` + column stretch.

**Async init:** call `AsyncUI.get().init(root)` if not bound (same as `ui_pos_retail._init_async:601`).

**`_debug_layout_geometry()`** — exact contract from `ui_pos_retail.py:1168`:
- `self.update_idletasks()`
- Assert left pane width ≥ 180 (sidebar minimum).
- Assert no child `x + w > root_w + 5` (off-screen clipping).
- Assert tree frames have non-zero w/h.
- Assert PanedWindow sash position is valid (left pane ≥ 180, right pane ≥ 180).
- Return `{issues: [...]}` dict; log warning if non-empty.

**Observer wiring:** `self._observer.register(self._on_supplier_changed)` + `self._observer.register(self._on_po_changed)`.

### 5.9 Module-level `setup_supplier_order_tab(self, parent=None)`
Exact shape of `setup_inventory_management_tab` (`ui_inventory_management.py:1318`):
```python
def setup_supplier_order_tab(self, parent=None):
    if parent is None:
        parent = self.tab_view
    frame = SupplierOrderManagementFrame(parent, app=self, fg_color="transparent")
    parent.add(frame, text=i18n.t("supplier_order_title"))
    self.supplier_order_frame = frame
    self._refresh_supplier_order_tab = frame.refresh
    return frame
```

---

## 6. Inventory Update on Receipt (PO → Received) — atomic + audited

Flow (`PoCrudManager.receive_and_update_inventory(po_id)`):
1. Load PO + items via `SqliteWALConnection`.
2. Pre-generate **all** barcodes in one batch, grouped by vendor: `generate_batch_barcodes(vendor_name, total_qty_for_vendor)` (returns list). Distribute per item. **If `native_accel` unavailable**, fall back to `barcode_logic.generate_internal_barcode(vendor)` per box (slower but identical format — `native_accel` already implements this internally).
3. Open **one** `SqliteWALConnection` (single transaction). For each PO line item:
   - Call `database.receive_inventory_atomically(vendor, product_name, date_received, qty, total_cost, unit_price, mfg_barcode, expiry, mfg_date, barcode_generator, pre_generated_barcodes=item_barcodes)`.
   - This inserts `qty` product rows + one `receiving_log` row, all in a sub-transaction. Because the outer `SqliteWALConnection` is `isolation_level=None` (autocommit) with WAL, each `receive_inventory_atomically` call manages **its own** `BEGIN/COMMIT`. To keep the whole receipt atomic, the new code wraps the per-item calls in a **retry loop** (exponential backoff on `sqlite3.OperationalError`) rather than one giant transaction — matching `ui_pos_retail._do_checkout:1006` retry pattern. On any `ValueError` (stale barcode) → fail fast (no retry). On `OperationalError` → retry up to 3× (0.1s, 0.2s, 0.4s).
4. After all items received, `update_po_status(po_id, "Received")` + mark each `po_items` row `status='Received'`, `internal_barcodes=json.dumps(item_barcodes)`.
5. `audit_log.log_action("PO_RECEIVE", details=f"PO#{po_number} received: {total_boxes} boxes for {n_items} items, vendor={vendor_name}")`.
6. Return `{po_number, boxes_received, items_received}` → UI callback shows `messagebox.showinfo` with `i18n.t("po_received_success", po=po_number, count=boxes_received)`.

> **Atomicity note:** True cross-item atomicity would require refactoring `receive_inventory_atomically` to accept an external cursor; that would touch `database.py`/`db.py` signatures (risk). The retry-loop approach matches the **existing** `ui_pos_retail` checkout pattern (`_do_checkout:1006`) and is the minimal, safe choice. Document this as a known limitation.

---

## 7. Async / Threading Contract

All DB reads & writes dispatch via `AsyncUI.get().run(func, callback, args)`:
- **Search** (`_on_supplier_search`, `_on_po_search`): debounced (250ms timer) `after` + AsyncUI.
- **Load** (`refresh`): AsyncUI → callback repopulates Treeviews.
- **Create/Update/Delete supplier**: AsyncUI → callback re-loads supplier list.
- **Generate Auto-Reorder**: AsyncUI → callback builds Draft POs + notifies observer.
- **Receive PO**: AsyncUI (long-running) → callback closes dialog + refreshes both panes.
- **Fallback:** If `HAS_ASYNC=False`, run synchronously via `self.after(0, ...)` wrapper (pattern: `ui_pos_retail._run_sync:630`).

Callbacks always guard `if error: messagebox.showerror(...)`.

---

## 8. Wiring Into `main_app.py:_wire_rx_extensions()` (exact edits)

Three surgical additions (mirroring the existing `inventory_mgmt` block):

```python
# (A) in _wire_rx_extensions nav-icon section, after line 80
ui_navigation._NAV_ICONS.setdefault("supplier_order_title", "🚛")

# (B) in _patched_init, after line 124 (tab_inventory_mgmt)
self.tab_supplier_order = self.tab_view.add(i18n.t("supplier_order_title"))

# (C) in _patched_init setup block, after line 141
from ui_supplier_order_management import setup_supplier_order_tab
setup_supplier_order_tab(self)

# (D) in _patched_on_tab_change, after line 181
elif current == i18n.t("supplier_order_title"):
    if hasattr(self, "supplier_order_frame"):
        self.supplier_order_frame.refresh()
```
No changes to `ui.py`, `ui_navigation.py`, or any existing module logic.

---

## 9. Tasks / Milestones (ordered, verifiable)

| # | Task | File(s) | Verifiable goal |
|---|---|---|---|
| T1 | Add `suppliers`, `purchase_orders`, `po_items` DDL + backfill to `init_db` | `database.py` (~line 238), `db.py` (~line 60) | `sqlite3 pharmacy.db ".schema suppliers"` shows 3 new tables; `SELECT name FROM suppliers` non-empty after backfill. |
| T2 | Add Supplier CRUD + PO CRUD + low-stock + receive DB functions | `database.py` (append ~line 1242), `db.py` (append ~line 920) | `python -c "import database; database.init_db(); database.add_supplier('TestVendor')"` succeeds; `get_products_below_reorder_threshold()` returns rows for products with `reorder_threshold>0` and count≤threshold. |
| T3 | Create `ui_supplier_order_management.py` module | new `archive/ui_supplier_order_management.py` | `py_compile` clean; `SupplierOrderManagementFrame` imports without error. |
| T4 | Implement dual-pane layout + `_debug_layout_geometry()` | same | `_debug_layout_geometry()` returns `{"issues": []}` on a 1024×768 window with ≥1 supplier & ≥1 PO. |
| T5 | Wire into `main_app._wire_rx_extensions()` | `main_app.py:58` | App launches; nav drawer shows 🚛 tab; tab opens `SupplierOrderManagementFrame`. |
| T6 | Add i18n keys to `locales/en.json` | `archive/locales/en.json` | `i18n.t("supplier_order_title")` → "Supplier & Order Management"; all new keys resolve. |
| T7 | Smoke test: full PO lifecycle | manual/automated | Create supplier → auto-reorder creates Draft PO → Submit PO → Receive PO → inventory boxes appear in `products` with `MED-XXXXXX` barcodes → `purchase_orders.status='Received'`. |
| T8 | Zero regression | `test_phase16.py`, `test_phase9_final_validation.py` | `python -m pytest archive/test_phase16.py archive/test_phase9_final_validation.py -q` → all pass; `exhaustive_verify.py` 105/105. |

**Milestone status:** DONE — T1, T2, T3 (infra), T6 (i18n — keys added to `en.json` AND propagated to `es/fr/de/ar/pt` to keep `test_phase9 [9.3.6]` green), T7 (PO-lifecycle smoke verified: create supplier→auto-reorder→Submit→Receive partial via `receipt_data`→`products` stocked→status=Received→Closed), T8 (zero regression). Dialog Chunk (§5.6 `SupplierDialog`, §5.7 `PoItemDialog` + `ReceivePoDialog`) `py_compile`-clean; manager-support verified functionally (23/23 managers + receipt_data partial receipt + tax_id round-trip + state-machine guards). **PENDING** — T4 (dual-pane `SupplierOrderManagementFrame` + `_debug_layout_geometry`), T5 (main_app wiring §5.9/§8), §6 `receive_and_update_inventory` (folded into `PoCrudManager._receive_with_data`; §5.8 frame not yet built). **Deviations from plan:** Chunk-2 prompt renamed `SupplierEditorDialog`→`SupplierDialog` and split `PoDetailDialog` into `PoItemDialog`+`ReceivePoDialog`; added `tax_id` column to `suppliers` (SupplierDialog field, propagated to sqlite DDL + SQLAlchemy ORM + ALTER migration); extended `PoCrudManager.transition` to accept `receipt_data` (ReceivePoDialog contract) implementing the §6 receipt flow at the manager layer since `database.py` is sealed.
| T9 | Audit-trace check | `audit_log.py` | After a PO lifecycle, `audit_log.get_logs()` contains `PO_STATUS` + `AUTO_REORDER` + `PO_RECEIVE` + `SUPPLIER_*` entries. |

---

## 10. Verification Plan

### 10.1 Static
```bash
cd archive
python -m py_compile ui_supplier_order_management.py
python -c "import native_accel; print(native_accel._native_accel_loaded())"
```

### 10.2 Layout geometry (VERIFICATION_CHECKLIST Protocol II.A/B)
```python
# In a smoke harness after root.update_idletasks():
results = frame._debug_layout_geometry()
assert results["issues"] == [], results["issues"]
# PanedWindow: left pane ≥ 180px, right pane ≥ 180px, no off-screen children
```
- **Extreme-value test:** Supplier with a 200-char performance-notes string — Notes column wraps; Treeview scrolls vertically without clipping.
- **Viewport test:** Resize to 800×600 — PanedWindow sash draggable, both panes stay ≥ 180px (sash `minsize=180`), scrollbars appear on both Treeviews.

### 10.3 Functional (lifecycle)
1. Add supplier "MedSupply" (preferred, lead_time=3).
2. Set a product's `reorder_threshold=3`, ensure `COUNT(*)<3`.
3. Click "Generate Auto-Reorder PO" → new Draft PO with 1 line item, suggested qty = 3+buffer.
4. Open PO detail → click **Submit** → status=Submitted (`submitted_at` set).
5. Click **Receive** → `receive_inventory_atomically` per item with `native_accel` pre-generated barcodes → `products` row count increases by `qty`; `po_items.status='Received'`; PO.status=Received.
6. Click **Close** → PO.status=Closed (`closed_at` set).

### 10.4 Zero regression
```bash
cd archive
python -m pytest test_phase16.py test_phase9_final_validation.py -q   # 136+24 must pass
python exhaustive_verify.py                                            # 105/105
```

### 10.5 Audit log
`audit_log.get_logs(search_query="PO_")` returns the auto-reorder, status-transition, and receive entries with timestamps.

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| No `suppliers` table exists → all CRUD fails | T1 adds the table + idempotent backfill; `add_supplier` `UNIQUE` guard prevents dupes on reruns. |
| Per-vendor barcode pre-gen mismatch across PO lines | Pre-generate one list per vendor, slice per item; assert `len(barcodes) == sum(qtys)`. |
| Cross-item atomicity on Receive (each `receive_inventory_atomically` commits independently) | Document as known limitation; retry-loop covers `OperationalError`. Full atomicity a future refactor (accept cursor param) — out of scope. |
| `SqliteWALConnection` import coupling to `ui_pos_retail` | Import guarded by `try/except`; fallback inline copy kept minimal. |
| rapidfuzz absent (slow fuzzy search) | `native_accel.fuzzy_search` already falls back to `difflib`; supplier lists are small so difflib is acceptable. |
| New i18n keys missing from non-English locales | `i18n.t()` falls back to English → no breakage; non-English translators can add later. |
| Existing vendor rows with `vendor_name='N/A'` | Backfill explicitly excludes `'N/A'`; products with no supplier link are excluded from auto-reorder (or grouped under a synthetic "Unassigned" supplier created on-demand). |
| State-machine transition bugs (e.g., jump Draft→Received) | Enforced at **two** layers: `PoCrudManager.transition()` guard + disabled UI buttons. |
| Layout clipping on small screens | `ttk.PanedWindow` with `sash` minsize=180; `grid_propagate(False)` on tree containers; `_debug_layout_geometry()` asserts in every smoke run. |

---

## 12. Out of Scope (explicitly)

- No changes to `ui.py`, `ui_navigation.py` base logic, label engine, checkout, or receive tab.
- No `supplier_id` FK backfill onto `products.vendor_name` (free-text preserved; name-match join only).
- No PyInstaller/packaging changes (`barcode_gen.pyd`/`rapidfuzz` already bundled per the hybrid plan T16/T17).
- No new top-level executable or entry point — single tab inside existing `PharmacyApp`.
- No C/C++ extensions (only rapidfuzz + barcode_gen already present).
