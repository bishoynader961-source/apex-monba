# Phase 17: Inventory Management Module — Implementation Plan

> **Status:** Planning — Implementation-Ready
> **Output file:** `archive/ui_inventory_management.py`
> **Entry point:** `archive/main_app.py` → `_wire_rx_extensions()` → `setup_inventory_management_tab(self)`
> **Date:** 2026-08-05
> **Target Python:** 3.12.7 | **GUI:** customtkinter 6.0.0

---

## 1. Context & Current State

### Existing codebase patterns (all in `archive/`)

| File | Role | Key APIs |
|---|---|---|
| `database.py` | SQLite CRUD layer | `add_product()`, `update_product_full()`, `delete_product()`, `get_all_products()`, `get_product_by_id()`, `search_products()`, `get_low_stock_products()`, `get_expiring_batches()`, `get_batches_expiring_within()` |
| `db.py` | SQLAlchemy ORM (optional) | Same function names as `database.py`; `@_db_fallback` in `database.py` tries ORM first, falls back to sqlite3 |
| `async_ui.py` | Thread-pool dispatcher | `AsyncUI.get().run(func, callback, args)` — marshals callback back to main thread via `root.after(0)` |
| `i18n.py` | Translation system | `i18n.t(key, **kwargs)` — falls back English → raw key |
| `ui_navigation.py` | Color palette | `COLOR_CARD_BG`, `COLOR_SUCCESS`, `COLOR_WARNING`, `COLOR_ERROR`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_SECONDARY`, `COLOR_SIDEBAR_BG`, `COLOR_SIDEBAR_HOVER` |
| `ui_helpers.py` | Treeview styling | `apply_treeview_style(tree)` — configures `odd`/`even`/`status_green`/`status_yellow`/`status_red` tags |
| `ui_modals.py` | Dialog classes | `EditBatchDialog(parent, row)` — full-field editor for a single batch |
| `ui_pos_retail.py` | Reference module (Phase 16) | `TaxCalculator`, `SqliteWALConnection`, `CartObserver` — proven patterns to replicate |
| `ui_inventory_tab.py` | Existing inventory browser | `setup_inventory_tab(self)` with grouped Treeview, search, sort, sell, edit, delete, import/export |
| `config.json` | Runtime config | `low_stock_threshold` (default 5), `expiry_alarm_days` (default 50), `tax_rate` (default 0.0) |

### Database schema (`products` table, key columns)

```
id, name, price, manufacturer_barcode, internal_unique_barcode (UNIQUE),
status, expiry_date, manufacture_date, vendor_name,
dea_schedule, wholesale_price, reorder_threshold
```

Serialized model: 1 row = 1 box. Quantity = COUNT(*) of rows with same name + status='In Stock'.

### CRUD gap analysis

The existing `ui_inventory_tab.py` provides a browser-view inventory tab (read-only grouped display with sell/edit/delete actions scattered across module-level functions). It does NOT provide:
- A unified, self-contained CRUD interface on a single Treeview
- Inline editing capability (currently delegates to `EditBatchDialog`)
- Visual row-level indicators (color tags for low-stock/expiry)
- Async loading (currently synchronous)
- WAL mode or retry logic (direct `sqlite3.connect` everywhere)
- Observer pattern decoupling

`ui_inventory_management.py` fills this gap with a comprehensive, production-ready module.

---

## 2. Architecture Decisions

### 2.1 Layered Design (mirrors Project Map §7)

```
View        (ui_inventory_management.py)
  ├── InventoryObserver   — Observer pattern: notifies subscribers on CRUD events
  ├── SqliteWALConnection — Context manager: WAL + busy_timeout + retry (reused from ui_pos_retail pattern)
  ├── InventoryCrudManager — Business logic: async CRUD ops using SqliteWALConnection
  └── InventoryManagementFrame  — CTkFrame: Treeview + toolbar + inline-editor + action buttons

Controller  (ui_inventory_management.py)
  ├── setup_inventory_management_tab(self)  — factory attached to PharmacyApp
  └── on_tab_change handler                   — calls frame.refresh() on tab activation

