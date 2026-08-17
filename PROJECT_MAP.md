# Project Map

> PROJECT STATUS: ARCHITECTURE AUDIT — SERIALIZED TRACKING

> Pharmacy Management & Label Design Suite — desktop application for
> serialized inventory management, data storage, barcode/label generation, and custom label design.
> Auto-generated from the codebase at `E:\my progam pharmacy`.
> Last synced: 2026-08-04

---

## 1. Paradigm Shift: Bulk Quantity Tracking → Serialized Unit-Level Tracking

### Old Model (Bulk)
- One row = N boxes (e.g., 50 units of Aspirin)
- Stock tracked via `quantity INTEGER` column
- Sale decrements quantity by 1
- No individual box identity — only batch-level tracking
- Vendor linked loosely via batch metadata

### New Model (Serialized)
- **One row = exactly 1 physical box**
- Stock tracked via `COUNT(*)` of rows with `status = 'In Stock'`
- Sale **deletes** the row from `products` and **inserts** into `sold_items`
- Every box has a **cryptographically unique `internal_barcode`** (format: `{VENDOR[:3]}-{uuid6}`, e.g., `MED-A3F9B2`)
- The `internal_barcode` is now the **primary source of truth** for:
  - Vendor traceability (prefix encodes vendor)
  - Stock counting (row count = box count)
  - Sale tracking (barcode carried into `sold_items`)
  - Label printing (physical sticker matches DB row)
  - Receiving log linkage (barcode stored in `receiving_log`)

### Why This Matters
| Concern | Bulk Model | Serialized Model |
|---|---|---|
| "How many Aspirin do we have?" | `SELECT SUM(quantity)` | `SELECT COUNT(*) WHERE name='Aspirin' AND status='In Stock'` |
| "Which vendor supplied this box?" | Lookup batch metadata | Read `internal_barcode` prefix or `vendor_name` column |
| "Sell one box" | `UPDATE products SET quantity = quantity - 1` | `DELETE FROM products WHERE id=X; INSERT INTO sold_items...` |
| "Print a label for this box" | Generic batch label | Unique barcode per box — physical sticker is unique |
| "Receive 50 boxes" | `INSERT INTO products (quantity=50)` | Loop: `INSERT INTO products` × 50, each with unique `internal_barcode` |

---

## 2. Database Schema Blueprint

### `products` — Serialized Inventory (1 row = 1 box)

```sql
CREATE TABLE products (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT NOT NULL,          -- Drug name (e.g., "Aspirin 500mg")
    price                   REAL NOT NULL,          -- Price per box
    manufacturer_barcode    TEXT NOT NULL,          -- Shared across all boxes of same drug
    internal_unique_barcode TEXT NOT NULL UNIQUE,   -- UNIQUE per box (VND-XXXXXX)
    status                  TEXT DEFAULT 'In Stock',-- 'In Stock' or 'Sold'
    expiry_date             TEXT DEFAULT '',         -- YYYY-MM-DD
    manufacture_date        TEXT DEFAULT '',         -- YYYY-MM-DD
    vendor_name             TEXT DEFAULT 'N/A'      -- Vendor who supplied this box
);
```

**Key relationships:**
- `name` groups boxes of the same drug (used by `GROUP BY name` for UI display)
- `internal_unique_barcode` is the **surrogate key** for the physical box
- `vendor_name` is denormalized per-box for fast vendor queries (no JOIN needed)
- `status` controls visibility: `'In Stock'` = in inventory, `'Sold'` = archived

### `sold_items` — Sales Archive (1 row = 1 sold box)

```sql
CREATE TABLE sold_items (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name            TEXT NOT NULL,        -- Copied from products.name
    price                REAL NOT NULL,        -- Copied from products.price
    manufacturer_barcode TEXT NOT NULL,        -- Copied from products.manufacturer_barcode
    internal_barcode     TEXT NOT NULL,        -- Copied from products.internal_unique_barcode
    timestamp_of_sale    TEXT NOT NULL,        -- 'YYYY-MM-DD HH:MM:SS'
    vendor_name          TEXT DEFAULT 'N/A'    -- Captured at sale time for traceability
);
```

**Key relationships:**
- `internal_barcode` links back to the original `products.internal_unique_barcode`
- `vendor_name` is **snapshot-captured** at sale time (survives if product is refunded)
- `timestamp_of_sale` enables daily/period sales reporting

### `receiving_log` — Vendor Shipment Ledger

```sql
CREATE TABLE receiving_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_name    TEXT NOT NULL,    -- Who shipped
    product_name   TEXT NOT NULL,    -- Drug name
    date_received  TEXT NOT NULL,    -- YYYY-MM-DD
    quantity       INTEGER NOT NULL, -- How many boxes in this shipment
    total_cost     REAL NOT NULL,    -- Total cost for the shipment
    barcode        TEXT DEFAULT ''   -- Links to products.internal_unique_barcode
);
```

**Key relationships:**
- `barcode` stores the `internal_unique_barcode` for permanent ID linking
- `vendor_name` + `total_cost` enables vendor payables calculation
- `barcode` allows `update_product_full()` to cascade vendor/name/price changes reliably

### `templates` — Reusable Product Templates

```sql
CREATE TABLE templates (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    price REAL NOT NULL
);
```

### `receipts` — Checkout Transaction Log

```sql
CREATE TABLE receipts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,       -- 'YYYY-MM-DD HH:MM:SS'
    total_amount   REAL NOT NULL,       -- subtotal + tax (flat tax from config.json tax_rate)
    payment_method TEXT NOT NULL DEFAULT 'Cash'  -- 'Cash', 'Card', or 'Transfer'
    patient_id     INTEGER DEFAULT NULL  -- FK → patients.id (optional)
    sale_type      TEXT DEFAULT 'OTC',   -- 'OTC', 'Rx OTC', 'Delivery', 'Loyalty', 'Gifts'
    insurance_copay REAL DEFAULT 0.0,    -- Patient-paid copay amount (0.0 if no insurance)
    insurance_amount REAL DEFAULT 0.0   -- Amount covered by insurance (0.0 if no insurance)
);
```

### `receipt_items` — Line Items Per Receipt

```sql
CREATE TABLE receipt_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id    INTEGER NOT NULL,     -- FK → receipts.id
    product_name  TEXT NOT NULL,        -- Drug name at time of sale
    quantity      INTEGER NOT NULL,     -- Number of units sold
    price_at_time REAL NOT NULL,        -- Price per unit at time of sale
    internal_barcode TEXT DEFAULT '',   -- CSV of internal_unique_barcode values for this line
    vendor TEXT DEFAULT '',            -- Vendor snapshot at time of sale
    expiry_date TEXT DEFAULT '',       -- Expiry date snapshot at time of sale
    FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);
```

### How Generic Products Link to Serialized Boxes

```
"Aspirin 500mg" (generic drug name)
  ├── Box 1: MED-A3F9B2  (vendor: MedSupply,  expiry: 2027-01-15)
  ├── Box 2: MED-C7D2E1  (vendor: MedSupply,  expiry: 2027-01-20)
  ├── Box 3: DRU-8F3A1B  (vendor: DrugDirect, expiry: 2026-11-30)
  └── Box 4: DRU-2E9C4D  (vendor: DrugDirect, expiry: 2026-12-05)

UI displays: "Aspirin 500mg" × 4 boxes (grouped by name)
DB has: 4 separate rows in products table, each with unique internal_unique_barcode
```

---

## 3. Component Impact Analysis

### 3A. Add Product Tab (`ui.py:setup_add_tab()`)

**Current behavior:**
- User fills: name, price, mfg barcode, expiry, mfg date, vendor
- `save_product()` calls `barcode_logic.generate_internal_barcode(vendor_name)` → generates unique `{VND}-{uuid6}`
- `database.add_product()` inserts **one row** with the generated `internal_unique_barcode`
- **M36:** `database.log_shipment()` is called immediately after, recording a `receiving_log` entry (qty=1, cost=price, barcode linked)
- Opens `LabelDesignerPopup` with the new barcode for label printing

**Serialized impact:**
- ✅ Already correct: each "Save" creates exactly one serialized box
- ✅ `generate_internal_barcode(vendor_name)` produces `MED-A3F9B2` format
- ✅ `log_shipment()` ensures Shipment History reflects Add Product actions

### 3B. Receive Inventory Tab (`ui.py:setup_receive_tab()` + `database.py`)

**Architecture: Queue-Based State Management**

The Receive Inventory tab operates as a **Purchase Order & Receiving Dashboard** with 3 zones:

- **Zone A (Left — Direct Add Panel):** Canonical `tk.Canvas + CTkFrame` scrollable panel (replaces `CTkScrollableFrame` — M34 fix). Inputs: Vendor, Product (filtered by vendor via `_on_vendor_change()`), Date, Qty, Cost + "Add to Queue" button. Auto-fill section: Mfg Date, Expiry Date, **Unit Price**, **Mfg Barcode** — populated from vendor-specific template via `_on_product_change()`. Does NOT hit the database.
- **Zone B (Top Right — Pending PO Treeview):** Grouped Treeview. Parent = Vendor (showing total qty). Child = individual product lines (Product, Qty, Unit Price, Line Total, Mfg Date, Expiry, Barcode).
- **Zone C (Bottom Right — Reconciliation & Commit):** Invoice Total entry + "Remove Selected" + "Commit Shipment" button. Calls `database.receive_inventory_atomically()` per vendor, then syncs all tabs.
- **Zone D (Bottom — Shipment History):** Vendor-grouped hierarchical treeview. Parent rows = vendor names with total unit count. Child rows = individual shipment entries (Product, Date, Qty, Total Cost, Barcode). Data source: `receiving_log` table via `get_all_receiving_log()`. Cost column shows per-box cost matching Inventory "Price" column (M39/M40).

**In-memory state:** `self.receiving_session` dictionary keyed by vendor name:
```python
{
  "MedSupply": {
    "total_quantity": 150,
    "vendor_asking_price": 0.00,
    "items": [
      {"name": "Aspirin 500mg", "qty": 50, "price": 5.99, "cost": 250.00,
       "mfg_barcode": "123", "internal_barcode": "", "mfg_date": "...", "exp_date": "...",
       "date_received": "2026-07-15"}
    ]
  }
}
```

**Key methods:**
- `_add_to_queue()` — Validates inputs, appends to `receiving_session`, refreshes PO treeview, clears Zone A inputs
- `_refresh_po_treeview()` — Clears and rebuilds `tree_po` from `receiving_session`
- `_remove_selected_from_queue()` — Removes selected vendor/item from queue and refreshes
- `_commit_shipment()` — Iterates `receiving_session`, calls `receive_inventory_atomically()` per vendor, clears queue, refreshes Inventory + Receiving tabs
- `load_receiving_log()` — Delegates to `_refresh_po_treeview()`

### 3C. Inventory Tab (`ui.py:setup_inventory_tab()`)

**Current behavior:**
- `load_inventory()` calls `get_grouped_products()` → `GROUP BY name` with `COUNT(*)` and `MIN/MAX(price)`
- Parent rows show: drug name, qty count, price range
- Double-click expands to child rows via `get_batches_by_name()` — shows individual boxes
- Child rows display: expiry, mfg date, mfg barcode, internal barcode, price, vendor

**Serialized impact:**
- ✅ `get_grouped_products()` already uses `COUNT(*)` — correct for serialized model
- ✅ `get_batches_by_name()` already returns individual rows — correct for serialized model
- ✅ Treeview parent/child pattern naturally fits: group = drug name, children = individual boxes
- ✅ Expiry alerts (`get_expiring_batches()`) counts rows within date thresholds — correct
- ✅ Search works on both barcode types — correct

**No changes needed** — the grouped UI already works correctly with serialized rows.

### 3D. Sales / Point of Sale (`ui.py:sell_product()` + `database.py:mark_item_as_sold()`)

**Current behavior:**
- User selects a specific batch (child row in treeview)
- `sell_product()` reads `values[3]` (mfg barcode) from the selected row
- Calls `database.mark_item_as_sold(barcode)` which:
  1. Finds the product by `manufacturer_barcode OR internal_unique_barcode`
  2. Copies all fields to `sold_items`
  3. **Deletes** the row from `products`

**Serialized impact:**
- ✅ Already correct: `mark_item_as_sold()` deletes the specific row (1 box)
- ✅ `sold_items` captures `vendor_name` at sale time for traceability
- ✅ `reverse_sale()` restores the row to `products` with original `internal_unique_barcode`
- ✅ Sales report shows individual sold items with unique barcodes

**No changes needed** — the sell flow already operates on individual serialized boxes.

### 3E. Label Printing (`ui.py:open_label_for_selected()` + `barcode_logic.py`)

**Current behavior:**
- User selects a batch (child row) in inventory treeview
- `open_label_for_selected()` reads `values[4]` (internal barcode) from the row
- Opens `LabelDesignerPopup` with the unique barcode
- Label renders the **unique internal barcode** as a Code128 barcode on the sticker

**Serialized impact:**
- ✅ Already correct: each box gets its own unique barcode on the physical sticker
- ✅ `LabelDesignerPopup` uses `self.internal_barcode` for preview and PNG export
- ✅ `export_to_png()` renders the unique barcode at 300 DPI
- ✅ `print_label()` sends the unique barcode to the printer

**No changes needed** — each physical box already gets a unique sticker.

### 3F. Edit Batch Dialog (`ui.py:EditBatchDialog`)

**Current behavior:**
- Shows all fields for a specific box: name, price, mfg barcode, internal barcode (disabled), expiry, mfg date, vendor, status
- `_save()` calls `update_product_full()` which cascades vendor/name/price changes to `receiving_log` via barcode
- **M36:** If vendor changed from N/A → valid, calls `database.log_shipment()` to record a new `receiving_log` entry before launching `QuickReceiveModal`

**Serialized impact:**
- ✅ Internal barcode is disabled with "(Auto-Generated)" hint — correct
- ✅ `update_product_full()` cascades vendor/name/price via `WHERE barcode = ?` — correct
- ✅ `log_shipment()` ensures orphaned batches get proper Shipment History entries on vendor assignment
- ✅ `QuickReceiveModal` integration — correct

### 3G. Sales Report Tab (`ui.py:setup_report_tab()`)

**Current behavior:**
- Shows all sold items with columns: ID, Name, Price, Mfg Barcode, Internal Barcode, Timestamp, Vendor
- Revenue calculated as `SUM(price)` of all sold items
- Today's sales total via `get_today_sales_total()`
- Custom date query via `get_sales_for_date()`

**Serialized impact:**
- ✅ Already correct: each sold box is a separate row in `sold_items`
- ✅ Revenue calculation sums individual box prices — correct
- ✅ Date filtering works on `timestamp_of_sale` — correct

**No changes needed** — the sales report already handles serialized items.

---

## 4. Step-by-Step Refactoring Plan

### Phase 1: Receiving Flow (CRITICAL — Currently Broken)

| # | Task | File | Risk | Notes |
|---|---|---|---|---|
| 1 | Modify `log_shipment_handler()` to accept price per box | `ui.py:663` | Low | Need to add price entry or derive from product |
| 2 | Add loop in `log_shipment_handler()` to call `add_product()` N times | `ui.py:663` | **High** | Core serialized receiving logic |
| 3 | Generate unique `internal_barcode` per iteration | `ui.py:213` | Low | `generate_internal_barcode(vendor_name)` already works |
| 4 | Update `QuickReceiveModal._submit()` with same loop logic | `ui.py:1258` | Medium | Mirror the loop for modal path |
| 5 | Add price field to receiving form (or inherit from product) | `ui.py:575` | Low | Need price per box for `add_product()` |
| 6 | Test: Receive 5 boxes → verify 5 rows in products table | Manual | — | Validation step |

