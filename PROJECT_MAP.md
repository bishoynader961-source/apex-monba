# Project Map

> PROJECT STATUS: ARCHITECTURE AUDIT — SERIALIZED TRACKING

> Pharmacy Management & Label Design Suite — desktop application for
> serialized inventory management, data storage, barcode/label generation, and custom label design.
> Auto-generated from the codebase at `E:\my progam pharmacy`.
> Last synced: 2026-07-19

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
    total_amount   REAL NOT NULL,       -- Sum of (quantity × price_at_time) for all items
    payment_method TEXT NOT NULL DEFAULT 'Cash'  -- 'Cash', 'Card', or 'Transfer'
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
├── server_app.py           # Flask license server for PythonAnywhere (/api/validate, /api/activate, /api/create)
├── deploy_to_server.py     # Deployment script: upload server_app.py + reload via PythonAnywhere REST API
├── ui_checkout_tab.py      # Checkout tab: POS cart with qty management + receipts + payment + patient linkage
├── ui_templates_tab.py     # Templates tab: CRUD for product templates
├── ui_patients_tab.py      # Patients CRM tab: search, Treeview, dynamic custom field editor
├── ui_settings_tab.py      # Settings tab: config + RBAC + backup
├── excel_handler.py        # Excel import/export engine using openpyxl (threaded)
├── database.py             # SQLite CRUD operations + analytics + patient CRM
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

### `database.py` — Data Layer (500+ lines)

**Tables:** `products`, `templates`, `sold_items`, `receiving_log`, `receipts`, `receipt_items`, `patients`, `patient_fields`

**Products schema:** `id`, `name`, `price`, `manufacturer_barcode`, `internal_unique_barcode` (UNIQUE), `status`, `expiry_date`, `manufacture_date`, `vendor_name`

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
| `create_receipt(payment_method, items)` | Creates receipt + receipt_items, atomically deducts stock from products. Items: `[{product_name, quantity, price_at_time}]`. Rolls back on insufficient stock. |
| `get_receipts()` | Returns all receipts ordered by most recent first: `[(id, timestamp, total_amount, payment_method)]` |
| `get_receipt_items(receipt_id)` | Returns line items for a receipt: `[(id, receipt_id, product_name, quantity, price_at_time)]` |
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

Checkout & Receipts Flow:
  → setup_checkout_tab() → product dropdown (from get_grouped_products()), cart Treeview, order summary
  → _checkout_add_item() → validates stock availability (considers cart vs DB) → appends to self.cart
  → _refresh_cart_treeview() → rebuilds cart display, updates total + change calculator
  → _checkout_confirm() → create_receipt(payment_method, items):
      → BEGIN TRANSACTION
      → INSERT INTO receipts (timestamp, total_amount, payment_method)
      → FOR EACH item: INSERT INTO receipt_items
      → FOR EACH item: DELETE oldest `quantity` In Stock products by name (FIFO deduction)
      → COMMIT (or ROLLBACK on insufficient stock)
  → _refresh_receipts_history() → get_receipts() → displays past receipts
  → _on_receipt_double_click() → get_receipt_items(receipt_id) → messagebox with line items

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

---

## 10. Dependencies

| Package | Used By | Purpose |
|---|---|---|
| `customtkinter` | `ui.py`, `main.py`, `label_engine/main.py` | GUI framework |
| `python-barcode` | `barcode_logic.py`, `label_engine/canvas_core.py` | Code128 barcode rendering |
| `Pillow` | `barcode_logic.py`, `label_engine/canvas_core.py` | Image composition + element rendering |
| `qrcode` | `label_engine/canvas_core.py` | QR code image generation |
| `sqlite3` | `database.py` | Database (stdlib) |
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
| Deploy `licensing/` to Vercel | Pending manual deployment (see `licensing/DEPLOY.md`) |
| Create Upstash Redis database + set env vars in Vercel | Pending manual setup (see `licensing/DEPLOY.md`) |
| Enable GitHub Pages (source: `licensing/static/` folder on `main` branch) | Pending manual setup |

### Known Orphans

| Item | Detail |
|---|---|
| `receiving_log` entries 1 & 2 | Pre-serialization artifacts (dated 2026-07-14). They lack `barcode` values intentionally to preserve historical accuracy. Entry 1: 50x aspirin from medsupply ($200). Entry 2: 50x bands from medsupply ($100). No referential link to `products` exists and no further action is required. |

### Completed Items

| Milestone | Description | Status |
|---|---|---|
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
| M47 | License Server — Backend (`licensing/api/`: `BaseHTTPRequestHandler` endpoints for activate/validate/webhook. Upstash Redis via REST API. Lemon Squeezy webhook integration.) | ✅ Complete |
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

---

_This document reflects the architectural state as of 2026-07-29. **Phase 7 completed:** Command Center Architecture + Developer Tooling (M77). Phase 0 (M52) + Phase 1 (M53-M56) + Phase 2 (M57-M62) + Phase 3 (M63) + Phase 4 (M64-M66) + Phase 5 (M67-M70) + Phase 6 (M71-M76) + Phase 7 (M77) all complete. Remaining: cloud backup (F6), regulatory compliance (F7), and enterprise features (F8-F12). See execution roadmap in AGENTS.md._