Model     (database.py + db.py)
  ├── add_product(name, price, mfg_barcode, int_barcode, expiry, mfg, vendor, ...)
  ├── update_product_full(product_id, name, price, mfg_barcode, int_barcode, expiry, mfg, status, vendor, ...)
  ├── delete_product(product_id)  — NEW (see §5.3)
  ├── get_all_in_stock_batches(sort_by) — existing, used for Treeview population
  └── get_low_stock_products(threshold) — existing, used for visual indicators
```

### 2.2 Threading Strategy (non-blocking mainloop)

- All Treeview population, CRUD write operations, and search queries run via `AsyncUI.get().run(func, callback, args)`.
- Callback results marshal back to main thread via `root.after(0, callback)`.
- If `AsyncUI` unavailable (ImportError), fall back to synchronous execution with a loading spinner.
- Pattern matches `ui_pos_retail.py:613-642` and `ui_checkout_tab.py:360-377`.
- Never touch Tkinter widgets from background threads.

### 2.3 SQLite WAL + Retry Strategy

- `SqliteWALConnection` context manager:
  1. Opens `sqlite3.connect(db_path, timeout=30.0, check_same_thread=False, isolation_level=None)`
  2. `PRAGMA journal_mode=WAL`
  3. `PRAGMA busy_timeout=30000`
  4. `PRAGMA synchronous=NORMAL`
  5. Retries on `sqlite3.OperationalError` up to 3 attempts with exponential backoff (0.1s, 0.2s, 0.4s)
  6. All queries use `?` parameterized placeholders
- Used in `InventoryCrudManager._do_load_inventory()`, `_do_search()`, `_do_create()`, `_do_update()`, `_do_delete()`.

### 2.4 Observer Pattern for State Management

- `InventoryObserver` maintains a list of callback functions `(event: str, data: dict[str, Any]) -> None`.
- After every CRUD mutation, `InventoryCrudManager` calls `self._observer.notify("inventory_changed", {"action": ..., "row_id": ..., "row_data": ...})`.
- Observer callbacks:
  - `InventoryManagementFrame._on_inventory_changed()` → reloads Treeview, reapplies visual indicators, updates status bar
- This decouples the CRUD manager from the Treeview UI.

### 2.5 Visual Indicator Strategy

- **Low stock:** Rows where product name has ≤ `low_stock_threshold` in-stock boxes get `status_yellow` tag (from `ui_helpers.apply_treeview_style`).
- **Expiring soon:** Rows where `expiry_date` ≤ today + `expiry_alarm_days` get `status_red` tag.
- **Low stock + expiring:** `status_red` takes priority (most urgent).
- Tags configured via `apply_treeview_style()` from `ui_helpers.py`.

---

## 3. Component Specifications

### 3.1 SqliteWALConnection (reused pattern from ui_pos_retail.py)

```python
class SqliteWALConnection:
    """Context manager: WAL-mode SQLite connection with retry on lock.

    Usage:
        with SqliteWALConnection(db_path, max_retries=3) as (conn, cur):
            cur.execute("SELECT ... WHERE col = ?", (val,))
            rows = cur.fetchall()
    """
    def __init__(self, db_path: str, max_retries: int = 3,
                 initial_delay: float = 0.1) -> None: ...
    def __enter__(self) -> tuple[sqlite3.Connection, sqlite3.Cursor]: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
```

- Identical implementation to `ui_pos_retail.py:136-189`. Reuse verbatim — no duplication.

### 3.2 InventoryObserver

```python
class InventoryObserver:
    """Observer pattern: notifies registered callbacks on inventory mutations."""

    def __init__(self) -> None: ...
    def register(self, callback: Callable[[str, dict[str, Any]], None]) -> int: ...
    def unregister(self, callback: Callable[[str, dict[str, Any]], None]) -> None: ...
    def notify(self, event: str, data: dict[str, Any]) -> None: ...
```

- Same pattern as `ui_pos_retail.CartObserver` (`ui_pos_retail.py:192-221`).

### 3.3 InventoryCrudManager

```python
class InventoryCrudManager:
    """Async CRUD operations for the products table.

    All database operations run via AsyncUI thread pool. Results are
    marshaled back to the main thread through callbacks.
    """

    def __init__(self, db_path: str) -> None: ...
    def load_all(self, sort_by: str = "name") -> list[dict[str, Any]]: ...
    def search(self, query: str, sort_by: str = "name") -> list[dict[str, Any]]: ...
    def create(self, product: dict[str, Any]) -> int: ...
    def update(self, product_id: int, product: dict[str, Any]) -> bool: ...
    def delete(self, product_id: int) -> bool: ...
    def get_by_id(self, product_id: int) -> dict[str, Any] | None: ...