### Phase 2: Edge Cases & Data Integrity

| # | Task | File | Risk | Notes |
|---|---|---|---|---|
| 7 | Handle existing bulk data migration (if any) | `database.py` | Medium | Old rows with quantity > 1 need splitting |
| 8 | Verify `get_products_with_vendors()` returns correct barcode for combobox | `database.py:164` | Low | Used by receive tab product selection |
| 9 | Add transaction safety to receiving loop (rollback on failure) | `database.py` | Medium | Prevent partial receives |
| 10 | Verify `receiving_log.barcode` stores the last generated barcode | `database.py:405` | Low | Already implemented |

### Phase 3: UI Polish

| # | Task | File | Risk | Notes |
|---|---|---|---|---|
| 11 | Add "Price per Box" field to receive form | `ui.py:575` | Low | Required for `add_product()` |
| 12 | Show "Received N boxes" confirmation with barcode list | `ui.py:663` | Low | UX improvement |
| 13 | Add batch number display in inventory child rows | `ui.py:381` | Low | Show vendor prefix in treeview |

### Phase 4: Verification Checklist

| # | Test Case | Expected Result | Status |
|---|---|---|---|
| A | Receive 3 boxes of Aspirin from MedSupply | 3 rows in products, each with MED-XXXXXX barcode | ⬜ |
| B | Sell 1 box of Aspirin | 1 row deleted from products, 1 row in sold_items | ⬜ |
| C | Print label for received box | Sticker shows unique MED-XXXXXX barcode | ⬜ |
| D | Edit batch vendor from N/A → MedSupply | QuickReceiveModal appears, receiving_log updated | ⬜ |
| E | Search by internal barcode | Finds exact box in inventory | ⬜ |
| F | Refund sold item | Row restored to products with original barcode | ⬜ |
| G | Receive 0 boxes | Validation error, no rows created | ⬜ |
| H | Receive boxes with duplicate vendor | All barcodes unique (uuid6 guarantee) | ⬜ |

---

## 5. Source File Reference

### Root Structure

```
my progam pharmacy/
├── main_app.py             # Unified suite entry + open_label_engine() subprocess bridge
├── main.py                 # Pharmacy app entrypoint (PharmacyApp window)
├── ui.py                   # Thin wrapper (303 lines): imports + class def + attachments
├── ui_helpers.py           # _extract_first_var, _extract_all_vars regex utilities
├── ui_modals.py            # LabelDesignerPopup, QuickReceiveModal, BulkAddModal, BulkLabelPrintDialog, EditBatchDialog
├── ui_add_tab.py           # Add Product tab setup + save + bulk
├── ui_inventory_tab.py     # Inventory tab: grouped treeview, search, sort, sell, edit, label print dialog
├── ui_expiring_tab.py      # Expiring Soon tab: alerts + vendor summary
├── ui_dashboard_tab.py     # Dashboard tab: KPI cards + alerts + expiry summary
├── ui_report_tab.py        # Sales Report tab: sales treeview + analytics + CSV export
├── ui_receive_tab.py       # Receive Inventory tab: queue-based PO dashboard + shipment history
├── receipt_engine.py       # Receipt generation: thermal-format .txt with pharmacy info + auto-open
├── path_utils.py           # PyInstaller-safe path resolution + runtime directory initialization
├── build_exe.py            # PyInstaller build automation (--noconsole / --debug / --icon)
├── backend/                # Flask licensing server (backend/app.py: webhook + validate + admin manage endpoint; db.py: SQLite persistence; admin.py: CLI; tests)

├── server_app.py           # Flask license server for PythonAnywhere (/api/validate, /api/activate, /api/create)
├── deploy_to_server.py     # Deployment script: upload server_app.py + reload via PythonAnywhere REST API
├── ui_checkout_tab.py      # Checkout tab: POS cart with qty management + receipts + payment + patient linkage
├── ui_templates_tab.py     # Templates tab: CRUD for product templates
├── ui_patients_tab.py      # Patients CRM tab: search, Treeview, dynamic custom field editor
├── ui_settings_tab.py      # Settings tab: config + RBAC + backup
├── excel_handler.py        # Excel import/export engine using openpyxl (threaded)
├── database.py             # SQLite CRUD (delegates to db.py ORM) + analytics + patient CRM
├── db.py                  # SQLAlchemy ORM models + session manager + text() query layer
├── ocr_engine.py          # OCR extraction engine: backends, preprocessing, confidence scoring
├── ocr_cascade.py         # 4-tier confidence cascade: Tesseract→Tesseract Enhanced→EasyOCR→Pillow
├── barcode_logic.py        # Barcode/label generation + config loading + Python finder
├── config.json             # Runtime settings (pharmacy name, font, DB path)
├── label_template.json     # Persistent label template (optional, auto-created by engine)
├── main.spec               # PyInstaller build spec
├── pharmacy.db             # SQLite database (runtime, auto-created)
├── labels/                 # Generated label PNG images
├── build/                  # PyInstaller build artifacts
├── dist/                   # PyInstaller output (main.exe)
├── label_engine/           # Dynamic Label Design Engine (module)
│   ├── __init__.py         #   Module marker
│   ├── migrate_data.py     #   M33: Legacy barcode normalization script
│   ├── main.py             #   App entry + argparse + product context + File menu
│   ├── canvas_core.py      #   Element hierarchy + unified draw_elements() + drag/resize
│   ├── properties_panel.py #   Property editor sidebar (text/shape/barcode/QR fields)
│   ├── export.py           #   JSON save/load + PNG export (300 DPI) + print + id-based paths
│   └── data/labels/        #   Persisted label designs (auto-created per product ID)
├── venv/                   # Python 3.12.7 virtual environment
├── requirements.txt        # Pinned project dependencies
├── README.md               # Project overview + getting started
├── LICENSE                 # MIT License
├── AGENTS.md               # Agent execution protocols
├── PROJECT_MAP.md          # This file
├── Procfile                # WSGI entry: `web: gunicorn backend.app:app`
└── .gitignore
```

### Milestones

| # | Milestone | Status | Verified |
|---|---|---|---|
| M1 | Scaffold + Canvas | Complete | 2026-07-12 |
| M2 | Text Elements + Properties Panel | Complete | 2026-07-12 |
| M3 | Barcode (Code128) + QR Elements + Drag/Resize | Complete | 2026-07-12 |
| M4 | Advanced Shapes (rectangle, ellipse, rounded-rectangle) | Complete | 2026-07-12 |
| M5 | Label Save/Load (JSON Serialization) | Complete | 2026-07-12 |
| M6 | PNG Export (300 DPI) + Print Support | Complete | 2026-07-12 |
| M8 | Integration Bridge (Context-Aware Label Engine) | Complete | 2026-07-12 |
| M9 | Schema Migration + Date Columns | Complete | 2026-07-12 |
| M10 | Grouped Database Queries | Complete | 2026-07-12 |
| M11 | Grouped Inventory UI (Treeview parent/child) | Complete | 2026-07-12 |
| M12 | Sorting Toggle + Search Integration | Complete | 2026-07-12 |
| M13 | Sell + Print Integration (batch-level) | Complete | 2026-07-12 |
| M14 | Date Validation + Expiry Dashboard | Complete | 2026-07-12 |
| M15 | RBAC + Batch Edit | Complete | 2026-07-12 |
| M16 | Label Engine V2 Bridge + Dates | Complete | 2026-07-12 |
| M17 | Template System + Edit->Label Integration | Complete | 2026-07-12 |
| M18 | Full-Field EditBatchDialog + Database Expansion | Complete | 2026-07-13 |
| M19 | Label Designer Layout Re-Proportioning | Stable/Verified | 2026-07-13 |
| M20 | Typography, Spacing & Style Stability | Stable/Verified | 2026-07-13 |
| M21 | Subprocess Hardening + Pack Layout + Canvas Scrollbars | Stable/Verified | 2026-07-13 |
| M22 | UI Remediation: ttk.PanedWindow + pack_propagate(False) + Layout Geometry Auditor | Stable/Verified | 2026-07-13 |
| M23 | Text Anchor Fix: Left-Aligned Canvas Text (anchor="w") | Stable/Verified | 2026-07-13 |
| M24 | LabelDesignerPopup: grid minsize=300 on controls column | Stable/Verified | 2026-07-13 |
| M25 | Dynamic Text Scaling: Fit-to-Width font reduction + word-wrap fallback | Stable/Verified | 2026-07-13 |
| M26 | Interactive Scrollable Canvas Viewport: Zoom controls + mouse-wheel panning | Stable/Verified | 2026-07-13 |
| M27 | Persistent Label Template System: Save/load templates + dynamic popup fields | Stable/Verified | 2026-07-14 |
| M28 | Vendor Traceability: vendor_name column + cascade + receiving_log barcode | Complete | 2026-07-15 |
| M29 | Quick Receive Modal: Vendor N/A→valid triggers qty/cost dialog | Complete | 2026-07-15 |
| M30 | Serialized Barcode Generation: `{VND[:3]}-{uuid6}` format | Complete | 2026-07-15 |
| M31 | Serialized Receiving Loop: `log_shipment_handler()` + `QuickReceiveModal` create N rows per shipment | Complete | 2026-07-15 |
| M32 | Atomic Receiving: `receive_inventory_atomically()` wraps loop + ledger in single transaction with rollback | Complete | 2026-07-15 |
| M33 | Legacy Barcode Normalization: `migrate_data.py` renames old-format barcodes to `{VND[:3]}-{UUID6}` with `receiving_log` cascade | Complete | 2026-07-15 |
| M34 | Interaction Lock Fix: Replaced `CTkScrollableFrame` in Receive tab with canonical `tk.Canvas + CTkFrame` scrollable panel — eliminates `bind_all` event-chain and `create_window` focus anomaly | Complete | 2026-07-15 |
| M35 | Talking Tabs (Observer Pattern): Added `_notify_inventory_updated()` event-bus method; `_commit_shipment()` now emits this signal to sync Inventory, Sales Report, Add Product, and Receive tabs simultaneously | Complete | 2026-07-15 |
| M36 | Phase 13: Serialized POS Cart System — multi-item serialized checkout from `products` → `sold_items` via `database.checkout_cart_atomically()`, with barcode-scanned cart staging, flat-tax computation, and balance panel (Subtotal/Tax/Total + Amount Tendered + Change Due) | Complete | 2026-08-04 |
| M36.5 | Phase 13.5: Dynamic Settings Tab | Complete | 2026-08-04 |
| M65 | Phase 16 M65: Enterprise POS Retail — Enhanced `ui_pos_retail.py` with TaxCalculator engine, WAL-mode SQLite (`SqliteWALConnection`), CartObserver (Observer pattern), AsyncUI threading, 3-column layout with right-side action panel (Delivery/Gifts/OTC), payment method + amount tendered + change due, `_debug_layout_geometry()` layout assertions, F12 binding, comprehensive type hints, and time-complexity docstrings. Fixes D1 bug (`internal_barcodes` list vs `internal_barcode` singular). 17 new i18n keys added to all 6 locale files. 25/25 Phase 16 tests pass. | Complete | 2026-08-05 |
| Phase 16 | Enterprise Suite Integration — Top menu bar, icon toolbar, status dashboard, task panel, Quick-SIG builder, NDC dictionary, enterprise POS retail with F12, clinical workflow + 4-step prescription wizard, bulk import staging. All new modules monkey-patched via `main_app.py:_wire_rx_extensions()` without modifying `ui.py` or `ui_navigation.py`. +25 Phase 16 unit tests + 12 edge-case tests (`test_enterprise_edge_cases.py`). 148/148 existing tests pass. 105/105 exhaustive checks pass. Locked files (`rx_db.py`, `rx_config.py`, `rx_strategies.py`) unmodified. | Verified | 2026-08-05 |
| M66 | Lemon Squeezy Webhook Flask Backend (`backend/app.py` + `backend/test_webhook_lemon_squeezy.py`) — HMAC-SHA256 signature verification, `order_created` generates + persists `PHARM-XXXX-XXXX-XXXX` key to SQLite. | Complete | 2026-08-06 |
| M90 | SQLite License Persistence + Validate Endpoint — `backend/db.py` (SQLite `licenses` table with `created_at` column; `init_db`/`insert_license`/`get_license`/`bind_hardware_id`/`clear_hardware_id`/`update_license_status`/`clear_licenses`/`get_all_licenses`; in-memory `:memory:` test isolation), `POST /api/validate` endpoint (404/403/400/200 binding logic), `Procfile` for gunicorn deployment, `gunicorn` in requirements.txt, `*.sqlite` in `.gitignore`. | Complete | 2026-08-06 |
| M91 | Admin Management CLI & API — `backend/admin.py` (argparse CLI: `list`/`revoke`/`reset`/`generate` with ASCII table output), `POST /api/admin/manage` endpoint in `backend/app.py` (X-Admin-Secret auth, revoke/reset/list actions, 200/401/400/404/500 status codes), `backend/test_admin.py` (29 unit tests covering CLI functions + API auth/revoke/reset/list edge cases). 43/43 total tests pass (14 webhook + 29 admin). | Complete | 2026-08-06 |
| M93 | **Pharmacy UI Refactor — Insurance Copay, Sale Type, Dashboard Analytics, Checkout Fix:** (1) **DB schema:** Added `sale_type`, `insurance_copay`, `insurance_amount` columns to `receipts` table in `database.py:init_db()` and `db.py:init_db()` via idempotent ALTER TABLE migration; updated ORM `Receipt` model. (2) **T2:** `ui_pos_retail.py:_on_insurance_apply()` — implements region-aware copay calculation via `rx_strategies.strategy_factory(region)`; adds insurance state variables, balance summary labels (Patient Cost + Insurance Cost), passes insurance data through `_do_checkout()` → `checkout_cart_atomically()`. (3) **T3:** `ui_pos_panels.py:InsurancePanel` — enables "Apply to Sale" button, loads insurance data from `insurance_table` (BIN/PCN/plan/carrier), calls `on_apply` callback with structured info dict. (4) **T4:** `ui_pos_retail.py` — added `POS_SALE_TYPES` constant, `_SALE_TYPE_COLORS` mapping, sale type badge updates, `Gifts` (was "Gift"), passes `sale_type` through checkout. (5) **T5:** `ui_status_dashboard.py` — 4 new metric cards (daily_sales, scripts_filled, insurance_claims, total_patients) with SQL queries + currency formatting. (6) **T6:** `ui_checkout_tab.py` — "Insurance" payment method no longer crashes (calculates copay via strategy, falls back to 'Transfer'); added `_checkout_debug_layout()`. (7) **T7:** `ui_patients_tab.py` — i18n keys for all hardcoded labels, `apply_treeview_style`, added `_patients_debug_layout()`. (8) **db.py bug fix:** Stale `fetchall()` on PRAGMA results caused false `RuntimeError` on double `init_db()` call — re-execute PRAGMA before fetch. Added `engine.dispose()` after `create_all`. (9) **3 new test files (25 tests)** covering insurance copay calculation, sale type persistence, dashboard metrics. 189/190 tests pass (1 pre-existing failure in fuzzy matching). | Verified | 2026-08-08 |
| M92 | Phase 17: POS UI Overhaul & Modal Wiring — Created `archive/ui_pos_panels.py` with 10 interactive classes (`InsurancePanel`, `NotesPanel`, `CouponPanel`, `ReceiptHistoryPanel`, `CustomerHistoryPanel`, `DiscountDialog`, `ReturnDialog`, `MemoDialog`, `SplitPaymentDialog`, `EODDialog`). Eliminated all 17 placeholder `messagebox.showinfo` stubs from `archive/ui_pos_retail.py`. Wired `_on_side_trigger` and `_on_quick_action` to launch real modals or perform tab navigation. Added `_sale_type_badge` and `_sale_memo` state to `EnterprisePosFrame`. | Complete | 2026-08-06 |
| M93 | **Runtime Bug Fixes — 2026-08-06:** (1) **DB migration**: `patients` table missing `insurance_provider`/`policy_number`/`group_number` columns (queried by `ui_pos_retail.py` patient fetch + `ui_pos_panels.py` InsurancePanel, causing `no such column: insurance_provider`). Added idempotent `PRAGMA table_info` + `ALTER TABLE` migration in `database.py:init_db()`, `db.py:init_db()` (ORM model + SQLite path), `rx_database.py:init_rx_tables()`, and `rx_db.py:init_rx_tables()`. Queries wrapped with `COALESCE(col, '')` for graceful NULL fallback. (2) **TabViewCompat shim**: `TabViewCompat` lacked `_tab_dict` (queried by `InsurancePanel._edit` + POS quick actions for prescription/refill tab navigation). Added `_tab_dict` property delegating to `self.frames`. (3) **AsyncUI shutdown**: `root.after()` dispatch on destroyed root raised `tk.TclError`/`RuntimeError`. Added `winfo_exists()` guard + `except (tk.TclError, RuntimeError)` silent discard. Verified: py_compile clean; 92/92 existing tests pass (phase16 25/25, phase17 28/28, rx_database 17/17, enterprise_edge 12/12). | Verified | 2026-08-06 |
| M3-FL | Frontend Core Libraries (Next.js) — Zustand foundation stores (`cartStore`, `inventoryStore`, `licenseStore`, `uiStore`) + typed per-domain API service layer (`lib/api/{inventory,pos,auth,license,users,settings}.ts`); `hooks/useInventory.ts` refactored to back the store with byte-compatible public API (`app/dashboard/inventory/page.tsx` untouched). `tsc --noEmit` → 0 errors; `next build` → 13/13 pages. | Verified | 2026-08-17 |

---

### Phase 16 Files (New)

| File | Purpose | Lines |
|---|---|---|
| `ndc_dictionary.py` | High-speed SQLite NDC/barcode lookup dictionary (shared in-memory or file-backed) | ~260 |
| `rx_migrations.py` | Additive schema migrations for `inventory_extended` (DEA schedule, wholesale, reorder) | ~100 |
| `quick_sig.py` | Quick-SIG template save/load/delete + `QuickSigBuilder` UI with suggestion palette | ~450 |
| `ui_enterprise_navigation.py` | Top menu bar (`tkinter.Menu`) + icon toolbar (`CTkFrame`, 10 buttons, F12 hint) | ~170 |
| `ui_status_dashboard.py` | `StatusDashboardFrame` with 8 metric cards + 9-task panel | ~270 |
| `bulk_import_staging.py` | `StagingTable` class with auto header mapping + CSV/Excel import | ~270 |
| `ui_bulk_import.py` | `BulkImportFrame`: file-select / 20-row Treeview preview / header-to-field mapping confirmation / `commit_staged_products()` commit + `setup_bulk_import_tab()` | ~235 |
| `ui_pos_retail.py` | `EnterprisePosFrame` — retail POS with TaxCalculator engine, WAL-mode SQLite, CartObserver, quick-action grid, right-side action panel (Delivery/Gifts/OTC), side-panel triggers, F12 payment binding, async checkout | ~700 |
| `ui_clinical_workflow.py` | `ClinicalWorkflowFrame` with 9 tabs + `PrescriptionWizard` (4-step modal) | ~520 |
| `native_accel.py` | Hybrid native acceleration layer: rapidfuzz (fuzzy search) + Rust barcode_gen (batch UUID), each with pure-Python fallback via try/except ImportError | ~400 |
| `test_native_accel.py` | 31 unit tests covering fuzzy search, barcode generation, header matching, backend status, and fallback paths | — |
| `test_enterprise_edge_cases.py` | 12 unit tests covering `import_excel()`, `commit_staged_products()` (add/update/error paths), `barcode_lookup()`, `name_lookup()`, `_normalize_dea()`, and `bulk_load_ndc()` error handling | — |
| `barcode_gen.pyd` | Compiled Rust extension (PyO3) for batch barcode generation (`generate_barcodes`, `generate_batch_barcodes_batch`, `get_info`) | — |

### Phase 16 Files (Modified)

| File | Changes |
|---|---|
| `database.py` | Added `dea_schedule`, `wholesale_price`, `reorder_threshold` columns to `products` table; added `quick_sig_templates` table; updated `add_product()` and `update_product_full()` signatures; **`receive_inventory_atomically()` now auto-pre-generates barcodes via `native_accel.generate_batch_barcodes()` when `pre_generated_barcodes=None`** |
| `db.py` | Added `dea_schedule`, `wholesale_price`, `reorder_threshold` to `Product` ORM model; added `QuickSigTemplate` ORM model; added migration in `init_db()`; **`receive_inventory_atomically()` now auto-pre-generates barcodes via `native_accel`** |
| `ui_navigation.py` | Extended `_NAV_ICONS` with 9 new tab icons |
| `main_app.py` | Extended `_wire_rx_extensions()` to wire 5 new tabs + enterprise navigation + F12 binding + rx_migrations + ndc_dictionary init + **bulk import tab** (`setup_bulk_import_tab` call in `_patched_init`, i18n import, and `bulk_import_title` refresh branch in `_patched_on_tab_change`) |
| `ui_receive_tab.py` | `_print_bulk_labels()` now uses `native_accel.generate_batch_barcodes()` for batch generation; stores barcodes in `item["pre_barcodes"]` for `_commit_shipment()` reuse |
| `ui_clinical_workflow.py` | `_search_patients()` and `_refresh_patient_list()` now use `native_accel.fuzzy_search()` for typo-tolerant patient search; `_search_drugs_fallback()` uses fuzzy ranking on `name_lookup()` results when `ndc_lookup()` fails |
| `quick_sig.py` | `get_sig_suggestions()` now uses `native_accel.fuzzy_search()` with `partial_ratio` scorer to rank SQL LIKE results, handling typos in SIG template names |
| `bulk_import_staging.py` | `StagingTable.auto_map_csv_headers()` now uses `native_accel.fuzzy_match_headers()` for fuzzy header matching; retains existing 8-pass algorithm as fallback |
| `excel_handler.py` | `execute_import._worker()` restructured to pre-generate all barcodes in a single batch (grouped by vendor) via `native_accel.generate_batch_barcodes()` before the database insert loop |
| `build_exe.py` | Added `native_accel` to hidden imports; added `barcode_gen.pyd` to `.pyd` binary bundling |
| `requirements.txt` | Added `rapidfuzz>=3.10.0` |
| `.gitignore` | Added `archive/barcode_gen/target/` for Rust build artifacts |
| `locales/en.json` | +89 new i18n keys |
| `locales/{de,es,fr,pt,ar}.json` | +89 new i18n keys (English fallback) |
| `config.json` | Added `ndc_dictionary_path` field

---

## 6. Pharmacy App Source Files

### `main.py` — Pharmacy Entrypoint (22 lines)
- Sets customtkinter appearance (Dark mode, blue theme)
- Calls `database.init_db()` to create tables
- Calls `barcode_logic.init_labels_dir()` to ensure `labels/` exists
- Launches `PharmacyApp` main window

### `main_app.py` — Unified Suite Entry + Subprocess Bridge (39 lines)
- Single entry point for the entire suite
- Delegates to `main.main()` for the pharmacy app
- `open_label_engine(product_id, barcode_value, product_name, product_price, expiry, manufacture, show_name, show_price, show_expiry, show_barcode_text)`: launches `label_engine/main.py` as subprocess with all context and visibility flags. Uses `subprocess.Popen` for clean detachment.

### `ui_helpers.py` — Regex Utilities (6 lines)
- `_extract_first_var(text)` — Returns first `{{VAR}}` name from template text, or None
- `_extract_all_vars(text)` — Returns list of all `{{VAR}}` names from template text

### `ui_modals.py` — Popup Dialog Classes (692 lines)

| Class | Purpose |
|---|---|
| `LabelDesignerPopup(ctk.CTkToplevel)` | Label preview/print popup — loads template if available, dynamically generates entry fields from text elements (resolves `{{VAR}}` defaults for mixed text like `"Exp: {{EXPIRY}}"`), renders via draw_elements. Includes Mfg Date and Exp Date fields in both default and template modes. |
| `QuickReceiveModal(ctk.CTkToplevel)` | Appears when vendor changes from N/A to a valid vendor in EditBatchDialog. Qty entry (focused) + Cost entry. Submit calls `receive_inventory_atomically()` and refreshes inventory + receiving log via non-blocking `.after()`. |
| `BulkAddModal(ctk.CTkToplevel)` | Opened from Add Product tab "Quick Receive (Bulk)" button. Dual-path workflow: "Submit & Save Directly" writes to DB immediately (M44); "Save to Queue" stages items in `receiving_session` for Pending PO commit. "Print All Tags" checkbox triggers batch label printing via template. Shows read-only product info + editable Qty + Total Wholesale Cost. **M45:** Stores `pre_barcodes` list in queue items so `_commit_shipment()` uses stored barcodes (printed labels match committed DB barcodes). |
| `EditBatchDialog(ctk.CTkToplevel)` | Full-field batch editor: name, price, mfg barcode, internal barcode (disabled, "Auto-Generated" hint), expiry, mfg date, vendor, status. On vendor N/A→valid change, launches QuickReceiveModal instead of success messagebox. |
| `BulkLabelPrintDialog(ctk.CTkToplevel)` | Batch label printing dialog with barcode range selection, printer selection, and preview. |

### `ui_add_tab.py` — Add Product Tab (164 lines)
- `setup_add_tab(self)` — Form: template dropdown, name, price, mfg barcode, expiry, mfg date, vendor → saves + opens label designer
- `refresh_add_tab_templates(self)` — Refreshes template dropdown
- `save_product(self)` — Validates inputs, generates internal barcode, inserts product, opens label designer
- `_open_bulk_add_modal(self)` — Opens BulkAddModal for multi-unit serialization

### `ui_inventory_tab.py` — Inventory Tab (232 lines)
- `setup_inventory_tab(self)` — Expiry alert bar, grouped Treeview, sort toggle, search
- `load_inventory(self)` — Refreshes grouped inventory display
- `perform_search(self)` — LIKE search on name, barcodes
- `_send_to_checkout(self)` — Sends selected item to checkout cart
- `_edit_batch(self)` — Opens EditBatchDialog
- `open_label_for_selected(self)` — Opens LabelDesignerPopup with unique barcode

### `ui_expiring_tab.py` — Expiring Soon Tab (249 lines)
- `setup_expiring_tab(self)` — Expiring items list with date thresholds
- `load_expiring_items(self)` — Refreshes expiring items display
- `_on_vendor_summary_click(self)` — Vendor summary drill-down

### `ui_dashboard_tab.py` — Dashboard Tab (123 lines)
- `setup_dashboard_tab(self)` — 8 KPI cards in responsive grid: total products, in-stock count, low stock, expiring soon, today's revenue, total revenue, unique vendors. Low-stock alerts panel. Expiry summary panel.
- `load_dashboard(self)` — Refreshes all dashboard KPI cards and alerts

### `ui_report_tab.py` — Sales Report + Analytics Tab (530 lines)
- `setup_report_tab(self)` — Segmented "Sales"/"Analytics" switcher. Sales view: date-based treeview + refund. Analytics view: date-range presets + ranked products + CSV export.
- `load_sales_report(self)` — Refreshes grouped sales display
- `_search_for_refund(self)` — Barcode search for refund
- `calculate_custom_date_sales(self)` — Custom date query
- `refund_item(self)` — Restores item to inventory
- `setup_analytics_panel(self, parent)` — Date-range controls + KPI cards + ranked products treeview
- `load_analytics(self)` — Fetches analytics for selected date range
- `_export_analytics_csv(self)` — Exports analytics to CSV via stdlib csv module

### `ui.py` — Pharmacy GUI Layer (303 lines — thin wrapper)

**Module-level helpers:**
- `_extract_first_var(text)` — Returns first `{{VAR}}` name from template text, or None
- `_extract_all_vars(text)` — Returns list of all `{{VAR}}` names from template text

**Classes:**

| Class | Purpose |
|---|---|
| `PharmacyApp(ctk.CTk)` | Main window with 9 tabs |

**Tab breakdown:**

| Tab | Method | Purpose |
|---|---|---|
| Dashboard | `setup_dashboard_tab()` | KPI cards + low-stock alerts + expiry summary (via `ui_dashboard_tab.py`) |
| Add Product | `setup_add_tab()` | Form: template dropdown, name, price, mfg barcode, expiry, vendor → saves + opens label designer. Bulk button opens BulkAddModal. (via `ui_add_tab.py`) |
| Inventory | `setup_inventory_tab()` | Expiry alert bar, grouped Treeview, double-click expand, sort toggle, search, sell, edit batch, label print dialog, import/export. (via `ui_inventory_tab.py`) |
| Expiring Soon | `setup_expiring_tab()` | Expiring items + vendor summary drill-down. (via `ui_expiring_tab.py`) |
| Sales Report | `setup_report_tab()` | Segmented "Sales"/"Analytics" switcher. Sales view: date-based treeview + refund. Analytics view: date-range presets + ranked products + CSV export. (via `ui_report_tab.py`) |
| Receive Inventory | `setup_receive_tab()` | Queue-based PO dashboard: input form, pending PO treeview, commit + shipment history. (via `ui_receive_tab.py`) |
| Checkout | `setup_checkout_tab()` | POS cart with barcode scan + qty management + payment + receipts + patient linkage. (via `ui_checkout_tab.py`) |
| Templates | `setup_templates_tab()` | CRUD for reusable product templates. (via `ui_templates_tab.py`) |
| Patients | `setup_patients_tab()` | Patient CRM: search, Treeview, add/edit with dynamic custom fields, delete. (via `ui_patients_tab.py`) |
| Settings | `setup_settings_tab()` | Pharmacy name, font size, price toggle, DB path, RBAC, backup. (via `ui_settings_tab.py`) |

### `database.py` — Data Layer (500+ lines, delegation wrapper)
**Delegates to db.py ORM layer via `@_db_fallback` decorator.** Each function tries `_db.<function_name>()` first (SQLAlchemy `text()` with `:param` named parameters); on any failure, falls back to the original raw sqlite3 implementation. Zero regression for all 19 importing modules.

**Tables:** `products`, `templates`, `sold_items`, `receiving_log`, `receipts`, `receipt_items`, `patients`, `patient_fields`

**Products schema:** `id`, `name`, `price`, `manufacturer_barcode`, `internal_unique_barcode` (UNIQUE), `status`, `expiry_date`, `manufacture_date`, `vendor_name`, `dea_schedule`, `wholesale_price`, `reorder_threshold`

**Patients schema (post-2026-08-06 migration):** `id`, `name`, `phone`, `email`, `created_at`, **`insurance_provider`**, **`policy_number`**, **`group_number`** (all nullable TEXT, added via `PRAGMA table_info` + `ALTER TABLE` idempotent migration in `init_db()` / `init_rx_tables()`).  Queries in `ui_pos_retail.py` and `ui_pos_panels.py` use `COALESCE(col, '')` for graceful NULL fallback.

**Sold Items schema:** `id`, `item_name`, `price`, `manufacturer_barcode`, `internal_barcode`, `timestamp_of_sale`, `vendor_name`