```

- Uses `SqliteWALConnection` for all read/write operations.
- Returns plain `dict[str, Any]` rows (not raw tuples) for cleaner UI binding.
- `create()` requires `barcode_logic.generate_internal_barcode(vendor_name)` to produce the unique internal barcode.
- `delete()` calls `database.delete_product(product_id)` if it exists, or executes raw `DELETE FROM products WHERE id = ?` as fallback.
- All methods are synchronous functions meant to be called via `AsyncUI.run()`.

### 3.4 InventoryManagementFrame

```python
class InventoryManagementFrame(ctk.CTkFrame):
    """Full CRUD inventory management interface.

    Layout (2-column grid):
    Row 0: Toolbar — search bar, add/edit/delete buttons, sort selector, refresh
    Row 1: Central Treeview data grid with vertical scrollbar
    Row 2: Status bar — item count, low-stock count, expiring count, last refreshed

    All list operations (load, search, create, update, delete) run asynchronously
    via AsyncUI to keep the UI mainloop responsive.

    Visual indicators:
      - Low stock rows: yellow tag (≤ low_stock_threshold in-stock)
      - Expiring soon rows: red tag (expiry ≤ today + expiry_alarm_days)
    """

    def __init__(self, parent: ctk.CTkBaseClass, app: Any | None = None,
                 **kwargs: Any) -> None: ...

    # Build methods
    def _configure_grid(self) -> None: ...
    def _build_toolbar(self) -> None: ...
    def _build_treeview(self) -> None: ...
    def _build_status_bar(self) -> None: ...

    # Display
    def _populate_tree(self, rows: list[dict[str, Any]]) -> None: ...
    """Populate the Treeview with rows. O(n) where n = len(rows).
    Applies low-stock and expiring tags. Sorting is O(n log n) per click."""
    def _apply_row_tags(self, iid: str, row: dict[str, Any]) -> None: ...
    def _refresh_status_bar(self) -> None: ...

    # Async operations
    def _run_async(self, func: Callable, callback: Callable[[Any, Any], None],
                   args: tuple = ()) -> None: ...
    def _on_inventory_changed(self, event: str, data: dict[str, Any]) -> None: ...
    """Observer callback: reload Treeview + status bar after CRUD mutation."""
    def _do_load_inventory(self, sort_by: str) -> list[dict[str, Any]]: ...
    """Background: load all in-stock products via SqliteWALConnection. O(n) where n = row count."""

    # Search
    def _on_search(self, event: Any | None = None) -> None: ...
    """Submit search to background thread."""
    def _do_search(self, query: str, sort_by: str) -> list[dict[str, Any]]: ...
    """Background: LIKE search on name, barcodes, vendor, expiry. O(n) scan or O(log n) indexed."""
    def _on_search_done(self, rows: list[dict[str, Any]] | None, error: Any) -> None: ...

    # CRUD handlers
    def _on_add(self) -> None: ...
    def _on_edit(self) -> None: ...
    def _on_delete(self) -> None: ...
    def _on_refresh(self) -> None: ...
    def _on_sort_change(self, sort_key: str) -> None: ...

    # Inline editor
    def _open_editor(self, row: dict[str, Any] | None = None) -> None: ...
    """Open a modal or inline form for Add/Edit. Uses EditBatchDialog for Edit,
    new inline form for Add (or reuse EditBatchDialog with row=None sentinel)."""

    # Debug
    def _debug_layout_geometry(self) -> dict[str, Any]: ...
    """Assert layout integrity after update_idletasks()."""

    # Public API
    def refresh(self) -> None: ...
    def get_selected_row(self) -> dict[str, Any] | None: ...
```

### 3.5 Tab setup factory

```python
def setup_inventory_management_tab(self: Any, parent: Any | None = None) -> InventoryManagementFrame:
    """Tab-setup function attached to PharmacyApp via monkey-patch.

    Expects main_app.py to have already created:
        self.tab_inventory_mgmt = self.tab_view.add(i18n.t("inventory_mgmt_title"))

    After calling, PharmacyApp has:
        self.inventory_mgmt_frame          — InventoryManagementFrame instance
        self._refresh_inventory_mgmt_tab   — lambda calling frame.refresh()
    """
    ...