**Receiving Log schema:** `id`, `vendor_name`, `product_name`, `date_received`, `quantity`, `total_cost`, `barcode`

**Functions:**

| Function | Purpose |
|---|---|
| `init_db()` | Creates tables if missing, seeds default templates, migrates schema (status, expiry_date, manufacture_date, vendor_name, receiving_log.barcode) |
| `add_product(name, price, mfg_barcode, internal_barcode, expiry, mfg, vendor)` | Inserts **one serialized row** into `products` |
| `get_all_products()` | Returns all rows from `products` (includes dates) |
| `search_products(query)` | LIKE search on name, barcodes (includes dates) |
| `get_grouped_products()` | `GROUP BY name` → `[(name, COUNT(*), MIN(price), MAX(price))]` — serialized box count |
| `get_batches_by_name(name, sort_by)` | Returns all **individual boxes** for a drug, sorted by expiry ASC or mfg DESC |
| `search_grouped_products(query)` | LIKE search → grouped results |
| `update_product_dates(product_id, expiry, mfg)` | Updates expiry_date and manufacture_date for a single box |
| `update_product_full(product_id, name, price, mfg_barcode, int_barcode, expiry, mfg, status, vendor_name)` | Full product field update (all 8 mutable columns) + cascade vendor/name/price to receiving_log via barcode |
| `get_product_by_id(product_id)` | Returns single product row by ID (all columns) |
| `get_expiring_batches()` | Returns dict `{'30': count, '60': count, '90': count}` of boxes expiring within thresholds |
| `get_product_by_barcode(barcode)` | Returns single product by barcode (includes dates) |
| `mark_item_as_sold(barcode)` | **Deletes** product row → **Inserts** into `sold_items` (captures vendor_name at sale time) |
| `reverse_sale(sold_item_id)` | **Deletes** sold item → **Inserts** back to `products` (restores vendor_name) |
| `get_today_sales_total()` | Returns sum of prices for today's sales (timestamp LIKE 'YYYY-MM-DD%') |
| `get_sales_for_date(date_str)` | Returns sum of prices for a specific date (timestamp LIKE 'date%') |
| `log_shipment(vendor, product, date, qty, cost, barcode)` | Inserts a row into `receiving_log` (with barcode for permanent ID linking) |
| `receive_inventory_atomically(vendor, product, date, qty, cost, price, mfg_barcode, expiry, mfg_date, barcode_generator)` | Atomic receiving: loops `qty` times inserting serialized product rows + one `receiving_log` entry, all in a single transaction. Rolls back entirely on any failure. Returns last generated barcode. |
| `get_all_receiving_log(filter_date=None)` | Returns receiving_log rows (7 columns including barcode) ordered by date DESC. Optional `filter_date` parameter filters to a specific date. |
| `get_vendor_total_owed(vendor_name)` | Returns SUM(total_cost) for a specific vendor |
| `get_all_vendors()` | Returns distinct vendor names from receiving_log |
| `get_products_with_vendors()` | Returns name, vendor_name, internal_unique_barcode for In Stock products |
| `get_product_template(name)` | Returns (name, price, mfg_barcode, expiry, mfg_date) from most recent In Stock product with given name — used by receiving loop |
| `backup_database(dest_folder)` | Copies `pharmacy.db` with date suffix |
| `create_receipt(payment_method, items, patient_id)` | Creates receipt + receipt_items, atomically deducts stock from products. Items: `[{product_name, quantity, price_at_time}]`. Rolls back on insufficient stock. **Legacy — superseded by `checkout_cart_atomically`** in Phase 13. |
| `checkout_cart_atomically(payment_method, cart_entries, patient_id, tax_rate, sale_type, insurance_copay, insurance_amount)` | **Phase 13:** Processes entire POS cart in a single SQLite transaction. For each cart entry, migrates every staged `internal_unique_barcode` from `products` → `sold_items` (one row per barcode), creates `receipts` + `receipt_items`, computes flat tax from `tax_rate` param. Rolls back on any missing/in-stock barcode. Returns `receipt_id`. Supports both SQLAlchemy (`db.py`) and sqlite3 (`database.py`) paths via `@_db_fallback`. |
| `get_receipts()` | Returns all receipts ordered by most recent first: `[(id, timestamp, total_amount, payment_method, sale_type)]` |
| `get_receipt_items(receipt_id)` | Returns line items for a receipt: `[(id, receipt_id, product_name, quantity, price_at_time, internal_barcode, vendor, expiry_date)]` |
| `get_receipt_items_grouped_by_date()` | Returns sold items grouped by date: `{date: [(id, receipt_id, name, qty, price, total, timestamp, payment, int_barcode, vendor, expiry)]}` |
| `get_all_receipt_items_flat()` | Returns all sold items as flat list for barcode search |
| `get_receipts_total_for_date(date_str)` | Returns sum of receipt totals for a specific date |
| `reverse_receipt_item(receipt_item_id)` | Reverses a sold item: restores to products, updates receipt total, deletes receipt if empty |
| `get_dashboard_metrics()` | Returns dict with: total_products, total_items_sold, total_revenue, in_stock_count, out_of_stock, expiring_soon, unique_vendors, total_inventory_value, low_stock_count |
| `get_sales_analytics(start_date, end_date)` | Returns analytics: ranked_products [(rank, name, qty, revenue, avg_price)], total_items_sold, total_revenue, unique_products, total_transactions, avg_basket_size |
| `add_patient(name, phone, email, custom_fields)` | Inserts patient + optional custom fields (EAV). Returns patient_id. |
| `get_all_patients(search_query)` | Returns all patients with custom fields dict: `[(pid, name, phone, email, created_at, {field: value})]` |
| `get_patient_by_id(patient_id)` | Returns single patient with custom fields, or None. |
| `update_patient(patient_id, name, phone, email, custom_fields)` | Updates core fields, replaces all custom fields (delete + re-insert). |
| `delete_patient(patient_id)` | Deletes patient and all custom fields (CASCADE). |

### `excel_handler.py` — Smart Mapping Import/Export Engine (170 lines)

| Function/Class | Purpose |
|---|---|
| `DB_FIELDS` | Schema dict: `{field_key: {label, required, default}}` for each importable field |
| `HEADER_ALIASES` | 30+ heuristic rules mapping lowercased header strings to DB field keys |
| `read_excel_headers(file_path)` | Returns `(headers: list[str], row_count: int)` without importing data |
| `auto_map_headers(excel_headers)` | Matches headers via aliases → `(mapping: {db_key: col_idx}, unmatched: [(idx, header)])` |
| `execute_import(file_path, column_map, default_values, on_complete)` | Background thread import using validated column_map. Creates unique barcodes per row. |
| `export_to_excel(data_list, headers, output_path, on_complete)` | Generic Excel export with styled headers, auto-sized columns. Background thread. |
| `export_inventory(output_path, on_complete)` | Exports current in-stock inventory to .xlsx with all batch columns. |

### `ui_inventory_tab.py` — Inventory Tab + Import Wizard (400 lines)

| Component | Purpose |
|---|---|
| `ImportWizardModal(ctk.CTkToplevel)` | Smart mapping wizard: DB fields with `CTkComboBox` (auto-mapped to Excel columns), default value `Entry` per field, unmatched columns with `[Ignore / Create Field]` toggle, required field validation, "Confirm Import" callback. |
| `setup_inventory_tab(self)` | Builds toolbar (search, action buttons, sort toggle), Treeview with professional styling, expiry alert bar. |
| `_configure_tree_tags(self)` | Configures `"odd"`/`"even"`/`"imported"` row tags for striping and import highlighting. |
| `_header_sort(self, col)` | Click-to-sort on column headers: ascending/descending toggle with ▲/▼ indicators, striping reapplied. |
| `load_inventory(self)` | Refreshes Treeview with alternating row tags, highlights recently imported batches. |
| `_refresh_after_import(self)` | Tags newly imported rows with `"imported"` highlight, auto-clears after 8 seconds. |
| `_import_excel(self)` | Reads Excel headers → opens `ImportWizardModal` → calls `execute_import()` with mapping. |

### `barcode_logic.py` — Barcode & Config (191 lines)

| Function | Purpose |
|---|---|
| `load_config()` | Reads `config.json`, creates with defaults if missing |
| `generate_internal_barcode(vendor_name)` | Returns `{VND[:3]}-{uuid6}` (e.g. `MED-A3F9B2`). Falls back to `PRD-` prefix for N/A vendors. Uses `uuid.uuid4().hex[:6].upper()` for cryptographic uniqueness. |
| `create_label(price, internal_barcode)` | Renders full label PNG to `labels/` dir |
| `generate_preview_image(flags, overrides, internal_barcode)` | Returns PIL Image for live preview |
| `open_label_engine(product_id, barcode_value, ...)` | Launches label_engine/main.py subprocess with context |

---

## 7. Label Engine Source Files (`label_engine/`)

### `label_engine/main.py` — App Entry + Product Context (379 lines)

**Argparse:** `--id <product_id>`, `--barcode <barcode_value>`, `--name <product_name>`, `--price <product_price>`, `--expiry <date>`, `--manufacture <date>` for context-aware launch. Visibility flags: `--show-name`, `--show-price`, `--show-expiry`, `--show-barcode-text`.

**Class: `ZoomableLabelCanvas(LabelCanvas)`** (subclass of canvas_core LabelCanvas)

| Method | Purpose |
|---|---|
| `__init__(parent, width, height)` | Sets zoom=1.0, binds MouseWheel + Shift-MouseWheel for panning, canvas click for focus |
| `set_zoom(zoom)` | Clamps to ZOOM_MIN..ZOOM_MAX, updates scrollregion, redraws |
| `_update_scrollregion()` | Overrides parent: sets scrollregion to (0, 0, width*zoom, height*zoom) |
| `redraw()` | Overrides parent: calls draw_elements(scale=self.zoom), draws zoom-scaled selection rect + resize handles |
| `_on_mousewheel(event)` | Vertical scroll (yview_scroll) |
| `_on_shift_mousewheel(event)` | Horizontal scroll (xview_scroll) |

**Class: `LabelEngineApp(ctk.CTk)`**

| Method | Purpose |
|---|---|
| `__init__(product_id, barcode_value, product_name, product_price, product_expiry, product_manufacture, show_*)` | Window setup, ttk.PanedWindow layout, 3-tier context loading |
| `_load_product_context` | 3-tier fallback: (1) saved label by real product_id, (2) template with var_context substitution, (3) hardcoded defaults. Treats `"NEW"` sentinel as no product ID. |
| `_build_menu` | File menu: Save (Ctrl+S), Load (Ctrl+O), Export PNG (Ctrl+E), Print (Ctrl+P), Exit |
| `_build_toolbar` | Canvas size, + Text/Shape/Barcode/QR, Delete, Export PNG, Print, Zoom controls (-, %, +, Reset), Save Template, Load Template buttons |
| `_build_main_pane` | Creates ttk.PanedWindow (horizontal). Canvas frame: width=800, pack_propagate(False), weight=1. Properties panel: width=350, pack_propagate(False), weight=0 |
| `verify_layout_geometry` | Geometric auditor: fetches actual winfo_width() of window, canvas frame, and properties panel; asserts panel >= 300px, panes don't exceed window, canvas >= 200px |
| `_save_file` | Uses `save_label_by_id()` if real product context (not "NEW"), else opens Save dialog |
| `_load_file` | Uses `load_label_by_id()` if real product context (not "NEW"), else opens Load dialog |
| `_export_png` | Opens Export PNG dialog → `export.export_to_png()` |
| `_print_label` | → `export.print_label()` → temp PNG → Windows print dialog |
| `_delete_selected` | Removes the currently selected element |

### `label_engine/canvas_core.py` — Canvas Engine (435 lines)

**Class Hierarchy:**
```
LabelElement (base dataclass)
├── BarcodeElement    — Code128 barcode rendering via python-barcode
├── QRElement         — QR code rendering via qrcode library
└── ShapeElement      — Rectangle, ellipse, rounded-rectangle with configurable fill/border
```

**Unified Renderer:**
`draw_elements(surface, elements, scale=1.0)` — Draws all elements onto either a `tkinter.Canvas` or a `PIL.Image`. Handles text (with `_fit_text_to_width` auto-scaling, `anchor="w"` left-aligned), shapes, barcodes, and QR codes.

**`LabelCanvas` class:** add_element, remove_element, select, redraw, _update_scrollregion, _canvas_coords. Drag (B1-Motion), Resize (5 handles), Hit-test selection.

### `label_engine/properties_panel.py` — Property Editor (214 lines)

| Group | Shown For | Fields |
|---|---|---|
| `text_fields` | `type == "text"` | Text, Font dropdown, Size, Color hex |
| `shape_fields` | `type == "shape"` | Shape type dropdown, Fill Color, Border Color, Border Width |
| `barcode_fields` | `type == "barcode"` | Data, Show Text checkbox |
| `qr_fields` | `type == "qr"` | Data, Fill Color, Back Color |
| `no_selection` | Nothing selected | "No element selected" label |

### `label_engine/export.py` — Export & I/O (113 lines)

| Function | Purpose |
|---|---|
| `save_label(filename, canvas)` | Serializes canvas to JSON via `to_dict()` |
| `load_label(filename, canvas)` | Deserializes JSON, restores canvas via `from_dict()` |
| `export_to_png(filename, canvas)` | Renders to PIL Image at 300 DPI via `draw_elements()` |
| `print_label(canvas)` | Exports to temp PNG, invokes Windows print via `os.startfile(path, "print")` |
| `get_label_path(product_id)` | Returns `data/labels/<product_id>.json` path |
| `save_label_by_id(product_id, canvas)` | Saves label to ID-based path |
| `load_label_by_id(product_id, canvas)` | Loads label from ID-based path |
| `save_template(canvas)` | Saves canvas layout to `label_template.json` |
| `load_template(canvas)` | Loads template from `label_template.json` |

---

## 8. Tech Stack

| Component | Choice | Version |
|---|---|---|
| Language | Python | 3.12.7 |
| GUI | customtkinter | 6.0.0 |
| Imaging | Pillow | 12.3.0 |
| Barcode | python-barcode | 0.16.1 |
| QR Code | qrcode | 8.2 |
| Database | sqlite3 | stdlib |
| UUID | uuid | stdlib |
| Fuzzy Search | rapidfuzz | 3.14.5 (C++ backend, difflib stdlib fallback) |
| Native Barcode | Rust/PyO3 (barcode_gen.pyd) | 1.0.0 (uuid v4 batch, Python barcode_logic fallback) |
| Packaging | PyInstaller | (build spec) |

---

## 9. System Flow

```
main_app.py
  → main.py (PharmacyApp)
    → database.init_db() → creates/migrates all 4 tables
    → barcode_logic.init_labels_dir()

Add Product Flow (1 box):
  → setup_add_tab() → form: template, name, price, mfg barcode, expiry, mfg date, vendor
  → save_product() → validates dates → generate_internal_barcode(vendor_name) → add_product()
  → add_product() → INSERT INTO products (one serialized row with unique barcode)
  → LabelDesignerPopup(self, name, price, int_barcode, expiry, mfg)
    → update_preview() → draw_elements(preview_canvas, elements, context=ctx)
    → launch_m8_engine() → open_label_engine("NEW", barcode, name, price, expiry, mfg, show_*)

Receive Inventory Flow (Queue-Based — ATOMIC per vendor):
  → setup_receive_tab() → 3-zone layout (A: input, B: PO treeview, C: commit)
  → _add_to_queue() → validates inputs → appends to self.receiving_session[vendor]["items"]
  → _refresh_po_treeview() → clears + rebuilds tree_po from receiving_session
  → _commit_shipment() → iterates receiving_session:
      → for each vendor, for each item:
          → receive_inventory_atomically(vendor, item, date, qty, cost, price, mfg_barcode, expiry, mfg_date, barcode_generator)
              → BEGIN TRANSACTION
              → LOOP qty times:
                  → barcode_generator(vendor) → unique barcode (VND-XXXXXX)
                  → INSERT INTO products (one serialized row)
              → INSERT INTO receiving_log (shipment ledger entry)
              → COMMIT (or ROLLBACK on any error)
      → receiving_session.clear()
      → load_inventory() + load_receiving_log() → cross-tab sync

Inventory Tab Flow:
  → load_inventory() → get_grouped_products() → GROUP BY name, COUNT(*) → parent rows
  → double-click group → _toggle_group() → get_batches_by_name() → individual box rows
  → sort toggle (Expiry Date / Mfg Date) → _on_sort_change() → re-query with new ORDER BY
  → sell_product() → batch-level selection → mark_item_as_sold(barcode) → DELETE + INSERT
  → open_label_for_selected() → batch-level selection → LabelDesignerPopup with unique barcode
  → EditBatchDialog._save() → update_product_full() → cascade vendor/name/price via WHERE barcode = ?
  → if vendor changed N/A→valid → QuickReceiveModal (qty + cost → log_shipment())

Sales Report Flow:
  → load_sales_report() → get_sold_items() → individual sold boxes with barcodes
  → refund_item() → reverse_sale(sold_id) → DELETE from sold_items, INSERT back to products

Checkout & Receipts Flow (Phase 13 — Serialized Multi-Item):
  → setup_checkout_tab() → balance panel (Subtotal/Tax/Total + Amount Tendered + Change Due),
    cart Treeview columns: (Item, Qty, Unit Price, Tax, Total), barcode scan entry
  → _pos_scan_barcode(barcode) → looks up internal_unique_barcode → groups by product_name,
    appends barcode to `internal_barcodes` list (rejects duplicates) → auto-appends to pos_cart
  → _pos_adjust_qty(delta) → +1: FIFO-adds oldest In Stock box not yet in cart;
    -1: pops one barcode from internal_barcodes list (min qty = 1)
  → _pos_refresh_cart() → recalculates per-line tax (subtotal × tax_rate/100), updates Treeview
    + balance panel labels, calls _pos_update_change()
  → _pos_complete_sale() → database.checkout_cart_atomically(method, cart, patient_id, tax_rate):
      → BEGIN TRANSACTION
      → INSERT INTO receipts (timestamp, total_amount=subtotal+tax, payment_method, patient_id)
      → FOR EACH cart entry: INSERT INTO receipt_items (internal_barcode=CSV of barcodes)
      → FOR EACH barcode IN entry.internal_barcodes:
          → SELECT product WHERE internal_unique_barcode=barcode AND status='In Stock'
          → if not found → ROLLBACK + raise ValueError
          → INSERT INTO sold_items (item_name, price, mfg_barcode, internal_barcode, timestamp, vendor_name)
          → DELETE FROM products WHERE id = product_id
      → COMMIT (or ROLLBACK on any error)
  → receipt_engine.generate_receipt(receipt_id, cart, subtotal, total, tax=tax, ...) →
    renders txt receipt with Subtotal/Tax/TOTAL breakdown
  → audit_log.log_action("CHECKOUT", ...)

Integration Bridge:
  main_app.open_label_engine(product_id, barcode_value, ...)
    → subprocess.Popen: label_engine/main.py --id <id> --barcode <barcode> ...
      → auto-loads saved label from data/labels/<id>.json (if exists)
      → or auto-creates elements from args (gated by show_* flags)

Template System:
  Standalone engine toolbar → "Save Template" → save_template(canvas) → label_template.json
  Standalone engine toolbar → "Load Template" → load_template(canvas) → restores layout
  LabelDesignerPopup → reads label_template.json → dynamic entry fields via {{VAR}} syntax
```

Settings & Config Flow (Phase 13.5 — Dynamic Settings Tab):
  → setup_settings_tab() renders form: Pharmacy Name, Address, Phone, Tax Rate (%),
    Font Size, Receipt Header/Footer Notes, DB Path, PG Sync, Email Report
  → All fields pre-populated from barcode_logic.load_config() (reads config.json fresh)
  → save_settings() validates inputs (tax_rate float 0–100, font_size positive int),
    merges updates into existing config dict (preserves license_key, email_report,
    expiry_ignore_list, and any future keys), writes config.json
  → _notify_config_updated() broadcast: delegates to _notify_inventory_updated() +
    _refresh_cart_treeview() (re-reads tax_rate → recomputes Tax/Total) +
    _checkout_update_change() (recomputes Change Due) + load_dashboard()
  → POS Checkout re-renders balance panel (Subtotal/Tax/Total/Change) immediately,
    no restart required
  → _pos_complete_sale() reads pharmacy_info (incl. receipt_header_note/footer_note)
    from config fresh at sale time → receipt_engine.generate_receipt() renders notes
    between header/sep and "Thank you"/sep respectively

---

## 10. Dependencies

| Package | Used By | Purpose |
|---|---|---|
| `customtkinter` | `ui.py`, `main.py`, `label_engine/main.py`, `design_system.py` | GUI framework | | |
| `python-barcode` | `barcode_logic.py`, `label_engine/canvas_core.py` | Code128 barcode rendering |
| `Pillow` | `barcode_logic.py`, `label_engine/canvas_core.py` | Image composition + element rendering |
| `qrcode` | `label_engine/canvas_core.py` | QR code image generation |
| `sqlite3` | `database.py`, `db.py` | Database (stdlib) |
| `sqlalchemy` | `db.py` | ORM layer with `text()` query API |
| `pytesseract` | `ocr_engine.py` | Tesseract OCR wrapper (optional — auto-detected at runtime) |
| `easyocr` | `ocr_engine.py` | EasyOCR alternative backend (optional — auto-detected at runtime) |
| `uuid` | `barcode_logic.py` | Cryptographic barcode generation (stdlib) |
| `tkinter` | `ui.py`, `label_engine/canvas_core.py` | Canvas, Treeview, messagebox (stdlib) |

---

## 11. Build & Run

```bash
# Install dependencies
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Run full pharmacy suite
python main_app.py

# Run label designer only (standalone)
python label_engine/main.py

# Run label designer with product context
python label_engine/main.py --id PROD-001 --barcode MED-A3F9B2 --name "Aspirin 500mg" --price "$5.99"

# Build standalone executable (Windows)
pyinstaller main.spec
# Output → dist/main.exe
```

---

## 12. ORPHANS & PENDING

### Active TODO Items

| Item | Status |
|---|---|
| Replace `API_BASE_URL` placeholder in `licensing/main.py` with real Vercel URL | Pending deployment |
| Deploy `licensing/` to Vercel | Obsolete — `licensing/` archived; LS webhook consolidated into `backend/app.py` (§7) |
| Create Upstash Redis database + set env vars in Vercel | Obsolete — `licensing/` archived; LS webhook consolidated into `backend/app.py` (§7) |
| Enable GitHub Pages (source: `licensing/static/` folder on `main` branch) | Pending manual setup |
| Fix pre-existing locale key gap: `transaction_complete_msg`, `search_ndc`, `insufficient_stock_pos`, `select_payment_method`, `pos_transaction_log` missing from `locales/ar.json` (discovered during Phase 13.5 verification — NOT introduced by Phase 13.5) | Pending (out of scope) |
| **Bulk Import UI** — `ui_bulk_import.py` created with `BulkImportFrame` (file selection → `StagingTable` → 20-row preview → mapping → `commit_staged_products`). Wired into `main_app.py:_wire_rx_extensions()` with `from ui_bulk_import import setup_bulk_import_tab`, `setup_bulk_import_tab(self)` call, and `bulk_import_title` refresh branch in `_patched_on_tab_change`. `commit_staged_products()` now invoked from the app via the Execute button. 7 new i18n keys added to all 6 locale files. | Complete | 2026-08-05 |

### Known Orphans

| Item | Detail |
|---|---|
| `receiving_log` entries 1 & 2 | Pre-serialization artifacts (dated 2026-07-14). They lack `barcode` values intentionally to preserve historical accuracy. Entry 1: 50x aspirin from medsupply ($200). Entry 2: 50x bands from medsupply ($100). No referential link to `products` exists and no further action is required. |

### Completed Items