```

---

## 4. UI Layout Specification

```
InventoryManagementFrame (grid, 2 columns)
├── Row 0: Toolbar (fixed height, grid_propagate(False))
│   ├── Left: Search entry (CTkEntry, width=280, Return → _on_search)
│   ├── Search button → _on_search
│   ├── Refresh button → _on_refresh
│   ├── Add button (+) → _on_add
│   ├── Edit button (✎) → _on_edit
│   ├── Delete button (✕) → _on_delete
│   ├── Sort selector (CTkSegmentedButton): Name, Expiry, Vendor, Price
│   └── Filter selector (CTkSegmentedButton): All, Low Stock, Expiring, Out of Stock
├── Row 1: Treeview (expands, weight=1)
│   ├── Columns: ID | Name | Price | Mfg Barcode | Int. Barcode | Status | Expiry | Vendor | Qty*
│   ├── Vertical scrollbar (ttk.Scrollbar)
│   ├── Row tags: odd/even striping, status_yellow (low stock), status_red (expiring)
│   ├── Double-click → inline edit row
│   └── Single-click → enable/disable Edit & Delete buttons
├── Row 2: Status bar (fixed height, grid_propagate(False))
│   ├── Total items count
│   ├── Low-stock count (yellow badge)
│   ├── Expiring-soon count (red badge)
│   └── Last refreshed timestamp
```

**Layout integrity rules (per VERIFICATION_CHECKLIST.md §1-2):**
- Toolbar and status bar: `grid_propagate(False)` with fixed min-height
- Treeview: has `ttk.Scrollbar` for vertical scrolling
- No hardcoded English strings — all via `i18n.t()`
- `_debug_layout_geometry()` verifies: toolbar height > 0, status bar height > 0, treeview dimensions > 0, no child clipping

### 4.1 Inline Editor Modal

Reuse `EditBatchDialog` from `ui_modals.py` for the **Edit** path (existing, tested, full-field editor). For **Add**, either:
- Option A: Extend `EditBatchDialog` to accept `row=None` (creates Add mode), OR
- Option B: Create a lightweight `AddProductDialog` in-module.

**Decision:** Option A — extend `EditBatchDialog` to handle `row=None`. The dialog already has all fields (Name, Price, Mfg Barcode, Internal Barcode, Expiry, Mfg Date, Vendor, Status). For Add mode, internal barcode is auto-generated via `barcode_logic.generate_internal_barcode(vendor_name)`.

This minimizes new code and reuses the tested dialog. The plan will specify passing `row=None` to `EditBatchDialog.__init__`.

---

## 5. CRUD Data Flow Specifications

### 5.1 Schema mapping (database row → Treeview row)

Database `products` columns → Treeview columns:

| Column | DB field | Format |
|---|---|---|
| ID | `id` | int |
| Name | `name` | str |
| Price | `price` | `$X.XX` |
| Mfg Barcode | `manufacturer_barcode` | str |
| Int. Barcode | `internal_unique_barcode` | str |
| Status | `status` | str ("In Stock" / "Sold") |
| Expiry | `expiry_date` | str (YYYY-MM-DD or "N/A") |
| Mfg Date | `manufacture_date` | str (YYYY-MM-DD or "N/A") |
| Vendor | `vendor_name` | str ("N/A" fallback) |
| Qty* | (computed) | COUNT(*) WHERE name=X AND status='In Stock' |

**Qty column:** Shows the count of in-stock boxes for the same product name. Computed in `_populate_tree()` by calling `database.get_low_stock_products()` or by pre-aggregating from the loaded batch list in memory. For O(1) Treeview population, aggregate in-memory during `_do_load_inventory`:

```python
def _do_load_inventory(self, sort_by: str) -> list[dict[str, Any]]:
    # Time complexity: O(n) where n = total product rows
    rows = database.get_all_in_stock_batches(sort_by=sort_by)
    # Group by name for qty aggregation
    qty_map: dict[str, int] = defaultdict(int)
    for row in rows:
        qty_map[row[1]] += 1  # row[1] = name
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "name": row[1],
            "price": row[2],
            "mfg_barcode": row[3],
            "int_barcode": row[4],
            "status": row[5],
            "expiry_date": row[6] or "N/A",
            "mfg_date": row[7] or "N/A",
            "vendor": row[8] or "N/A",
            "qty": qty_map[row[1]],
        })
    return result