| Milestone | Description | Status |
|---|---|---|
| RX-1 | `archive/rx_db.py` — SQLAlchemy ORM models (Prescriber, InventoryExtended, RxTable, Insurance, AuditLogEntry, RxConfigEntry) all with `regional_metadata` JSON columns + audit log extensions | ✅ Complete |
| RX-2 | `archive/rx_database.py` — sqlite3 + `_db_fallback` pattern with `row_factory=sqlite3.Row`, `PRAGMA foreign_keys=ON`, prescription CRUD + JSON serialization | ✅ Complete |
| RX-3 | `archive/rx_config.py` — ConfigManager singleton, unit conversions, regional label registry, Fernet credential encryption (with stdlib HMAC fallback) | ✅ Complete |
| RX-4 | `archive/rx_strategies.py` — PharmacyIntegrationStrategy ABC + authenticate(), USBillingStrategy, EUBillingStrategy, MockProvider, strategy_factory | ✅ Complete |
| RX-5 | `archive/ui_rx_workflow.py` — Rx workflow UI with Custom Fields pattern replicated verbatim from `ui_patients_tab.py:125-282`, prescription CRUD dialog | ✅ Complete |
| RX-6 | `archive/rx_integration_settings.py` — RxBillingSettingsFrame with US/EU region selector, encrypted credential entries, Test Connection, Save, file picker for EU cert | ✅ Complete |
| RX-7 | `archive/rx_init.py` — Standalone initialization script for Rx tables + region config | ✅ Complete |
| RX-8 | `archive/test_rx_config.py` — 21 tests: ConfigManager singleton, unit conversions, regional labels, Fernet round-trips | ✅ Complete |
| RX-9 | `archive/test_rx_database.py` — 16 tests: schema creation, FK constraints, JSON metadata, prescription CRUD, GDPR hard-delete | ✅ Complete |
| RX-10 | `archive/test_rx_strategies.py` — 30 tests: factory resolution, US/EU/Mock strategy behavior, authenticate() | ✅ Complete |
| RX-11 | `archive/rx_wiring_instructions.md` — Integration guide for main_app.py / ui.py without modifying core files | ✅ Complete |
| RX-12 | `archive/build_rx_app.py` — PyInstaller build automation with hidden imports (cryptography, sqlalchemy, customtkinter) + data bundling | ✅ Complete |
| RX-13 | `archive/verify_build.py` — Post-build verification: exe existence, data files, module compilation, imports, spec hidden imports (4/5 checks pass pre-build) | ✅ Complete |
| RX-14 | `archive/PharmacyPro_Rx.spec` — PyInstaller spec with all RX modules + hidden imports | ✅ Complete |
| RX-15 | `archive/rx_config.json` — Default region config (US, imperial, HIPAA) | ✅ Complete |
| RX-16 | `archive/ui_enterprise_settings.py` — EnterpriseSettingsFrame: region selector, Fernet-encrypted credential persistence to rx_secrets.json, connection testing via strategy.authenticate(), 14-column compliance audit log viewer with search/export | ✅ Complete |
| RX-17 | `archive/ui_pos_terminal.py` — PosTerminalFrame: Rx inventory search (inventory_extended via rx_db with sqlite3 fallback, async via AsyncUI), cart management, 4 sale types (Delivery/OTC/Rx OTC/Loyalty), tax/total calculation, inventory decrement, transaction logging via audit_log.log_action, recent transactions view | ✅ Complete |
| M1–M27 | Label Engine + Pharmacy Core | ✅ Complete |
| M28 | Vendor Traceability (vendor_name column + cascade + receiving_log barcode) | ✅ Complete |
| M29 | Quick Receive Modal (vendor N/A→valid triggers qty/cost dialog) | ✅ Complete |
| M30 | Serialized Barcode Generation (`{VND[:3]}-{uuid6}` format) | ✅ Complete |
| M31 | Serialized Receiving Loop (`log_shipment_handler()` + `QuickReceiveModal` create N rows per shipment) | ✅ Complete |
| M32 | Atomic Receiving (`receive_inventory_atomically()` — single transaction with rollback) | ✅ Complete |
| M33 | Legacy Barcode Normalization (`migrate_data.py` — renames ~49 old-format barcodes to `{VND[:3]}-{UUID6}` with receiving_log cascade) | ✅ Complete |
| M34 | Vendor Prefix in Inventory Treeview (child rows show barcode prefix e.g. `MED` for instant vendor identification) | ✅ Complete |
| M35 | Purchase Order & Receiving Dashboard (queue-based state management, 3-zone UI, cross-tab sync on commit) | ✅ Complete |
| M36 | Shipment History Bridge (`save_product()` + `EditBatchDialog._save()` now log to `receiving_log` — Shipment History shows Add Product + vendor-change entries) | ✅ Complete |
| M37 | Shipment History Unit Cost Display (tree_history "Cost" column shows per-box unit cost — directly comparable to Inventory "Price" column) | ✅ Complete |
| M38 | Vendor-Filtered Combobox + Auto-Fill Expansion (Receive tab product combobox filters by vendor, `_on_product_change()` autofills Unit Price + Mfg Barcode from vendor-specific template) | ✅ Complete |
| M39 | Shipment History Cost Alignment (`_commit_shipment()` + `QuickReceiveModal._submit()` store `qty × tpl_price` as `total_cost` — all paths now produce matching unit_cost) | ✅ Complete |
| M40 | Price Cascade to Receiving Log (`update_product_full()` now cascades price changes to `receiving_log.total_cost` — `total_cost = new_price × quantity`) | ✅ Complete |
| M41 | Vendor-Grouped Shipment History (tree_history upgraded to hierarchical treeview — parent rows = vendor groups with unit count, child rows = individual shipment entries) | ✅ Complete |
| M42 | Click-to-Sort Date Column (Date column heading is clickable — sorts child rows within each vendor group chronologically, toggles ascending/descending with arrow indicator) | ✅ Complete |
| M43 | Date Filter for Shipment History (date entry + Filter/Clear buttons — filters treeview to show only shipments from a specific date, grouped by vendor) | ✅ Complete |
| M44 | Bulk Add from Add Product Tab (`BulkAddModal` — "Quick Receive (Bulk)" button creates N serialized boxes with unique barcodes in single transaction, logs consolidated shipment to `receiving_log`) | ✅ Complete |
| M45 | Bulk Print Tags + Save to Queue (`BulkAddModal` dual-path: "Submit & Save Directly" preserves existing DB-write path; "Save to Queue" stages items in `receiving_session` for Pending PO commit. "Print All Tags" checkbox triggers batch label printing via template. `_commit_shipment()` uses stored `pre_barcodes` to ensure printed labels match committed DB barcodes.) | ✅ Complete |
| M46 | License Gate — Client-Side (`license_gate.py`: hardware fingerprinting via SHA-256, 24-hour offline cache with clock-rollback protection, `LicenseGate` CTk blocking window. `main.py` wrapper blocks `PharmacyApp` launch until validation passes. `config.json` extended with `license_key` field.) | ✅ Complete |
| M47 | License Server — Backend (`licensing/api/`: `BaseHTTPRequestHandler` endpoints for activate/validate/webhook. Upstash Redis via REST API. Lemon Squeezy webhook integration.) **Superseded 2026-08-06:** the `webhook` endpoint (`archive/licensing/api/webhook.py`) was deleted; Lemon Squeezy webhooks are handled solely by `backend/app.py` — see §7. | ✅ Complete |
| M48 | Landing Page — GitHub Pages (`docs/`: dark-themed responsive site with hero, features grid, how-it-works steps, pricing card, and footer. Lemon Squeezy Checkout CTA. Vanilla JS with smooth scroll, intersection observer animations, and analytics placeholder.) | ✅ Complete |
| M49 | Checkout & Receipts Module (`receipts` + `receipt_items` tables in DB. New "Checkout" tab with product selector, cart Treeview, running total, payment method (Cash/Card/Transfer), amount paid + change calculator, confirm button that atomically deducts stock and creates receipt. Receipts History with double-click detail view.) | ✅ Complete |
| M50 | Batch-Aware Selling (flat batch-level inventory treeview — no parent/child grouping. Every in-stock batch is its own top-level row with columns: Drug Name, Price, Int. Barcode, Vendor, Expiry, Mfg Date, Mfg Barcode. Stock deduction uses `WHERE internal_unique_barcode = ?` instead of FIFO-by-name. Cart deduplication by `product_name + internal_barcode`. `_send_to_checkout()`, `_edit_batch()`, `open_label_for_selected()`, search, sort all adapted to flat structure.) | ✅ Complete |
| M51 | Dev Hardware MAC Whitelist + Standalone Key Generator (`license_gate.py`: `get_device_mac()` extracts MAC via `uuid.getnode()` with try/except safety; `DEV_MAC_WHITELIST` set constant; `is_dev_mac()` checks membership. `main.py` + `validate_license()` both check MAC before license gate — whitelisted devices skip GUI entirely and return `(True, "Dev Hardware Bypass Active")`. `generate_key.py`: standalone argparse CLI — `--days`, `--prefix`, `--email` — generates `{PREFIX}-XXXX-XXXX-XXXX` via `secrets.token_hex(4)`, inserts into `licenses.db` with WAL mode and 10s timeout.) | ✅ Complete |
| M52 | Phase 0: `ui.py` Monolith Modularization (3647 → 303 lines, 93% reduction). Split into 11 focused module files: `ui.py` (wrapper + shared methods), `ui_helpers.py`, `ui_modals.py`, `ui_add_tab.py`, `ui_inventory_tab.py`, `ui_expiring_tab.py`, `ui_report_tab.py`, `ui_receive_tab.py`, `ui_checkout_tab.py`, `ui_templates_tab.py`, `ui_settings_tab.py`. Module-level functions attached to `PharmacyApp` class post-import — preserves all `self` references without mixin complexity. | ✅ Complete |
| M53 | Phase 1 Part 1: `barcode_logic.py:_find_python_executable()` PyInstaller Fix (detects `sys.frozen` builds, searches venv + PATH for real Python via `shutil.which()`, raises descriptive exception if none found in frozen mode). **Verified:** venv detection now checks `archive/venv/Scripts/python.exe` first regardless of frozen state — fixes MinGW Python fallback issue. | ✅ Complete |
| M54 | Phase 1 Part 2: `database.py` Enhanced Metrics + Analytics (`get_dashboard_metrics()` now returns `total_inventory_value` + `low_stock_count`; new `get_sales_analytics(start_date, end_date)` returns ranked products with qty sold, revenue, avg price, plus total_items_sold, total_revenue, unique_products, total_transactions, avg_basket_size). | ✅ Complete |
| M55 | Phase 1 Part 2: Dashboard Tab (`ui_dashboard_tab.py` — 8 KPI cards in responsive grid: total products, in-stock count, low stock, expiring soon, today's revenue, total revenue, unique vendors. Low-stock alerts panel with item names + quantities. Expiry summary panel with critical/warning/safe counts. Auto-refresh on tab switch.) | ✅ Complete |
| M56 | Phase 1 Part 2: Report Tab Analytics Upgrade (`ui_report_tab.py` — segmented "Sales"/"Analytics" switcher. Sales view: existing date-based receipt treeview + barcode search + refund. Analytics view: date-range controls with presets (Today, This Week, This Month, Last 30 Days, This Year, Custom), 4 KPI cards (total sold, revenue, transactions, avg basket), ranked products treeview (top sellers by quantity), CSV export via stdlib `csv` module.) | ✅ Complete |
| M57 | Phase 2: Patient CRM Schema + CRUD (`database.py` — `patients` table: id, name, phone, email, created_at; `patient_fields` table: id, patient_id, field_name, field_value (EAV pattern for user-defined custom fields). Functions: `add_patient()`, `get_all_patients(search)`, `get_patient_by_id()`, `update_patient()`, `delete_patient()` with full transactional safety.) | ✅ Complete |
| M58 | Phase 2: Patient CRM Tab (`ui_patients_tab.py` — search bar with live filtering on name/phone/email, Treeview listing all patients with custom fields summary, Add/Edit modal dialog with dynamic custom field rows (add/remove), double-click to edit, delete with confirmation, wired to `database.py` CRUD.) | ✅ Complete |
| M59 | Phase 2: Excel Import/Export Engine (`excel_handler.py` — `import_inventory_from_excel()` maps Excel columns (Name, Price, Expiry, SKU, Vendor) to serialized products with unique barcodes; `export_to_excel()` outputs formatted .xlsx with styled headers and auto-sized columns; `export_inventory()` shortcut for in-stock inventory. All operations run in background threads with GUI loading feedback via `on_complete` callbacks.) | ✅ Complete |
| M60 | Phase 2: Inventory Tab Excel Buttons (`ui_inventory_tab.py` — "Import Excel" (purple) and "Export Excel" (blue) buttons in the toolbar, wired to threaded `excel_handler` functions with non-blocking Toplevel loading indicators and result messageboxes.) | ✅ Complete |
| M61 | Smart Mapping Wizard (`excel_handler.py` + `ImportWizardModal` — `read_excel_headers()` reads Excel headers + row count without importing. `auto_map_headers()` uses 30+ heuristic alias rules to auto-match headers to DB fields. `ImportWizardModal` Toplevel presents: DB fields with `CTkComboBox` mapped to Excel columns (auto-selected or manual), default value `Entry` per field, unmatched columns with `[Ignore / Create Field]` segmented toggle, required field validation. `execute_import()` accepts validated `column_map` + `default_values` dict.) | ✅ Complete |
| M62 | Inventory Tab Visual Overhaul (`ui_inventory_tab.py` — alternating row striping via `"odd"/"even"` tags (#2b2b2b/#333340), import highlight tagging (`"imported"` tag → #1a3a2a with 8-second auto-clear), column header click sorting (ascending/descending with ▲/▼ arrow indicators, striping reapplied after sort), professional column alignment (strings left, prices right, dates center), bold Segoe UI headings with hover color.) | ✅ Complete |
| M63 | POS Checkout Tab Rewrite (`ui_checkout_tab.py` — cart with Qty column + per-item quantity display, Qty +/- adjustment buttons, Remove/Clear Cart, receipt detail modal via `get_receipt_items()` messagebox, patient linkage via CTkComboBox, barcode scan with dedup merge, Complete Sale with audit log + receipt creation. All backward-compatible stubs preserved for ui.py imports.) | ✅ Complete |
| M64 | Receipt Generation Engine (`receipt_engine.py` — thermal-format .txt receipts with pharmacy name/address/phone header, patient name, itemized line totals, payment method. `open_receipt_file()` auto-opens after sale. `ui_checkout_tab.py` passes pharmacy config + patient name to generator, asks to open receipt after each sale.) | ✅ Complete |
| M65 | Label Print Dialog (`ui_inventory_tab.py` — `LabelPrintDialog` Toplevel: displays product info, quantity input, "Generate Labels" creates N barcode label PNGs via `barcode_logic.create_label()`, "Open Label Designer" launches full M8 engine. Toolbar "Label" button renamed to "Print Label" and wired to new dialog.) | ✅ Complete |
| M66 | Store Configuration Fields (`ui_settings_tab.py` + `barcode_logic.py` — new config fields: `address`, `phone`, `tax_rate` (float 0-100%). Settings tab rows shifted to accommodate Address, Phone, Default Tax Rate (%) fields. `save_settings()` validates tax rate 0-100 and persists all new fields. Config defaults updated in `load_config()`.) | ✅ Complete |
| M67 | Proactive Alert Engine & Tab Badges (`ui.py` — `_calculate_alert_counts()` returns low-stock + expiring-30d counts; `_update_tab_badges()` renames tab headers to "Inventory [N Alerts]" / "Expiring Soon [N]". `ui_inventory_tab.py` — filter toggle segmented control: All / Low Stock / Expiring Soon filters Treeview rows. Badge auto-refreshes on `_notify_inventory_updated()`.) | ✅ Complete |
| M68 | Sales Analytics & Reporting Overhaul (`ui_report_tab.py` — Est. Profit KPI card added to analytics panel (30% margin estimate); "Export Sales Report (CSV)" button added to Sales view exports full grouped report; `barcode_logic.load_config()` supplies tax_rate for profit calc.) | ✅ Complete |
| M69 | Automated Database Backup (`backup.py` — `MAX_BACKUPS` increased to 10; `create_backup()` copies `pharmacy.db` to `archive/backups/pharmacy_backup_YYYYMMDD_HHMMSS.db` with auto-cleanup. Settings tab "Backup Database Now" button wired to `backup_database_gui()` with success notification.) | ✅ Complete |
| M70 | Audit Trail Viewer (`audit_log.py` — `user_pin` column added via migration; `log_action()` accepts `user_pin` param; `get_logs()` supports `search_query` filter. `ui_settings_tab.py` — `AuditLogViewer` Toplevel: searchable Treeview with Timestamp/Action/User-PIN/Details columns, alternating row striping, "View Audit Logs" button in Settings tab.) | ✅ Complete |
| M71 | Dynamic Path Resolution (`path_utils.py` — `get_resource_path()` resolves paths via `sys._MEIPASS` when frozen or `__file__` when running from source. `ensure_runtime_directories()` auto-creates `receipts/`, `backups/`, `labels/` at startup. Updated `barcode_logic.py`, `database.py`, `receipt_engine.py`, `backup.py`, `license_gate.py`, `main_app.py` to use `get_resource_path()` for all file I/O.) | ✅ Complete |
| M72 | PyInstaller Build Automation (`build_exe.py` — CLI script: `python build_exe.py` (production, `--noconsole`) or `--debug` (console). Auto-collects CustomTkinter assets, bundles `config.json`/`pharmacy.db`/`licenses.db` as data files, registers 25+ hidden imports. Output: `dist/PharmacyManagementSystem/PharmacyManagementSystem.exe`.) | ✅ Complete |
| M73 | Production License Fallback (`license_gate.py` — `_frozen_app_dir()` resolves writable paths next to `.exe` (not `_MEIPASS`). License cache + `licenses.db` stored in exe directory when frozen. `is_dev_mode()` structurally returns False for frozen builds. Offline validation falls back to local cache → local DB → server.) | ✅ Complete |
| M74 | Custom Application Icon (`build_exe.py` — `_find_icon()` searches assets/ for logo.ico/app.ico/pharmacy.ico/icon.ico, accepts `--icon` CLI flag, graceful skip if none found. `ui.py` — `_set_window_icon()` sets title bar icon via `iconbitmap()` at startup with same search order + fallback.) | ✅ Complete |
| M75 | License Server + Deployment (`server_app.py` — Flask app with `/api/validate`, `/api/activate` (public), `/api/create` + `/admin` (protected by `SERVER_ADMIN_SECRET` header). Same SQLite schema as generate_key.py. `deploy_to_server.py` — reads `.env` credentials, uploads server_app.py to PythonAnywhere via REST API, triggers webapp reload. Supports `--upload`, `--reload`, `--dry-run` flags.) | ✅ Complete |
| M76 | Enterprise License Features (`server_app.py` — HWID binding: `/api/validate` + `/api/activate` accept `hwid` field, bind on first activation, reject mismatch with 403. Payment webhooks: `/api/webhook/paddle` (HMAC-SHA256) + `/api/webhook/paymob` (HMAC-SHA512) with signature verification, auto-generate license on success. Rate limiting: Flask-Limiter with 10/min activate, 30/min validate, 5/min create. Structured logging: timestamp, endpoint, status, IP, user-agent to server.log + stdout. Error handlers: 404, 405, 429, 500 return JSON. `license_gate.py` — HWID sent in API requests, itsdangerous signed cache tokens with 7-day offline grace, device-bound signing key, clock-rollback protection.) | ✅ Complete |
| M77 | Command Center Architecture (`hub.py` — unified local CLI orchestration script with 6 subcommands: `deploy` (Vercel CLI prod build + `--rollback`), `vercel-logs` (REST API: list deployments + optional raw build events, reads VERCEL_OIDC_TOKEN), `test-webhook` (fires mock JSON payloads for `paddle`/`lemonsqueezy` with 3 event templates each: subscription_created, payment_succeeded/order_created, subscription_cancelled; `--prod` flag routes to PythonAnywhere), `paddle-lookup` (queries Paddle Sandbox/Prod API for customer + subscriptions by email using PADDLE_API_KEY), `ls-lookup` (queries Lemon Squeezy API for orders + subscriptions by email), `validate-ui` (Playwright headless browser: 4-step test — page load, broken image scan, optional checkout flow simulation with screenshot-per-step, final snapshot). Auto-loads all credentials from `.env.local`.) | ✅ Complete |
| M78 | Autonomous Crash Reporter + AI Debug Agent (`crash_reporter.py` — `sys.excepthook` wrapper that POSTs structured error telemetry to `/api/report-error`. Payload: error_type, traceback, crash_frame, hashed HWID, OS info, app_version. Non-blocking daemon thread. `server_app.py` — `/api/report-error` validates payload, creates GitHub Issue with `automated-crash` label via REST API, checks `KNOWN_FIXES` dict for auto-email dispatch. `ai-debug-agent.yml` — GitHub Actions workflow triggers on `automated-crash` label, reads issue body, searches codebase for crash location, uses LLM to draft analysis + fix suggestions, posts comment, creates PR if applicable. `exhaustive_verify.py` — 104 checks all PASS.) | ✅ Complete |
| M79 | **Phase 2: SQLAlchemy ORM Layer** (`db.py` — full ORM models matching `database.py` schema exactly (Product, Template, SoldItem, ReceivingLog, Receipt, ReceiptItem, Patient, PatientField, AuditLog). `_resolve_database_url()` supports `DATABASE_URL` env var, `database_url` (PostgreSQL), `db_path` (SQLite), and SQLite fallback. `get_session()` context manager with auto-commit/rollback. `init_db()` with `create_all()` + SQLite migration (ALTER TABLE, PRAGMA checks) + default template seeding. All 57 query functions implemented using SQLAlchemy `text()` with `:param` named parameters. `database.py` updated to `@_db_fallback` decorator pattern — delegates to db.py ORM first, falls back to original sqlite3 code on any failure. Zero regression: all 19 modules importing `database` work unchanged. `exhaustive_verify.py`: 103/104 PASS.) | ✅ Complete |
| M80 | **Phase 3: OCR Cascade System** (`ocr_engine.py` — `OCRCascadeEngine` with abstract `OCREngine` base class, `TesseractEngine`/`EasyOCREngine`/`PillowPatternEngine` backends, `ExtractionResult` dataclass with normalized confidence (0.0–1.0) + `needs_review` flag, Pillow-based preprocessing strategies (standard/adaptive/enhanced/minimal). `ocr_cascade.py` — `OCRCascade` with 4-tier confidence cascade: Tier 1 Tesseract Standard (90%), Tier 2 Tesseract Enhanced (70%), Tier 3 EasyOCR (50%), Tier 4 Pillow Pattern (30%). Skips unavailable engines, returns `CascadeResult` with all tier details + metadata. `design_system.py` — `OCRProgressBar`, `CascadeStatusBadge`, `OCRFeedbackBadge`, `OCRCascadeMonitor` UI components using customtkinter with PharmacyPro color scheme, background-thread execution with real-time UI updates.) | ✅ Complete |
| M81 | **Phase 4: Daily Sales Email System** (`local_daily_report.py` — `DailyReportGenerator` class with `ReportMetrics`/`EmailConfig` dataclasses. Dynamically queries SQLAlchemy backend via `db.get_session()` context manager for yesterday's revenue, total patient count, top-selling items (daily/weekly/monthly toggle), and low stock alerts. Email compilation with HTML + plain-text MIME multipart. SMTP dispatch in background daemon thread via `send_report_async()`. Password sourced from `SMTP_PASSWORD` env var, never stored in config.json. `ui_settings_tab.py` — email section with recipient field, SMTP host/port/username/password, period toggle (daily/weekly/monthly), enable/disable checkbox, "Send Test Email" button with non-blocking background dispatch + async status feedback via `after()` callback. `config.json` updated with `email_report` defaults.) | ✅ Complete |
| M82 | **Phase 5: Scoped UI Redesign** (`ui_navigation.py` — `NavigationDrawer` with styled CTkButton list with badge support, `TabViewCompat` shim providing full CTkTabview API (add/tab/get/set/configure) for zero-code-change migration, `CompactCard` reusable card widget with header + badge, `BadgeLabel` color-coded status widget. `ui.py` — replaced CTkTabview with NavigationDrawer + TabViewCompat, `_update_tab_badges()` refactored to use `drawer.update_badge()` with color-coded status. `ui_dashboard_tab.py` — modern CompactCard KPI cards, CascadeStatusBadge integration in header. `ui_settings_tab.py` — email section wrapped in card layout with CascadeStatusBadge + SMTP status indicator. `ui_checkout_tab.py` — Order Summary card with CascadeStatusBadge, Email Report card with "Send Today's Report" button. `ui_expiring_tab.py`/`ui_inventory_tab.py`/`ui_patients_tab.py`/`ui_templates_tab.py`/`ui_report_tab.py`/`ui_receive_tab.py` — added consistent title headers with `text_color="#f0f0f0"`, consistent grid row configs for visual alignment. `exhaustive_verify.py`: 103/104 PASS — zero regressions.) | ✅ Complete |
| M83 | **Phase 6: Rust Extensions (1)** (`archive/rust_crypto/` — PyO3 cdylib using aes 0.8 + cbc 0.1 + hmac 0.12 + sha2 0.10 + pbkdf2 0.12, providing `encrypt_py`/`decrypt_py`/`derive_key` Fernet AES-128-CBC+HMAC-SHA256 token functions. `archive/hw_client/` — PyO3 cdylib using sha2 0.10 + mac_address 1.0 + gethostname 1.0, providing `get_anonymized_hwid`/`get_device_id`/`get_device_mac` hardware fingerprinting via WMIC/MAC/hostname. Both crates built with `abi3-py38` for Python 3.8-3.14 compatibility via `PYO3_USE_ABI3_FORWARD_COMPATIBILITY`. `crypto_utils.py` — `_resolve_backend()` now checks `hasattr(rust_crypto, 'encrypt_py')` to distinguish compiled extension from namespace package, falls back to cryptography→pycryptodome chain. `_RustBackend.encrypt` fixed to pass raw JSON string directly to `encrypt_py` (was double-encoding with `json.dumps(data.decode())`). `crash_reporter.py` — `_get_anonymized_hwid()` tries `hw_client.get_anonymized_hwid()` first with `hasattr` check, falls back to WMIC subprocess. `license_gate.py` — `get_device_mac()` and `_get_device_id()` try `hw_client` first, fall back to `uuid.getnode()`+platform. `check_repo.py` — added Rust crate file listing alongside GitHub remote verification. `exhaustive_verify.py`: 103/104 PASS — zero regressions.) | ✅ Complete |
| M84 | **Phase 7: Async Non-Blocking UI** (`async_ui.py` — centralized `ThreadPoolExecutor`-backed task manager with singleton pattern, thread-safe `.after()` callback marshaling, graceful shutdown with `cancel_futures`. `local_daily_report.py` — `send_report_async()` and `send_test_email_async()` now delegate to `AsyncUI.get().run()` instead of raw `threading.Thread`; callbacks receive `(result, error)` tuple. `crash_reporter.py` — `_crash_excepthook` and `report_error()` use `AsyncUI.get().run()` for non-blocking POST. `excel_handler.py` — `execute_import()` and `export_to_excel()` return `Future` via `AsyncUI`; callbacks now marshaled to main thread automatically. `ui_checkout_tab.py` — `_pos_refresh_patients()` runs DB query in background, updates combo via `.after()` callback. `ui_report_tab.py` — `load_sales_report()` and `load_analytics()` offloaded to `AsyncUI`, tree/KPI updates happen in main-thread callback. `ui_settings_tab.py` — `_on_complete` callback updated to `(result, error)` signature. `ui.py` — `PharmacyApp.__init__()` calls `init_async_ui(self)` to bind Tkinter root. `PharmacyPro_Enterprise.spec` / `build_exe.py` — added `async_ui` to hiddenimports. `exhaustive_verify.py`: 103/104 PASS — zero regressions.) | ✅ Complete |
| M85 | **Phase 8: Internationalization (i18n)** (`locales/en.json` — added 58 new i18n keys covering OCR cascade tiers (4), OCR cascade status/feedback badges (6 format + static), navigation drawer brand/subtitle (2), dashboard KPI labels (3), checkout tab labels (12), email report settings (12), PostgreSQL sync section (10), and async UI states (1). `locales/ar.json` — added 58 matching Arabic translations. `design_system.py` — `CascadeStatusBadge`, `OCRProgressBar`, `OCRFeedbackBadge` now use `i18n.t()` for all text; `TIER_NAMES` constant converted to `_tier_names()` function for runtime resolution. `ui_navigation.py` — `NavigationDrawer` header uses `i18n.t("app_brand_name")` / `i18n.t("app_subtitle")`. `ui_dashboard_tab.py` — all KPI titles, OCR label, low stock alerts panel use `i18n.t()`. `ui_checkout_tab.py` — all buttons, labels, payment methods, dynamic total/item-count formatting use `i18n.t()` with format strings. `ui_settings_tab.py` — email settings (recipient, SMTP host/port/user/pass, report period, enable toggle, test button, status messages), PostgreSQL sync section (URL, host, port, database, user, SSL mode, test connection, build URL), and audit button all use `i18n.t()`. `exhaustive_verify.py` tests 8.10/8.11 updated from `== 248` to `>= 248` to accept new keys. Dynamic formatting verified for `{tier}`, `{percent}`, `{count}`, `{total}`, `{review}`, `{message}`, `{backend}`, `{error}` placeholders. `exhaustive_verify.py`: 103/104 PASS — zero regressions.) | ✅ Complete |
| M86 | **Phase 9: Final System Validation** (`test_phase9_final_validation.py` — 24-test integration suite covering i18n language switching (EN↔AR), dynamic format string interpolation, locale key completeness (en/ar parity ≥248), AsyncUI singleton/executor lifecycle/thread cleanup/error isolation, crypto round-trip with Rust backend, HWID native extension integration, design_system i18n integration, concurrent task isolation, and no-hardcoded-strings audit across `design_system.py`, `ui_navigation.py`, `ui_dashboard_tab.py`, `ui_checkout_tab.py`. All 24/24 tests PASS. AsyncUI class gained `reset()` classmethod + `_executor = None` cleanup in `shutdown()`. `exhaustive_verify.py`: 103/104 PASS — zero regressions.) | ✅ Complete |
| M87 | **Phase 10: Executable Build & Deployment** (...). **FINAL: 105/105 PASS — 100% verification complete.**) | ✅ Complete |
| M88 | **Phase 13: Serialized POS Cart System** (`ui_checkout_tab.py` — cart Treeview columns: (Item, Qty, Unit Price, Tax, Total); barcode scanning stages individual `internal_unique_barcode` grouped by product name with duplicate rejection; balance panel with Subtotal/Tax/Total + Amount Tendered + Change Due; `database.checkout_cart_atomically()` atomically migrates staged barcodes from `products`→`sold_items`, creates `receipts`+`receipt_items`, computes flat tax from `config.json`, single SQLite transaction with rollback on missing barcode; `receipt_engine.generate_receipt()` extended with `subtotal`/`tax` params; `ui_inventory_tab.py:_send_to_checkout()` unified to `self.pos_cart`; `self.cart` removed from `ui.py`.) | ✅ Complete |
| M89 | **Phase 13 Fix:** `create_receipt()` retained for backward compatibility; `checkout_cart_atomically()` is the new primary checkout path. `generate_receipt()` signature changed: `subtotal` and `total` now required positional args; `tax` added as keyword arg. Tax row in receipt rendered only when tax > 0.) | ✅ Complete |
| M36.5 | **Phase 13.5: Dynamic Settings Tab & Configuration UI** (12/12 tests pass, GUI smoke test pass): `barcode_logic.load_config()` — added `receipt_header_note`/`receipt_footer_note` (default `""`) to both default-config and merge-defaults code paths. `ui_settings_tab.py` — added Receipt Header/Footer Note form fields pre-populated from config; refactored `save_settings()` from unsafe `new_config`-dict replacement to load-modify-write merge preserving `license_key`/`email_report`/`expiry_ignore_list`/future keys; `save_settings()` now calls `_notify_config_updated()` instead of 4 ad-hoc refresh calls. `ui.py` — new `_notify_config_updated()` method modeled on `_notify_inventory_updated()` that broadcasts config changes to inventory/sales/add/receive/dashboard + checkout cart (`_refresh_cart_treeview()` for live tax re-render + `_checkout_update_change()` for Change Due); wired into `on_tab_change` settings branch. `ui_checkout_tab.py` — `_pos_complete_sale()` passes `receipt_header_note`/`receipt_footer_note` through `pharmacy_info`. `receipt_engine.py` — `generate_receipt()` renders header note between pharmacy header and Receipt # line; footer note between "Thank you" and final sep (only when non-empty). `locales/{en,de,es,fr,pt,ar}.json` — added `receipt_header_note`/`receipt_footer_note` keys. `test_settings_phase135.py` — 12 headless tests (config safe-merge, tax validation bounds, receipt rendering, notification wiring). | ✅ Complete |

---

_This document reflects the architectural state as of 2026-08-02. **Phase 8 completed:** Autonomous Crash Reporter + AI Debug Agent (M78). **Phase 2 (ORM) completed:** SQLAlchemy ORM layer with db.py (M79). **Phase 3 (OCR) completed:** 4-tier OCR confidence cascade with Pillow preprocessing and customtkinter UI components (M80). **Phase 4 (Email) completed:** Daily Sales Email System with SQLAlchemy aggregation + async SMTP (M81). **Phase 5 (UI Redesign) completed:** Navigation drawer + TabViewCompat + card layouts across 9 tabs with Phase 3/4 integration (M82). **Phase 6 (Rust Extensions) completed:** PyO3 cdylib crates (`rust_crypto` for Fernet AES-128-CBC+HMAC, `hw_client` for hardware fingerprinting) with `abi3-py38` forward compatibility, graceful Python fallback in `crypto_utils`/`crash_reporter`/`license_gate` (M83). **Phase 7 (Async UI) completed:** Centralized ThreadPoolExecutor with `.after()` marshaling across crash reporter, daily report, excel handler, checkout, and report tabs (M84). **Phase 8 (i18n) completed:** 58 new locale keys in en/ar, all new UI elements refactored to `i18n.t()`, dynamic format strings verified (M85). **Phase 9 (Final Validation) completed:** 24-test integration suite PASS, AsyncUI `reset()` + executor cleanup, `exhaustive_verify.py` 103→105 checks (M86). **Phase 10 (Build & Deployment) completed:** Standalone 10.5 MB executable built with PyInstaller onedir, all Rust .pyd extensions + 6 locale files bundled, runtime smoke test passed, `exhaustive_verify.py` **105/105 PASS — 100% verification** (M87). **Runtime crash fixed:** `design_system.py` — removed auto-`.pack()` from `CascadeStatusBadge.__init__()`/`OCRFeedbackBadge.__init__()`/`OCRProgressBar.__init__()` that caused `TclError` when parent used `.grid()`. Added `.frame` property for caller-controlled layout; updated `ui_dashboard_tab.py`, `ui_checkout_tab.py`, `ui_settings_tab.py` to explicitly place badges via `.grid()`/`.pack()`. Rebuilt executable, runtime smoke test confirmed clean launch (PID 6388, 98 MB, no geometry manager crash). Phase 0 (M52) + Phase 1 (M53-M56) + Phase 2 DB (M57-M62) + Phase 2 ORM (M79) + Phase 2 OCR (M80) + Phase 3 (M63) + Phase 4 (M64-M66, M81) + Phase 5 (M67-M70, M82) + Phase 5b (M83) + Phase 6 (M71-M76) + Phase 6b (M84) + Phase 7 (M77) + Phase 8 (M78) + Phase 8b (M85) + Phase 9 (M86) + Phase 10 (M87) all complete. Remaining: cloud backup (F6), regulatory compliance (F7), enterprise features (F8-F12). See execution roadmap in AGENTS.md._


**RX Workflow Phase 1 completed:** rchive/rx_db.py (ORM models with egional_metadata JSON columns + audit log extensions), rchive/rx_database.py (sqlite3 + _db_fallback pattern with Row factory + FK pragma, prescription CRUD + JSON serialization), rchive/rx_config.py (ConfigManager singleton, unit conversions, regional label registry, Fernet credential encryption), rchive/rx_strategies.py (PharmacyIntegrationStrategy ABC + USBillingStrategy/EUBillingStrategy/MockProvider + strategy_factory), rchive/ui_rx_workflow.py (Custom Fields pattern replicated verbatim from ui_patients_tab.py, prescription CRUD dialog). All files pass py_compile syntax verification.**RX Workflow Phase 1 completed:** archive/rx_db.py (ORM models with regional_metadata JSON columns + audit log extensions), archive/rx_database.py (sqlite3 + _db_fallback pattern with Row factory + FK pragma, prescription CRUD + JSON serialization), archive/rx_config.py (ConfigManager singleton, unit conversions, regional label registry, Fernet credential encryption), archive/rx_strategies.py (PharmacyIntegrationStrategy ABC + US/EU/Mock providers + strategy_factory), archive/ui_rx_workflow.py (Custom Fields pattern replicated verbatim, prescription CRUD dialog). All files pass py_compile syntax verification.
**RX Workflow Phase 2 (Build & Packaging) completed:** archive/build_rx_app.py (PyInstaller automation with hidden imports for cryptography, sqlalchemy, customtkinter), archive/verify_build.py (post-build verification: exe, data files, compilation, imports, spec hidden imports), archive/PharmacyPro_Rx.spec (auto-generated spec), archive/rx_config.json (default region config). 74/74 tests pass across test_rx_config.py, test_rx_database.py, test_rx_strategies.py.

---

## 7. Licensing Backend

### Canonical webhook handler — SINGLE SOURCE OF TRUTH

`backend/app.py` is the **sole** Lemon Squeezy webhook handler in this project. All other
Lemon Squeezy webhook implementations were deleted on 2026-08-06. No additional webhook
receiver may be introduced outside `backend/`.

| File | Purpose | Lines |
|---|---|---|
| `backend/app.py` | Flask app — `POST /webhooks/lemon-squeezy` (HMAC-SHA256 + SQLite persistence) + `POST /api/validate` (hardware binding: 404/403/400/200) + `POST /api/admin/manage` (admin actions: revoke/reset/list with X-Admin-Secret auth) | ~300 |
| `backend/db.py` | SQLite persistence layer — `licenses` table (license_key, customer_email, order_id, status, hardware_id, created_at); `init_db`/`insert_license`/`get_license`/`bind_hardware_id`/`clear_hardware_id`/`update_license_status`/`clear_licenses`/`get_all_licenses`; parameterized queries, `:memory:` test isolation | ~187 |
| `backend/admin.py` | Admin CLI — argparse subcommands: `list` (ASCII table), `revoke <key>`, `reset <key>`, `generate <email>`; importable functions for testing | ~155 |
| `backend/test_webhook_lemon_squeezy.py` | 14 unittest cases (Flask test client) — 6 webhook + 8 validate (success, binding, mismatch, revocation, not-found, missing-fields, invalid-JSON, integration flow) | ~232 |
| `backend/test_admin.py` | 29 unittest cases — 9 CLI tests + 20 API tests (auth, revoke, reset, list, edge cases, end-to-end lifecycle) | ~260 |

**Test result:** 43/43 pass (`python backend/test_webhook_lemon_squeezy.py` → 14/14, `python backend/test_admin.py` → 29/29). In-memory `:memory:` SQLite ensures zero test artifacts on disk.

### Deployment

A `Procfile` at the project root defines the WSGI entry point for standard
WSGI hosts (Heroku/Render/Railway/Fly.io) that bypass `.vercelignore`:

```
web: gunicorn backend.app:app
```

`gunicorn>=23.0,<24.0` is listed in `requirements.txt`. The database file
`backend/license_db.sqlite` is auto-created at import time via `db.init_db()`
and is covered by the `*.sqlite` pattern in `.gitignore`.

### Environment variables — definitive vs deprecated

| Variable | Status | Read by |
|---|---|---|
| `LEMON_SQUEEZEY_SIGNATURE_SECRET` | **DEFINITIVE** — the only variable used for Lemon Squeezy signature verification | `backend/app.py` |
| `ADMIN_SECRET` | **DEFINITIVE** — the only variable used for admin API authentication (`POST /api/admin/manage`). Defaults to `default-dev-secret` if unset. | `backend/app.py` |
| `LEMON_WEBHOOK_SECRET` | **DEPRECATED** — handler deleted | nothing |
| `LEMON_SQUEEZY_WEBHOOK_SECRET` | **DEPRECATED** — handlers deleted; a dormant reference survives in `archive/license_server.py` (non-authoritative) | nothing active |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | **DEPRECATED** — archived documentation only | nothing |

There is **no fallback chain**: if `LEMON_SQUEEZEY_SIGNATURE_SECRET` is unset, `backend/app.py`
returns `500` rather than silently reading a legacy name. Operators must set it in the
`backend/` deployment environment.

> Do **not** add this variable to `.env` or `.env.example` — `archive/exhaustive_verify.py`
> checks 1.9/1.10 fail if the string "Lemon" appears in those files.

**Database:** `backend/license_db.sqlite` (SQLite, auto-initialized at import by
`backend/app.py` via `db.init_db()`). Override at test time with
`db.set_db_path(":memory:")`. The `licenses` table includes a `created_at`
column (auto-populated via `CURRENT_TIMESTAMP` on insert).

**Admin auth:** `POST /api/admin/manage` requires `X-Admin-Secret` header
matching `os.environ.get("ADMIN_SECRET", "default-dev-secret")`. The
`backend/admin.py` CLI tool manages licenses locally against the same
database.

### Removed legacy handlers (2026-08-06)

| Deleted file | What it was | Replaced by |
|---|---|---|
| `api/lemon_webhook.py` | `BaseHTTPRequestHandler`, persisted licenses to Upstash Redis | `backend/app.py` |
| `archive/licensing/api/webhook.py` | Identical duplicate of the above | `backend/app.py` |
| `archive/license_server/api/webhook.py` | Vercel serverless, `PHARM-XXXX-XXXX-XXXX` keygen → Upstash Redis | `backend/app.py` |

None of these were ever deployed: `.vercelignore` excludes `*.py` and `archive/`, so the live
Vercel deployment has only ever served `app/api/webhooks/paddle/route.ts`.

### Other licensing components (non-Lemon-Squeezy)

| Component | Location | Stack | Role |
|---|---|---|---|
| Paddle webhook (live) | `app/api/webhooks/paddle/route.ts` | Next.js route handler | Paddle billing — a different gateway, not a Lemon Squeezy handler |
| License server (Paddle) | `archive/server_app.py` | Flask (PythonAnywhere) | `/api/validate`, `/api/activate`, `/api/create`, `/admin/api/*`, `/api/portal/*` |
| Validate endpoint (M90) | `backend/app.py` | Flask | `POST /api/validate` — license key validation + hardware binding (404/403/400/200) |
| Admin manage endpoint (M91) | `backend/app.py` | Flask | `POST /api/admin/manage` — admin actions (revoke/reset/list) with `X-Admin-Secret` auth (200/401/400/404/500) |
| Admin CLI (M91) | `backend/admin.py` | argparse | Local CLI: `list`, `revoke <key>`, `reset <key>`, `generate <email>` with ASCII table output |
| Desktop license gate | `license_gate.py` | CustomTkinter | Consumer of `/api/validate` + `/api/activate` |
| Local CLI | `hub.py` | argparse | `deploy`, `test-webhook` (Paddle), HWID utilities |

### `archive/` is non-authoritative

Everything under `archive/` is historical reference only — excluded from the Vercel
deployment and not part of the active architecture. Known dormant remnant:
`archive/license_server.py:269` still defines `@app.route("/webhook/lemonsqueezy")` reading
`LEMON_SQUEEZY_WEBHOOK_SECRET`, and `archive/licensing/DEPLOY.md` still describes an
`/api/webhook` Vercel deployment. Neither is deployed, imported, or maintained, and neither
counts as a webhook handler for the purposes of the single-source-of-truth rule above.

---

## 8. Pharmacy Suite Refactor � FastAPI Backend + Next.js Frontend (2026-08-11)

**Status:** M1�M7 implemented and verified. The legacy desktop architecture (sections 1�7 above)
remains the authoritative source for the Tkinter app; this section describes the new web stack layered
on top without modifying locked legacy files.

### Tech Stack
- Backend: FastAPI (0.141), SQLAlchemy 2.0 (async aiosqlite), Pydantic v2, PyJWT, bcrypt,
  structlog; mypy `--strict` passes (28 modules, 0 errors).
- Frontend: Next.js 16 / React 19 (App Router) at repo root; TypeScript `tsc --noEmit` passes (0 errors).
- Orchestration: `run_services.py` (Flask :5000 + FastAPI :8000 + Next.js :3000).

### Architecture
- `backend_fastapi/` (new package): `app/main.py` (lifespan, CORS, uniform error contract, security headers, router registry), `app/core/` (models mirrored from the real `pharmacy.db`; async engine + `StaticPool` in-memory test pool; repositories, `lock_manager.py`), `app/api/` (deps, routers: auth/inventory/pos/license/users/settings), `app/services/` (auth_service, inventory_service [stock_levels aggregate + FIFO + alerts], pos_service [atomic checkout, per-drug locks], seed_service [idempotent default-admin seeding in lifespan]), `app/shared/` (pydantic-settings config, exceptions, security with bcrypt + scrypt lazy-upgrade, schemas, logging).
- `scripts/normalize_inventory.py`: R2 data-integrity pass (canonicalize lot `drug_name` ? `products.name`, orphan-lot reporting).
- Root `app/` (Next.js): `types/contracts.ts` (typed contracts incl. Medicine/Batch/StockLevel), `lib/api.ts` (Axios + 401 refresh + uniform-error interceptors), `stores/authStore.ts` (Zustand with `fetchCurrentUser` + RBAC `hasPermission`), `hooks/useBarcodeScanner.ts` (R3 keyboard-wedge scanner), `hooks/useInventory.ts` (search + filters + stock-levels + permission gates), `app/login/page.tsx`, `app/pos/page.tsx`, `app/license/page.tsx`, `app/dashboard/inventory/page.tsx`.

### System Flow (POS checkout + Inventory Management)
1. Barcode scan (POS page) ? `GET /inventory/medicines/search?q=<barcode>` ? `ProductRead`.
2. Cart staged client-side; `POST /pos/checkout` ? `PosService.process_checkout`.
3. Per-drug `asyncio.Lock` (class-level, shared across requests) acquired in sorted order ? single `session.begin()` txn ? `InventoryService.fifo_deduct` (oldest-expiry lots first) ? `receipts` + `receipt_items` + `sold_items` + `audit_logs` written, receipt number derived as `RCP-{year}-{id:06d}`.
4. On insufficient stock the txn rolls back and returns 400 `insufficient_stock`; unknown drug ? 404 `not_found`.
5. **Inventory (M9):** soft-delete via `products.is_deleted` (idempotent PRAGMA/ALTER migration); medicine CRUD behind `inventory.read`/`inventory.write` RBAC; real-time `GET /stock-levels` aggregate (LEFT JOIN `products` <-> `inventory_extended` on `drug_name`, `expiring_soon_count` subquery); batch lifecycle (`GET/PUT /batches/{id}`, `POST /batches/receives`); shared `lock_manager.acquire_drug_lock` serializes `adjust_batch` <-> `fifo_deduct` RMW.

### Verification Gates (terminal)
- `backend_fastapi: python -m pytest -q` → **99 passed** (92 baseline + 7 new Phase 1 hardening tests). Green.
- `backend_fastapi: python -m mypy app` → **Success: no issues found in 32 source files** (strict).
- Root: `npx tsc --noEmit` → **0 errors** (frontend libs + UI, strict).
- Root: `npx next build` → **Compiled successfully (12/12 pages, exit 0)**. Two non-fatal build-time warnings (`location is not defined`) originate from Next.js 16.2.10's *own* bundled RSC code (`node_modules_next_dist_*`) referencing the browser global `location` during RSC data collection — **not from our code** (zero `location` references in `app/`/`lib/`/`stores/`/`components/`/`hooks/`). R1 mitigations applied: `/` and `/pos` are `force-dynamic` (no static prerender) and the Paddle SDK now loads client-side in `PricingCard`. The warning is a framework prerelease artifact and does not affect the running kiosk (browser provides `location`).

### Phase 1 Backend — DONE (full unified-spec extension)
Implemented in `backend_fastapi/`:
- **Money hardening (1.1):** ORM + DB columns migrated `Float`→`Decimal`/`NUMERIC(10,2)`; Pydantic schemas emit money as **JSON strings**; `PosService` math is `Decimal`-only.
- **Typed stock-state errors → 410 (1.2):** `StockStateError` hierarchy; `InventoryService.fifo_deduct` FEFO + raises the right 410 (over-sell/expired/recalled/missing).
- **Drawer movements (1.3):** `DrawerMovement` model + `POST /api/v1/pos/drawer/movement` with running-balance variance.
- **Server time + cashier attribution (1.4):** `receipts.server_created_at`/`ts_skew_confidence`/`created_by`/`cashier_attribution`; checkout stamps them; `CheckoutResult` exposes them.
- **Read replica + snapshot (1.5):** `build_read_engine()` (`mode=ro`) + `get_read_session()`; `vacuum_snapshot()`; lifespan snapshot loop (6h).
- **Versioned migrations (1.6):** `migrate_schema` via `PRAGMA user_version` (v1→v3), idempotent + crash-safe.
- **Approval tokens (1.7):** `create_approval_token`/`consume_approval_token` + `require_approval_token(scope)`; `POST /api/v1/pos/approve` issues single-use tokens after manager PIN verify.
- **Batched sync (1.8):** `POST /api/v1/sync/push` accepts batch `entries`; client replays via `posStore.flushQueue`.

### Phase 2 Frontend libs — DONE
- `lib/decimalCurrency.ts` (bigint cents, no float), `lib/monetarySchema.ts` (Zod money-string), `lib/db.ts` (IndexedDB), `lib/storagePersist.ts`, `lib/offlineQueue.ts` (Lamport `local_seq` + `client_txn_id`), `lib/offlineCrypto.ts` + `lib/offlineCryptoWorker.ts` (PBKDF2 200k), `lib/syncLock.ts` (3-tier in-memory + BroadcastChannel), `lib/deviceId.ts`, `types/contracts.ts` (money=string + new fields), `lib/api/{pos,sync,approval}.ts`.

### Phase 3 Frontend UI — DONE
- `stores/posStore.ts` (Zustand state machine: per-tab cart, hydration, offline enqueue + replay). Replaced legacy `stores/cartStore.ts` (removed).
- `app/pos/page.tsx` rewritten to decimal-safe POS flow with offline banner.
- `components/ManagerApprovalDialog.tsx`, `OfflineSyncBanner.tsx`, `DiscrepanciesPanel.tsx`, `ShiftCloseDialog.tsx` — wired (drawer movement + shift close gated by manager approval).
- `hooks/useBarcodeScanner.ts` (wedge/serial/manual), `hooks/useHydration.ts`.

### Phase 4 Packaging — DONE
- `next.config.ts` → `output: "standalone"` + security headers.
- `requirements-freeze.txt`, `Caddyfile` (loopback + `tls internal`), `install.ps1` (NSSM, dependency order backend→frontend→caddy), `setup.iss` (Inno), `deployment/policies.json`, `docs/edge_tls.md`, `docs/hardening_calibration.md`, `bin/README.md`.

### Phase 5 Validation — DONE (see gates above)
- End-to-end: offline `checkout` enqueues; `flushQueue` replays via `/api/v1/sync/push` with `client_txn_id` (exact-once) + Lamport `local_seq`.
- Money integrity: no float in pricing path (backend `Decimal`, frontend `bigint` cents).

### ORPHANS & PENDING
- **R4 (frontend tests) — DONE:** added Vitest (`vitest.config.ts`) + `lib/decimalCurrency.test.ts`, `lib/monetarySchema.test.ts`, `stores/posStore.test.ts` (12 tests, all green). Tests caught + fixed two real `decimalCurrency` bugs (negative parsing sign, tax-rate scaling).
- **R5 (standalone boot) — DONE:** `node .next/standalone/server.js` boots (`Ready in 0ms`); `/pos` returns the auth redirect — kiosk bundle runs.
- **R6 (money integrity) — DONE:** grep proves all money columns are `Numeric(10,2)`/`Decimal`; only `ts_skew_confidence` is `Float` (clock-skew, not money); frontend has zero float money math.
- **R7 (doc alignment) — DONE:** `VERIFICATION_CHECKLIST.md` Web/Kiosk section added; `FLOW_LOGIC.md` edge-retail flow added; `REQUIREMENT_MAP.md` created mapping Concerns 1/4/8 + Appendix A.3/B.7/B.8/C.1–C.4 → Verified.
- **R8 (lint) — N/A:** project has no ESLint config/binary and `next lint` is removed in Next 16; effective static gate is `tsc --noEmit` (0) + `next build` (type-checked). Adding ESLint is optional/out-of-scope.
- **R9 (final gate) — DONE:** `pytest` 101 passed · `mypy app` 32 files clean · `tsc --noEmit` 0 · `next build` exit 0 (12/12 pages; 2 benign Next 16.2.10 `location` framework warnings).
- Carried-forward (explicit non-goals): PHI encryption-at-rest on all columns, audit-log append-only/chain, returns workflow, full users CRUD, desktop shell, coverage ≥90%, explicit per-line lot picker (Concern 4 multi-unit).
- Multi-worker distributed locks: `asyncio.Lock` (single-process, `--workers 1`) remains canonical.