```

### 5.2 Create flow (Add new product)

```
User clicks "Add"
  → _on_add()
  → _open_editor(row=None)
  → EditBatchDialog(self, row=None)
    → User fills: Name, Price, Mfg Barcode, Expiry, Mfg Date, Vendor, Status
    → On save → _save_create()
      → validate_name_non_empty
      → validate_price_is_float
      → validate_date_format (if provided)
      → generate_internal_barcode(vendor_name) → unique internal barcode
      → async_run(InventoryCrudManager.create(product_dict))
        → _do_create: SqliteWALConnection → INSERT INTO products ...
      → _on_create_done: observer.notify("inventory_changed")
        → _on_inventory_changed → reload Treeview + status bar
```

### 5.3 Update flow (Edit existing product)

```
User selects a row → clicks "Edit"
  → _on_edit()
  → get_selected_row() → row dict
  → _open_editor(row=row)
  → EditBatchDialog(self, row)
    → User edits fields → _save() calls update_product_full()
    → _do_update: SqliteWALConnection → UPDATE products SET ... WHERE id = ?
    → _on_update_done: observer.notify("inventory_changed")
      → _on_inventory_changed → reload Treeview + status bar
```

### 5.4 Delete flow

```
User selects a row → clicks "Delete"
  → _on_delete()
  → Admin PIN prompt (CTkInputDialog, PIN "1234")
  → _do_delete: SqliteWALConnection → DELETE FROM products WHERE id = ?
  → _on_delete_done: observer.notify("inventory_changed")
    → _on_inventory_changed → reload Treeview + status bar
```

**Note on `database.delete_product()`:** This function does NOT exist in `database.py`. The existing `ui_inventory_tab.py` uses a raw `sqlite3.connect` + `DELETE FROM products WHERE id = ?` in `_delete_batch()`. The plan will use `SqliteWALConnection` for the delete operation in `InventoryCrudManager._do_delete`.

### 5.5 Search flow

```
User types in search entry → presses Enter (or clicks Search)
  → _on_search()
  → async_run(_do_search, _on_search_done, (query, sort_by))
    → _do_search: SqliteWALConnection → SELECT ... WHERE name LIKE ? OR mfg_barcode LIKE ? OR int_barcode LIKE ? ...
    → returns list[dict[str, Any]]
  → _on_search_done(rows): populate Treeview (not full reload, filtered view)
```

### 5.6 Sort flow

```
User clicks a Treeview column header or changes Sort segmented button
  → _on_sort_change(sort_key)
  → async_run(_do_load_inventory, callback, (sort_key,))
  → _on_load_done: populate Treeview with sorted rows
```

**Time complexity of sorting:** O(n log n) where n = number of in-stock product rows. The SQL `ORDER BY` clause handles sorting at the database level. Python-side in-memory sorting via `list.sort()` is O(n log n). Documented in docstrings.

---

## 6. External Integration Error Handling

Per the user requirement: "comprehensive error handling using the standard logging module, including error handling for external integrations like payment bindings or webhooks."

The module will define a hook for optional external integrations:

```python
def _on_external_payment_binding_error(self, error: Exception) -> None:
    """Handle errors from payment binding integration (e.g., external POS API).

    Logs the error and notifies the user. Does NOT crash the inventory module.
    """
    log.error("Payment binding error in inventory management: %s", error, exc_info=True)
    messagebox.showerror(i18n.t("error"), f"{i18n.t('payment_binding_error', default='Payment binding failed')}:\n{error}")
```

```python
def _on_webhook_notification_error(self, url: str, error: Exception) -> None:
    """Handle errors from webhook notifications (e.g., inventory change webhook).

    Logs the error and queues a retry if a retry mechanism is configured.
    """
    log.error("Webhook notification failed for %s: %s", url, error, exc_info=True)
```

These are defensive hooks — the module does not make external calls itself, but provides extension points that downstream code can override. The logging uses `exc_info=True` for full tracebacks.

---

## 7. i18n Key Audit

### New keys required in `locales/en.json` (and all 6 locale files: en, de, es, fr, pt, ar)

| Key | English Value | Purpose |
|---|---|---|
| `inventory_mgmt_title` | "Inventory Management" | Tab title |
| `inventory_mgmt_subtitle` | "Full CRUD inventory browser with real-time stock monitoring" | Tab subtitle |
| `inventory_mgmt_search_placeholder` | "Search by name, barcode, vendor, or expiry..." | Search entry placeholder |
| `inventory_mgmt_add` | "Add Product" | Add button |
| `inventory_mgmt_edit` | "Edit" | Edit button |
| `inventory_mgmt_delete` | "Delete" | Delete button |
| `inventory_mgmt_refresh` | "Refresh" | Refresh button |
| `inventory_mgmt_search_btn` | "Search" | Search button |
| `inventory_mgmt_low_stock` | "Low Stock" | Filter option |
| `inventory_mgmt_expiring` | "Expiring Soon" | Filter option |
| `inventory_mgmt_out_of_stock` | "Out of Stock" | Filter option |
| `inventory_mgmt_all` | "All" | Filter option |
| `inventory_mgmt_total_items` | "Total Items: {count}" | Status bar |
| `inventory_mgmt_low_stock_count` | "Low Stock: {count}" | Status bar |
| `inventory_mgmt_expiring_count` | "Expiring: {count}" | Status bar |
| `inventory_mgmt_last_refresh` | "Last Refresh: {time}" | Status bar |
| `inventory_mgmt_qty_column` | "Qty" | Treeview column header |
| `inventory_mgmt_sort_name` | "Name" | Sort option |
| `inventory_mgmt_sort_expiry` | "Expiry" | Sort option |
| `inventory_mgmt_sort_vendor` | "Vendor" | Sort option |
| `inventory_mgmt_sort_price` | "Price" | Sort option |
| `inventory_mgmt_confirm_delete` | "Confirm Deletion" | Delete dialog title |
| `inventory_mgmt_delete_prompt` | "Enter Admin PIN to confirm deletion:" | PIN prompt |
| `inventory_mgmt_invalid_pin` | "Invalid PIN. Deletion cancelled." | Error message |
| `inventory_mgmt_deleted` | "Product deleted successfully." | Success message |
| `inventory_mgmt_save_failed` | "Failed to save product: {error}" | Error message |
| `inventory_mgmt_load_error` | "Failed to load inventory: {error}" | Error message |
| `inventory_mgmt_empty_selection` | "Please select a product to edit." | Warning |
| `inventory_mgmt_empty_cart_n/A` | N/A (not applicable) | N/A |
| `inventory_mgmt_loading` | "Loading..." | Loading state |
| `payment_binding_error` | "Payment binding failed" | External integration error |
| `webhook_error` | "Webhook notification failed" | External integration error |

**Total new keys: 30**

### Existing keys reused from en.json

`name`, `price`, `vendor`, `expiry_date`, `quantity`, `manufacturer_barcode`, `internal_barcode`, `status`, `manufacture_date`, `search`, `refresh`, `add`, `error`, `info`, `success`, `warning_msg`, `cancel`, `save` — these already exist in `en.json` and can be reused.

### Translation strategy for non-English locales

Each new key must be added to `locales/{de,es,fr,pt,ar}.json` with English fallback values (same as en.json). The `i18n.t()` function falls back to English → raw key, so any missing keys will still display the English value.

---

## 8. File Placement

- **Primary file:** `archive/ui_inventory_management.py` (~450-500 lines)
- **Import location:** `archive/main_app.py` line 108 area — add `from ui_inventory_management import setup_inventory_management_tab`
- **Tab creation:** In `_wire_rx_extensions()` `_patched_init()`, add tab:
  ```python
  self.tab_inventory_mgmt = self.tab_view.add(i18n.t("inventory_mgmt_title"))
  setup_inventory_management_tab(self)
  ```
- **Nav icon:** `ui_navigation._NAV_ICONS.setdefault("inventory_mgmt_title", "📋")`
- **All imports assume `archive/` is on `sys.path`** (injected by `main_app.py:main()`)

---

## 9. Implementation Task List

| # | Task | Spec Reference |
|---|---|---|
| T1 | Add 30 new i18n keys to all 6 locale files (en, de, es, fr, pt, ar) | §7 |
| T2 | Implement `SqliteWALConnection` context manager (WAL + busy_timeout + retry + parameterized queries) | §3.1 |
| T3 | Implement `InventoryObserver` class (register/unregister/notify) | §3.2 |
| T4 | Implement `InventoryCrudManager` — async CRUD ops using `SqliteWALConnection` | §3.3 |
| T5 | Implement `InventoryManagementFrame.__init__` + `_configure_grid` | §3.4 |
| T6 | Implement `_build_toolbar` — search, add, edit, delete, refresh, sort, filter | §4 |
| T7 | Implement `_build_treeview` — 9 columns + tags + scrollbars + bind events | §4 |
| T8 | Implement `_build_status_bar` — item count, low-stock, expiring, last refresh | §4 |
| T9 | Implement `_populate_tree` — O(n) populate with qty aggregation + visual tags | §3.4, §5.1 |
| T10 | Implement `_apply_row_tags` — low-stock yellow, expiring red | §2.5 |
| T11 | Implement async load flow: `_run_async` → `_do_load_inventory` → `_on_load_done` → `_populate_tree` | §2.2 |
| T12 | Implement search flow: `_on_search` → async `_do_search` → `_on_search_done` | §5.5 |
| T13 | Implement CRUD handlers: `_on_add`, `_on_edit`, `_on_delete`, `_on_refresh` | §5.2-5.4 |
| T14 | Implement observer callback `_on_inventory_changed` → reload Treeview + status bar | §2.4 |
| T15 | Implement `_on_sort_change` and `_on_filter_change` | §5.6 |
| T16 | Implement `_open_editor` — reuse `EditBatchDialog` for add (row=None) and edit | §4.1 |
| T17 | Implement `_debug_layout_geometry` with programmatic assertions | §3.4 |
| T18 | Implement `setup_inventory_management_tab(self, parent=None)` factory function | §3.5 |
| T19 | Wire into `main_app.py` `_wire_rx_extensions()` — tab creation + nav icon | §8 |
| T20 | Add comprehensive type hints to ALL function signatures | §3 |
| T21 | Add docstrings to ALL methods, including time complexity | §3 |
| T22 | Integrate external integration error handlers (payment binding, webhooks) | §6 |

---

## 10. Verification Plan

### Pre-build (static analysis)
```bash
cd archive
python -m py_compile ui_inventory_management.py                     # No syntax errors
python -c "import ui_inventory_management; print('OK')"              # Import without error
```

### Import & structure test
```python
import ui_inventory_management
assert hasattr(ui_inventory_management, 'InventoryManagementFrame')
assert hasattr(ui_inventory_management, 'setup_inventory_management_tab')
assert hasattr(ui_inventory_management, 'SqliteWALConnection')
assert hasattr(ui_inventory_management, 'InventoryObserver')
assert hasattr(ui_inventory_management, 'InventoryCrudManager')
```

### SqliteWALConnection retry test
- Mock a `sqlite3.OperationalError("database is locked")` on first `execute()` call
- Assert retry succeeds within `max_retries` attempts
- Assert `PRAGMA journal_mode=WAL` was set

### Observer pattern test
- Create `InventoryObserver`, register a callback
- Call `notify()` → assert callback was invoked with correct event + data

### InventoryCrudManager test
- `_do_load_inventory("name")` → returns list of dicts with all 10 keys
- `_do_search("aspirin", "name")` → returns matching rows
- `_do_create({...})` → returns new product_id
- `_do_update(id, {...})` → returns True
- `_do_delete(id)` → returns True

### Functional integration (requires running app — manual)
1. Launch `python main_app.py` from `archive/`
2. Navigate to "Inventory Management" tab (📋 icon)
3. Verify Treeview shows all in-stock products with 9 columns
4. Verify low-stock rows have yellow tag, expiring rows have red tag
5. Click "Add Product" → fill form → save → verify new row appears
6. Select a row → click "Edit" → modify → save → verify Treeview updates
7. Select a row → click "Delete" → enter PIN → verify row removed
8. Search by name/barcode → verify filtered results
9. Change sort column → verify Treeview re-sorts
10. Verify `_debug_layout_geometry()` logs no issues

### Zero regression
- Run existing test suite: `python -m pytest archive/test_phase16.py -v` (25 tests must still pass)
- Run root-level tests: `python -m pytest archive/test_phase16.py archive/test_phase9_final_validation.py` (all must pass)
- Verify `main_app.py` import chain works: `python -c "import main_app; print('OK')"`

---

## 11. Edge Cases & Failure Modes

| Scenario | Behavior |
|---|---|
| Database locked during load | `SqliteWALConnection` retries 3× with backoff, then raises → `_on_load_done` shows error messagebox, Treeview shows empty state |
| Barcode not found in search | Treeview shows "No results found" message |
| Empty Treeview (no products) | Status bar shows "Total Items: 0", all buttons except Add disabled |
| Admin PIN wrong on delete | Messagebox: "Invalid PIN. Deletion cancelled." |
| Add with existing internal barcode | `generate_internal_barcode()` uses `uuid.uuid4().hex[:6]` — collision is cryptographically negligible |
| Invalid price format | EditBatchDialog validates `float(price)`, shows error if not parseable |
| Invalid date format | Validate with `datetime.strptime(date, "%Y-%m-%d")`, show error messagebox |
| Very long product name (50+ chars) | Treeview column auto-width; name column has horizontal overflow handled by column stretching |
| Window resized to minimum | Grid weights distribute space; toolbar/status bar have `grid_propagate(False)` to resist crushing |
| AsyncUI unavailable | Synchronous fallback via `_run_sync` — same behavior, brief UI freeze acceptable |
| Payment binding error | `_on_external_payment_binding_error()` logs with `exc_info=True`, shows messagebox, does not crash |
| Webhook notification error | `_on_webhook_notification_error()` logs with `exc_info=True`, does not block inventory operations |

---

## 12. Code Quality Standards

- **No print statements** — use `logging.getLogger("ui_inventory_management")` throughout
- **No `// TODO`** — all functions fully implemented
- **No hardcoded English strings in UI** — all via `i18n.t()`
- **All DB queries parameterized** — `?` placeholders only
- **All DB connections enable WAL** — `PRAGMA journal_mode=WAL`
- **Thread-safe UI updates** — all widget updates via `root.after()` or main-thread callbacks
- **Python 3.10+ type hints** — `list[dict[str, Any]]`, `int | None`, `tuple[str, ...]`
- **Docstrings on all methods** — including time complexity for O(n) and O(n log n) operations
- **`grid_propagate(False)`** on fixed-size panels per VERIFICATION_CHECKLIST Protocol II.B
- **Reusability:** `SqliteWALConnection` and `InventoryObserver` are identical patterns to `ui_pos_retail.py` — copy verbatim to avoid divergence
- **Decoupled UI:** CRUD manager has zero import of CTK — pure data layer

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `delete_product()` doesn't exist in `database.py` | Use `SqliteWALConnection` with raw `DELETE FROM products WHERE id = ?` — matches existing `_delete_batch` pattern |
| `EditBatchDialog` doesn't support `row=None` | Extend `EditBatchDialog.__init__` to detect `row=None` and switch to Add mode (auto-generate barcode) |
| Duplicate nav icon name collision with existing inventory tab | Use unique key `inventory_mgmt_title` → nav icon 📋; existing inventory tab key is `inventory` → 📦. No collision. |
| `database.get_all_in_stock_batches()` may not exist | Already exists at `database.py:402-422` — confirmed via grep |
| `get_dashboard_metrics()` returns low_stock list | Use it for quick status bar counts; falls back to manual `get_low_stock_products()` if needed |
| Column count mismatch between DB row and Treeview | Map via dict keys, not positional indexes — safer and more readable |

---

## 14. Success Metrics

1. `python -m py_compile ui_inventory_management.py` → exit 0, no errors
2. `python -c "import ui_inventory_management; print('OK')"` → prints OK
3. `SqliteWALConnection` sets `PRAGMA journal_mode=WAL` on connect
4. `InventoryObserver.notify()` invokes all registered callbacks
5. Treeview shows low-stock rows with yellow tag, expiring rows with red tag
6. All CRUD operations succeed end-to-end with async dispatch
7. `_debug_layout_geometry()` returns no issues
8. 0 regressions in existing test suite
9. 30 new i18n keys present in all 6 locale files
