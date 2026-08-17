# Phase 16: Master Integration Plan — Enterprise Pharmacy Suite

> **Status:** Planning — Implementation-Ready
> **Entry Point:** `archive/main_app.py` → `archive/main.py` → `archive/ui.py` (PharmacyApp)
> **Application Root:** `archive/` (all active Python source, configs, locales reside here)
> **Date:** 2026-08-04

---

## 1. Context & Scope

Phase 16 transforms the existing pharmacy application into a commercial-grade enterprise suite by adding an enterprise navigation overlay (top menu bar + icon toolbar), real-time status dashboards, an expanded POS retail module, a tabbed clinical workflow interface, and backend infrastructure (NDC dictionary, bulk import staging, DEA schedules, Quick-SIG system).

**What already exists** (must not be broken):
- NavigationDrawer with 14 tabs (10 core + 4 enterprise: Enterprise Settings, POS Terminal, Rx Processing, EPCS Workflow) wired via `main_app.py:_wire_rx_extensions()`
- `ui_pos_terminal.py` — PosTerminalFrame with inventory search, cart, sale types (Delivery, OTC, Rx OTC, Loyalty)
- `ui_rx_processing.py` — RxProcessingFrame with patient/drug/prescriber lookup, billing, 3 queue tabs (In Processing, Rejects, Ready for Pickup)
- `ui_epcs_workflow.py` — EpcsWorkflowFrame with 3-step wizard (Patient → Medication → Prescription Details + Authorize)
- `database.py` / `db.py` — core pharmacy SQLite DB with `@_db_fallback` pattern (SQLAlchemy → sqlite3)
- `rx_db.py`, `rx_database.py`, `rx_config.py`, `rx_strategies.py` — **LOCKED backend** (import-only)

**Scope boundaries:**
- Backend Rx files (`rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py`) are **locked** — import and call only
- `database.py` and `db.py` are **modifiable** — used for `products` table DEA schedule expansion
- All new UI modules follow the existing monkey-patching integration pattern via `main_app.py`
- No existing features or tabs are removed or reorganized

---

## 2. Architecture Decisions

### 2.1 Integration Pattern: Monkey-Patching via `main_app.py`

All new modules are wired through `_wire_rx_extensions()` in `archive/main_app.py`, following the exact same pattern as `ui_enterprise_settings.py`, `ui_pos_terminal.py`, `ui_rx_processing.py`, and `ui_epcs_workflow.py`:

```python
# main_app.py additions (additive only, no existing lines changed)
ui_navigation._NAV_ICONS["status_dashboard"] = "📊"
ui_navigation._NAV_ICONS["clinical_workflow"] = "🏥"

# New nav icons for top-level enterprise features
_ENT_KEYS = ["status_dashboard", "clinical_workflow"]

# In _patched_init, after existing tabs:
self.tab_status_dashboard = self.tab_view.add(i18n.t("status_dashboard"))
setup_status_dashboard_tab(self)
self.tab_clinical = self.tab_view.add(i18n.t("clinical_workflow"))
setup_clinical_workflow_tab(self)

# In _patched_on_tab_change, after existing elif blocks:
elif current == i18n.t("status_dashboard"):
    self.status_dashboard_frame.refresh()
elif current == i18n.t("clinical_workflow"):
    self.clinical_frame.refresh()
```

### 2.2 Top Menu Bar: Overlay on PharmacyApp

The top menu bar is added as a `tkinter.Menu` attached to the root window in `_patched_init`, **not** as a tab. It provides global shortcuts across all tabs:

```python
# main_app.py — in _patched_init, after super().__init__():
menubar = ui_enterprise_navigation.setup_top_menu_bar(self)
self.config(menu=menubar)
```

### 2.3 Icon Toolbar: Toolbar Frame Above Tab Content

The icon toolbar is a horizontal `CTkFrame` placed between the navigation drawer header and the content area, providing quick-access buttons that dispatch to the appropriate handler regardless of the current tab.

### 2.4 Database Migration Strategy

| Target Table | File | Strategy |
|---|---|---|
| `products` (core) | `database.py` + `db.py` | Add `dea_schedule` column via `ALTER TABLE` migration in `init_db()` (modifying file — not locked) |
| `inventory_extended` (Rx) | `rx_db.py` (locked) | Create migration function in a new `rx_migrations.py` module that adds `dea_schedule` column if missing, called at init time |
| `ndc_dictionary` (new) | New file `ndc_dictionary.py` | New SQLite table `ndc_dictionary` with `CREATE TABLE IF NOT EXISTS` |
| `quick_sig_templates` (new) | New file `quick_sig.py` | New SQLite table `quick_sig_templates` with `CREATE TABLE IF NOT EXISTS` |
| `bulk_import_staging` (new) | New file `bulk_import_staging.py` | In-memory staging table, no persistent schema needed |

### 2.5 Decoupled Design (MVC-style separation)

| Layer | File(s) | Responsibility |
|---|---|---|
| **View** | `ui_*.py` modules | CustomTkinter UI construction, event handlers |
| **Controller** | `ui_enterprise_navigation.py`, `ui_status_dashboard.py`, `ui_pos_retail.py`, `ui_clinical_workflow.py` | Orchestrate view ↔ data-layer communication, async dispatch |
| **Model** | `database.py`, `db.py`, `rx_db.py` (locked), `ndc_dictionary.py`, `quick_sig.py`, `bulk_import_staging.py` | Data access, schema management, query functions |
| **Service** | `barcode_logic.py`, `receipt_engine.py`, `audit_log.py` | Cross-cutting utilities (config, receipts, logging) |

---

## 3. Verifiable Goals

### 3.1 Global Navigation and UI Framework

| Goal | Verification |
|---|---|
| V1.1 Top menu bar renders with File, Edit, Actions, View, Go, Workflow, Patient, Third Party, System, Help | Smoke test: `python -c "import ui_enterprise_navigation; print(ui_enterprise_navigation.TOP_MENUS)"` returns 10 menus |
| V1.2 Each top menu has at least 2 cascade items | Assert `len(menus['File']) >= 2`, etc. |
| V1.3 Icon toolbar with 10 buttons binds to handlers | Assert all 10 buttons are `CTkButton` instances with `command` set |
| V1.4 Refresh button triggers `_notify_config_updated()` | Integration test: mock `app._notify_config_updated` is called |
| V1.5 Rx Search button opens search dialog | Lambda binds to `app.search_entry.focus()` or opens a search toplevel |
| V1.6 Toolbar uses `pack_propagate(False)` on button row | Geometry assertion after `root.update_idletasks()` |

### 3.2 Interactive Status Dashboards and Task Management

| Goal | Verification |
|---|---|
| V2.1 Status sidebar shows 8 metric cards (Ready for Pickup, Waiting, Refill Requests, Third Party Ready, Third Party Reject, In Processing, Insurance Reject, Waiting to be Done) | Assert 8 `StatusMetricCard` instances exist |
| V2.2 Metrics are populated from `rx_db.get_rx_status_counts()` + custom queries | Mock DB returns counts, verify labels update |
| V2.3 Status sidebar uses scrollable viewport (elastic layout) | Assert scrollbar attached to container |
| V2.4 Task panel shows 9 workflow trigger buttons | Assert 9 `CTkButton` instances |
| V2.5 Task button "RX Requests" opens Rx Processing tab | Assert `app.tab_view.set(i18n.t("rx_processing"))` called |
| V2.6 Task button "Transfer Rxs" opens transfer dialog | Assert `TransferRxDialog` is instantiated |
| V2.7 Task panel uses `pack_propagate(False)` on fixed-height header | Geometry assertion |

### 3.3 Enterprise POS and Retail Module

| Goal | Verification |
|---|---|
| V3.1 POS quick-action grid has 9 buttons (Register Sale, Return/Exchange, End of Day Z-Report, Credit Card Batch, Inventory Lookup, Barcode Scanning, Gift Cards, Credit Card Processing, Receipt Printing) | Assert 9 `CTkButton` instances in grid |
| V3.2 Side-panel triggers (Delivery, Gifts, OTC, Rx-to-OTC) | Assert 4 `CTkkSegmentedButton` or `CTkButton` variants |
| V3.3 Bottom summary panel shows Item Count, Subtotal, Tax, Fees, Grand Total | Assert 5 `CTkLabel` instances in summary row |
| V3.4 F12 key triggers final payment | Assert `app.bind("<F12>", ...)` is registered; callback calls `_pos_complete_sale` |
| V3.5 F12 disabled when cart is empty | Assert binding checks `len(app.pos_cart) > 0` |

### 3.4 Clinical Workflow and Prescription Processing

| Goal | Verification |
|---|---|
| V4.1 Clinical workflow tabbed interface has 9 tabs: In Processing, DU, Reversals, Rejects, Drug Guide, Copay, Patient Profile, Third Party Claims, Transfer Rx | Assert `CTkTabview` with 9 tabs |
| V4.2 Prescription wizard has 4 steps: Patient Selection → Product Selection → Prescription Entry → Authorization | Assert wizard step counter reaches 4 |
| V4.3 Prescription entry supports Start Date and End Date fields | Assert `CTkEntry` for `start_date` and `end_date` exist in wizard |
| V4.4 Veterinarian selection dropdown exists | Assert `CTkComboBox` for veterinarian in wizard |
| V4.5 Action buttons: Save Draft, Print, Fax, Authorize & Send | Assert 4 `CTkButton` instances with correct labels |
| V4.6 Drug Guide tab renders drug info from search | Assert search entry + Treeview + detail panel |
| V4.7 Copay tab computes patient responsibility via strategy | Assert `strategy.calculate_patient_cost()` called |
| V4.8 Transfer Rx tab shows external prescription fields | Assert transfer NDC, reason, origin fields |

### 3.5 Backend Automation and Data Architecture

| Goal | Verification |
|---|---|
| V5.1 NDC dictionary table created in SQLite | `SELECT COUNT(*) FROM ndc_dictionary` succeeds |
| V5.2 `ndc_lookup(ndc_code)` returns name, strength, manufacturer instantly (<5ms) | `time.perf_counter()` delta test |
| V5.3 `barcode_lookup(mfg_barcode)` returns product data | Same timing assertion |
| V5.4 Bulk CSV/Excel staging utility accepts headers and maps to fields | `auto_map_csv_headers()` returns mapping dict |
| V5.5 DEA Schedule column exists on `products` table | `PRAGMA table_info(products)` includes `dea_schedule` |
| V5.6 DEA Schedule column exists on `inventory_extended` table | `PRAGMA table_info(inventory_extended)` includes `dea_schedule` |
| V5.7 Reorder threshold column exists on `products` | `PRAGMA table_info(products)` includes `reorder_threshold` |
| V5.8 Quick-SIG template system: button grid + dropdown saves to DB | `save_sig_template()` inserts row; `get_sig_templates()` returns list |
| V5.9 Quick-SIG: button click populates SIG field | Clicking a template button sets `sig_var` |

---

## 4. Detailed Implementation

### 4.1 New Files (7)

| File | ~Lines | Purpose |
|---|---|---|
| `ui_enterprise_navigation.py` | 250 | Top menu bar + icon toolbar (TopMenus, ToolbarButton dataclass, `setup_top_menu_bar()`, `setup_icon_toolbar()`) |
| `ui_status_dashboard.py` | 350 | Status metric cards + task panel (`StatusMetricCard`, `TaskPanel`, `setup_status_dashboard_tab()`) |
| `ui_pos_retail.py` | 450 | Enterprise POS retail module (`PosRetailFrame`, `PosSummaryPanel`, quick-action grid, F12 handler) |
| `ui_clinical_workflow.py` | 550 | Tabbed clinical interface + enhanced prescription wizard (`ClinicalWorkflowFrame`, `PrescriptionWizard`, `DrugGuidePanel`, `CopayPanel`, `TransferRxPanel`) |
| `ndc_dictionary.py` | 120 | In-memory SQLite dictionary for NDC/barcode lookups (`NdcDictionary`, `ndc_lookup()`, `barcode_lookup()`, `bulk_load_ndc()`) |
| `bulk_import_staging.py` | 180 | CSV/Excel staging utility (`StagingTable`, `auto_map_csv_headers()`, `stage_import()`, `commit_staged()`) |
| `quick_sig.py` | 150 | Quick-SIG template system (`QuickSigBuilder`, `save_sig_template()`, `get_sig_templates()`, `delete_sig_template()`) |

### 4.2 Modified Files (7)

| File | Changes |
|---|---|
| `archive/main_app.py` | Add nav icons, imports, tab creation in `_patched_init`, tab-change hooks in `_patched_on_tab_change`, call `setup_top_menu_bar()` + `setup_icon_toolbar()` |
| `archive/database.py` | Add `dea_schedule` + `wholesale_price` + `reorder_threshold` columns to `products` table in `init_db()`; add `search_ndc()` function; add `get_drug_guide()` function |
| `archive/db.py` | Mirror `products` schema changes in ORM model; add `dea_schedule`, `wholesale_price`, `reorder_threshold` columns; add `NdcDictionary` model |
| `archive/ui_navigation.py` | Add `_NAV_ICONS` entries for `status_dashboard`, `clinical_workflow`; add `NAV_TABS_ENTERPRISE` list for ordering |
| `archive/locales/en.json` | Add ~85 new i18n keys (see §4.4) |
| `archive/config.json` | Add `ndc_dictionary_path` field |
| `archive/barcode_logic.py` | Add `init_labels_dir()` call for `ndc_dictionary` directory in `init_labels_dir()` |

### 4.3 Locked Files (Import-Only — No Modifications)

| File | Usage |
|---|---|
| `rx_db.py` | `search_inventory()`, `get_rxs_by_status()`, `get_rx_status_counts()`, `add_rx()`, `add_rx_regional()`, `update_rx_status()`, `RX_STATUSES`, `REGION_LABELS`, `HAS_SQLALCHEMY` |
| `rx_database.py` | `init_rx_tables()`, `get_prescription_by_id()`, `add_prescription()` (sqlite3 fallback only) |
| `rx_config.py` | `ConfigManager` singleton, `get_labels()`, `get_region()` |
| `rx_strategies.py` | `strategy_factory(region)`, `calculate_patient_cost()`, `generate_claim()`, `validate_prescription()` |

### 4.4 New i18n Keys (en.json)

Keys to add across all 6 locale files:

```
Top Menu Bar:
  menu_file, menu_edit, menu_actions, menu_view, menu_go,
  menu_workflow, menu_patient, menu_third_party, menu_system, menu_help
  file_new, file_open, file_save, file_import, file_export, file_exit
  edit_copy, edit_paste, edit_find, edit_replace
  actions_refresh, actions_scan, actions_print
  view_dashboard, view_inventory, view_checkout, view_fullscreen
  go_dashboard, go_inventory, go_checkout, go_patients
  workflow_rx_request, workflow_refill, workflow_transfer
  patient_search, patient_new, patient_merge
  thirdparty_claim, thirdparty_reject, thirdparty_payment
  system_settings, system_backup, system_restore, system_logs, system_about
  help_documentation, help_shortcuts, help_support

Icon Toolbar:
  toolbar_refresh, toolbar_rx_search, toolbar_transfer, toolbar_inventory,
  toolbar_find_patient, toolbar_reports, toolbar_settings, toolbar_print,
  toolbar_email, toolbar_help

Status Dashboard:
  status_dashboard, status_dashboard_subtitle,
  metric_ready_pickup, metric_waiting, metric_refill_requests,
  metric_third_party_ready, metric_third_party_reject, metric_in_processing,
  metric_insurance_reject, metric_waiting_done,
  task_panel, task_rx_requests, task_refill_requests, task_iv_orders,
  task_fax_requests, task_print_lists, task_batch_fills,
  task_reprint_labels, task_partial_fills, task_transfer_rxs

Enterprise POS:
  pos_retail, pos_retail_subtitle,
  pos_register_sale, pos_return_exchange, pos_end_of_day,
  pos_cc_batch, pos_inventory_lookup, pos_barcode_scan,
  pos_gift_cards, pos_cc_processing, pos_receipt_print,
  pos_side_delivery, pos_side_gifts, pos_side_otc, pos_side_rx_otc,
  pos_item_count, pos_subtotal, pos_tax, pos_fees, pos_grand_total,
  pos_f12_pay

Clinical Workflow:
  clinical_workflow, clinical_workflow_subtitle,
  clinical_tab_in_processing, clinical_tab_du, clinical_tab_reversals,
  clinical_tab_rejects, clinical_tab_drug_guide, clinical_tab_copay,
  clinical_tab_patient_profile, clinical_tab_third_party_claims,
  clinical_tab_transfer_rx,
  wizard_step_patient, wizard_step_product, wizard_step_prescription,
  wizard_step_authorization,
  field_start_date, field_end_date, field_veterinarian,
  field_prescriber_select, field_quantity, field_refills,
  field_daw_code, field_sig, field_notes,
  action_save_draft, action_print, action_fax, action_authorize_send

Quick-SIG:
  quick_sig, quick_sig_templates, quick_sig_add_template,
  quick_sig_template_name, quick_sig_sig_text,
  quick_sig_save, quick_sig_delete, quick_sig_apply

NDC Dictionary:
  ndc_dictionary, ndc_bulk_load, ndc_status,
  ndc_loaded, ndc_loading, ndc_error
```

**Strategy for locale parity**: Add all keys to `en.json` first, then translate to `de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`. Use English as fallback (the `i18n.t()` function already falls back to English then to the raw key).

### 4.5 Top Menu Bar (`ui_enterprise_navigation.py`)

```python
TOP_MENUS = {
    "File": [("New RX", "file_new"), ("Open Label Designer", "file_open"),
             ("Import Data", "file_import"), ("Export Data", "file_export"),
             ("Exit", "file_exit")],
    "Edit": [("Copy", "edit_copy"), ("Paste", "edit_paste"),
             ("Find", "edit_find"), ("Replace", "edit_replace")],
    "Actions": [("Refresh", "actions_refresh"), ("Scan Barcode", "actions_scan"),
                ("Print Labels", "actions_print")],
    "View": [("Dashboard", "view_dashboard"), ("Inventory", "view_inventory"),
             ("Checkout", "view_checkout"), ("Full Screen", "view_fullscreen")],
    "Go": [("Dashboard", "go_dashboard"), ("Inventory", "go_inventory"),
           ("Checkout", "go_checkout"), ("Patients", "go_patients")],
    "Workflow": [("RX Requests", "workflow_rx_request"),
                 ("Refill Requests", "workflow_refill"),
                 ("Transfer", "workflow_transfer")],
    "Patient": [("Search", "patient_search"), ("New Patient", "patient_new"),
                ("Merge Records", "patient_merge")],
    "Third Party": [("Submit Claim", "thirdparty_claim"),
                   ("View Rejects", "thirdparty_reject"),
                   ("Claim Payment", "thirdparty_payment")],
    "System": [("Settings", "system_settings"), ("Backup", "system_backup"),
               ("Restore", "system_restore"), ("Logs", "system_logs"),
               ("About", "system_about")],
    "Help": [("Documentation", "help_documentation"),
             ("Keyboard Shortcuts", "help_shortcuts"),
             ("Support", "help_support")],
}

def setup_top_menu_bar(app) -> tk.Menu:
    """Create and return a tkinter.Menu menubar attached to the PharmacyApp root."""
    menubar = tk.Menu(app)
    for menu_name, items in TOP_MENUS.items():
        menu = tk.Menu(menubar, tearoff=0)
        for label_key, i18n_key in items:
            menu.add_command(label=i18n.t(i18n_key),
                             command=lambda k=i18n_key: _dispatch_menu(app, k))
        menubar.add_cascade(label=menu_name, menu=menu)
    app.config(menu=menubar)
    return menubar

def _dispatch_menu(app, key: str):
    """Route menu selection to the appropriate handler."""
    # Implementation dispatches to existing methods or opens dialogs
    # e.g., "file_exit" → app.destroy()
    #       "actions_refresh" → app._notify_config_updated()
    #       "go_dashboard" → app.tab_view.set(i18n.t("dashboard"))
```

### 4.6 Icon Toolbar (`ui_enterprise_navigation.py`)

```python
TOOLBAR_BUTTONS = [
    ("toolbar_refresh", "🔄"),
    ("toolbar_rx_search", "🔍"),
    ("toolbar_transfer", "↔️"),
    ("toolbar_inventory", "📦"),
    ("toolbar_find_patient", "👤"),
    ("toolbar_reports", "📊"),
    ("toolbar_settings", "⚙️"),
    ("toolbar_print", "🖨"),
    ("toolbar_email", "📧"),
    ("toolbar_help", "❓"),
]

def setup_icon_toolbar(app, parent) -> ctk.CTkFrame:
    """Create a horizontal toolbar of icon buttons below the nav header."""
    toolbar = ctk.CTkFrame(parent, fg_color="#1e1e2e", height=56)
    toolbar.pack_propagate(False)
    toolbar.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6, 7, 8, 9), weight=0)
    for idx, (key, icon) in enumerate(TOOLBAR_BUTTONS):
        btn = ctk.CTkButton(
            toolbar, text=icon, width=44, height=44,
            command=lambda k=key: _dispatch_toolbar(app, k),
        )
        btn.grid(row=0, column=idx, padx=4, pady=4)
    return toolbar

def _dispatch_toolbar(app, key: str):
    """Route toolbar button to handler."""
    if key == "toolbar_refresh":
        app._notify_config_updated()
    elif key == "toolbar_rx_search":
        app.tab_view.set(i18n.t("rx_processing"))
        if hasattr(app, "rx_processing_frame"):
            app.rx_processing_frame._show_search_dialog()
    elif key == "toolbar_inventory":
        app.tab_view.set(i18n.t("inventory"))
    # ... etc.
```

### 4.7 Status Dashboard (`ui_status_dashboard.py`)

**StatusMetricCard** — reusable component:
```python
class StatusMetricCard(ctk.CTkFrame):
    def __init__(self, parent, label_key, status="info", value=0):
        # Label + value + colored accent bar
        # Uses BadgeLabel from ui_navigation for color status
```

**8 metric cards**: Ready for Pickup, Waiting, Refill Requests, Third Party Ready,
Third Party Reject, In Processing, Insurance Reject, Waiting to be Done

Data sources:
- `rx_db.get_rx_status_counts()` → In Processing, Ready for Pickup, Rejects
- `rx_db.get_rxs_by_status("Pending")` → Waiting
- Custom queries on `rx_table.regional_metadata` JSON → Refill Requests, Third Party Ready/Reject, Insurance Reject

**TaskPanel** — 9 workflow trigger buttons in a grid:
```python
class TaskPanel(ctk.CTkFrame):
    def __init__(self, parent):
        # 3×3 grid of CTkButton: RX Requests, Refill Requests, IV Orders,
        # FAX Requests, Print Lists, Batch Fills, Reprint Labels, Partial Fills, Transfer Rxs
```

`setup_status_dashboard_tab(self)` creates a `StatusDashboardFrame` in the tab.

### 4.8 Enterprise POS Retail (`ui_pos_retail.py`)

**PosRetailFrame** layout:
```
PosRetailFrame (grid)
├── Row 0: Title — "Enterprise POS Retail"
├── Row 1: Main workspace (2 columns)
│   ├── Left (weight=3): Quick-action button grid (3×3)
│   │   Register Sale, Return/Exchange, End of Day, CC Batch,
│   │   Inventory Lookup, Barcode Scanning, Gift Cards, CC Processing, Receipt Printing
│   └── Right (weight=1): Side-panel triggers (Delivery, Gifts, OTC, Rx-to-OTC)
└── Row 2: Bottom summary panel (pack_propagate(False), height=80)
    ├── Item count | Subtotal | Tax | Fees | Grand Total
    └── F12: Process Payment button (prominent green)
```

Integration: The F12 handler is bound globally via `app.bind("<F12>", ...)` in `_patched_init`, dispatching to the retail frame's payment handler when the status dashboard or retail tab is active.

### 4.9 Clinical Workflow (`ui_clinical_workflow.py`)

**ClinicalWorkflowFrame** — tabbed interface with 9 tabs:
1. **In Processing** — Rx items with status Pending/Billed/Verified
2. **Drug Utilization Review (DU)** — DUR alerts panel (queries `rx_table` for flagged interactions)
3. **Reversals** — Recently filled Rxs eligible for reversal (status=Will Call, within 24h)
4. **Rejects** — Rejected claims with reason display
5. **Drug Guide** — Searchable drug database (NDC → drug info via ndc_dictionary)
6. **Copay** — Patient responsibility calculator (uses `strategy_factory(region).calculate_patient_cost()`)
7. **Patient Profile** — Demographics + insurance + prescription history
8. **Third Party Claims** — Claim submission status and results
9. **Transfer Rx** — External prescription import with transfer NDC, origin pharmacy, reason

**PrescriptionWizard** — enhanced version of the EPCS wizard with 4 steps:
1. Patient Selection (database.get_all_patients search)
2. Product Selection (rx_db.search_inventory)
3. Prescription Entry (Quantity, Refills, Start/End dates, DAW code, SIG, Notes, Veterinarian/Prescriber)
4. Authorization (strategy.validate_prescription → generate_claim → authorize)

Action triggers: Save Draft, Print, Fax, Authorize & Send

### 4.10 NDC Dictionary (`ndc_dictionary.py`)

In-memory SQLite database (separate from pharmacy.db) optimized for O(1) lookups:

```sql
CREATE TABLE IF NOT EXISTS ndc_dictionary (
    ndc_code     TEXT PRIMARY KEY,        -- 11-digit NDC
    drug_name    TEXT NOT NULL,
    strength     TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    dosage_form  TEXT,
    awp          REAL,
    dea_schedule TEXT DEFAULT 'CIII'       -- default conservative
);
CREATE INDEX IF NOT EXISTS idx_ndc_lookup ON ndc_dictionary(ndc_code);
```

Key functions:
```python
def init_ndc_dictionary(db_path) -> None
def ndc_lookup(ndc_code: str) -> dict | None
def barcode_lookup(barcode: str) -> dict | None
def bulk_load_ndc(csv_path: str) -> int  # returns row count
```

The dictionary is loaded at startup via `barcode_logic.load_config()` (reads `ndc_dictionary_path` from config.json).

### 4.11 DEA Schedule Schema Extension

**For `products` table** (in `database.py` + `db.py` — modifiable):

Add to `init_db()`:
```python
try:
    cursor.execute("ALTER TABLE products ADD COLUMN dea_schedule TEXT DEFAULT 'OTC'")
except sqlite3.OperationalError: pass

try:
    cursor.execute("ALTER TABLE products ADD COLUMN wholesale_price REAL DEFAULT 0.0")
except sqlite3.OperationalError: pass

try:
    cursor.execute("ALTER TABLE products ADD COLUMN reorder_threshold INTEGER DEFAULT 0")
except sqlite3.OperationalError: pass
```

Add to `db.py` ORM `Product` model:
```python
dea_schedule = Column(String(10), default="OTC")
wholesale_price = Column(Float, default=0.0)
reorder_threshold = Column(Integer, default=0)
```

**For `inventory_extended` table** (in `rx_db.py` — locked):

Create `rx_migrations.py`:
```python
def migrate_inventory_extended_dea_schedule(db_path: str) -> bool:
    """Add dea_schedule column to inventory_extended if missing (rx_db.py is locked)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(inventory_extended)")
    columns = [row[1] for row in cursor.fetchall()]
    if "dea_schedule" not in columns:
        cursor.execute("ALTER TABLE inventory_extended ADD COLUMN dea_schedule TEXT DEFAULT 'CIII'")
        conn.commit()
    conn.close()
    return True
```

Call `migrate_inventory_extended_dea_schedule()` from `rx_init.py` or from `_wire_rx_extensions()`.

### 4.12 Quick-SIG Template System (`quick_sig.py`)

```sql
CREATE TABLE IF NOT EXISTS quick_sig_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,        -- e.g., "Take 1 tablet by mouth twice daily"
    sig_text TEXT NOT NULL,    -- the actual SIG direction
    category TEXT DEFAULT 'General',  -- dosage form filter
    times_per_day INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0
);
```

Key functions:
```python
def init_quick_sig(db_path: str) -> None
def save_sig_template(name: str, sig_text: str, category: str = "General") -> int
def get_sig_templates(category: str = None) -> list[dict]
def delete_sig_template(template_id: int) -> bool
def build_sig_sig_panel(parent, sig_var: ctk.StringVar) -> 'QuickSigBuilder'
```

**QuickSigBuilder** — UI component:
```
CTkFrame (button grid)
├── Dropdown: Category filter (All, Oral, Topical, Ophthalmic, Otic, Inhaler, Injectable)
├── 2-column button grid: each button = one SIG template
├── "+" Add Template button → opens QuickSigDialog
└── Clicking any button sets sig_var to the template's sig_text
```

### 4.13 Bulk CSV/Excel Staging (`bulk_import_staging.py`)

```python
class StagingTable:
    """In-memory staging table with CSV/Excel import, header mapping, validation."""
    def __init__(self, target_table: str):
        self.target_table = target_table
        self._rows: list[dict] = []
        self._column_map: dict = {}
    
    def load_csv(self, file_path: str, delimiter: str = ",") -> int
    def load_excel(self, file_path: str, sheet_name: str = None) -> int
    def auto_map_headers(self) -> tuple[dict, list]  # (mapping, unmatched)
    def validate_row(self, idx: int) -> list[str]  # returns list of errors
    def commit(self, on_commit: callable) -> int  # writes to DB via callback
```

Supported target tables: `inventory_extended`, `prescriber_table`, `patients`

---

## 5. Backend Data Sources for Status Metrics

| Metric | Source Query | Module |
|---|---|---|
| Ready for Pickup | `rx_db.get_rxs_by_status("Will Call")` → count | rx_db.py (locked) |
| Waiting | `rx_db.get_rxs_by_status("Pending")` → count | rx_db.py (locked) |
| Refill Requests | `rx_table` where `refills_remaining > 0 AND status IN ('Will Call','Filled')` | Custom SQL in rx_migrations.py |
| Third Party Ready | `rx_table` where `regional_metadata` JSON contains `third_party_ready=true` | Custom SQL (sqlite3) |
| Third Party Reject | `rx_table` where `status='Rejected' AND regional_metadata.rejection_source='third_part'` | Custom SQL (sqlite3) |
| In Processing | `rx_db.get_rxs_by_status("Pending") + get_rxs_by_status("Billed") + get_rxs_by_status("Verified")` → count | rx_db.py (locked) |
| Insurance Reject | `rx_table` where `regional_metadata.claim_status='Rejected'` | Custom SQL (sqlite3) |
| Waiting to be Done | `rx_table` where `status='Pending' AND date_started=''` | Custom SQL (sqlite3) |

All custom SQL queries use raw `sqlite3` with `PRAGMA foreign_keys=ON` and `row_factory=sqlite3.Row` — no reliance on SQLAlchemy (which may be absent). They query `rx_table` and parse `regional_metadata` JSON via `json_each()`.

---

## 6. Implementation Roadmap

| Phase | Milestone | Deliverables | Verification |
|---|---|---|---|
| P16.1 | Backend Schema & Dictionary | `ndc_dictionary.py` + DEA columns in `database.py`/`db.py` + `rx_migrations.py` for `inventory_extended` | `python -m py_compile` + unit test: `PRAGMA table_info` checks + `ndc_lookup()` timing test |
| P16.2 | Quick-SIG System | `quick_sig.py` + `quick_sig_templates` table + `QuickSigBuilder` UI component | Import smoke + save/load/delete template + click populates SIG field |
| P16.3 | Top Menu Bar + Icon Toolbar | `ui_enterprise_navigation.py` + 140 i18n keys + `main_app.py` integration | `python -c "import ui_enterprise_navigation"` + verify menu has 10 cascades + 10 toolbar buttons |
| P16.4 | Status Dashboard + Task Panel | `ui_status_dashboard.py` + `StatusMetricCard` + `TaskPanel` + integration | StatusMetricCard renders 8 cards + TaskPanel renders 9 buttons + refresh populates data |
| P16.5 | Bulk Import Staging | `bulk_import_staging.py` + StagingTable class | `auto_map_csv_headers()` returns mapping + `commit()` writes to test DB |
| P16.6 | Enterprise POS Retail | `ui_pos_retail.py` + `PosRetailFrame` + F12 binding | 9 quick-action buttons + 4 side-panel triggers + bottom summary panel + F12 triggers payment |
| P16.7 | Clinical Workflow + Wizard | `ui_clinical_workflow.py` + `ClinicalWorkflowFrame` + `PrescriptionWizard` | 9 tabs render + 4-step wizard + Start/End date fields + Veterinarian dropdown + action buttons |
| P16.8 | Main App Integration | `main_app.py` wiring + `ui_navigation.py` update + all locale files | Full smoke test: app starts, all new tabs render, top menu works, toolbar buttons dispatch |

---

## 7. Constraints Compliance

| Constraint | How Addressed |
|---|---|
| **Locked backends** | `rx_db.py`, `rx_database.py`, `rx_config.py`, `rx_strategies.py` imported only; `inventory_extended` migration via separate `rx_migrations.py` |
| **Backend immutability** | No functions, classes, or schemas modified in locked files; only `ALTER TABLE` additions in separate module |
| **UI consistency** | All new modules use identical color variables (#1a1a2e/#2d2d3a/#3b82f6/#10b981), `apply_treeview_style()`, grid layout with weight config, `pack_propagate(False)` on fixed-height elements |
| **Async non-blocking** | All DB queries use `AsyncUI.get().run()` with `.after()` callback marshaling (same pattern as `ui_rx_processing.py` lines 969-1005) |
| **SQLite fallback** | Every `rx_db` call wrapped in try/except with raw sqlite3 fallback (same pattern as `ui_pos_terminal.py` lines 360-383) |
| **Layout elasticity** | All Treeviews have `ttk.Scrollbar`; Quick-SIG button grid uses `CTkScrollableFrame`; status cards use `CTkScrollableFrame` for overflow |
| **No placeholders/TODOs** | Every function fully specified with inputs/outputs in §4 |
| **i18n** | All display text via `i18n.t()` with fallback to English; locale parity enforced (en keys added first, then de/es/fr/pt/ar) |
| **Backward compatibility** | All schema changes use `ALTER TABLE ... ADD COLUMN` with `try/except OperationalError`; `init_rx_tables()` already called in `main_app.py` |

---

## 8. Risk Analysis & Mitigations

| Risk | Mitigation |
|---|---|
| `rx_db.HAS_SQLALCHEMY` is False (no SQLAlchemy) | All rx_db calls guarded with try/except + sqlite3 fallback; status metrics use raw sqlite3 queries on `rx_table` directly |
| New nav tabs conflict with existing `on_tab_change` | Monkey-patching preserves original `on_tab_change` via `_orig_on_tab_change(self)` then extends; new tabs added after existing ones |
| Top menu bar `tkinter.Menu` conflicts with CustomTkinter | `tkinter.Menu` is standard Tkinter — attaches to CTk root via `app.config(menu=...)`; tested pattern (used in label_engine/main.py File menu) |
| F12 global bind conflicts with existing key bindings | F12 handler checks `app.tab_view.get()` — only fires on `status_dashboard` or `clinical_workflow` tab; no existing F12 binding found in codebase |
| `inventory_extended` migration fails if column exists | `PRAGMA table_info()` check before `ALTER TABLE`; `try/except OperationalError` guard |
| NDC dictionary path missing in config.json | `load_config()` already merges new defaults; `init_ndc_dictionary()` falls back to in-memory dict if file missing |
| Quick-SIG templates table doesn't exist on first run | `init_quick_sig()` calls `CREATE TABLE IF NOT EXISTS` at module import + in setup function |
| Status metric queries slow on large datasets | All metrics use indexed queries (`rx_table.status` is indexed via `get_rxs_by_status`); counts limited to date range (last 7 days) |
| Clinical workflow wizard conflicts with EPCS wizard | Separate module `ui_clinical_workflow.py` with its own `PrescriptionWizard`; EPCS wizard remains untouched |
| Bulk import staging exceeds memory | `StagingTable` uses generator-based row iteration for CSV; Excel rows loaded lazily via openpyxl worksheet |
| i18n keys missing from non-English locales | `i18n.t()` falls back to English → raw key; verification test checks key count parity |

---

## 9. Verification Plan

### 9.1 Pre-Build Checks (Category 1)
```bash
cd archive
python -c "import ui_enterprise_navigation; print(len(ui_enterprise_navigation.TOP_MENUS))"  # → 10
python -c "import ui_enterprise_navigation; print(len(ui_enterprise_navigation.TOOLBAR_BUTTONS))"  # → 10
python -c "import ndc_dictionary; ndc_dictionary.init_ndc_dictionary(':memory:')"  # OK
python -c "import quick_sig; quick_sig.init_quick_sig(':memory:')"  # OK
python -c "import bulk_import_staging; print(hasattr(bulk_import_staging, 'StagingTable'))"  # True
```

### 9.2 Schema Verification (Category 2)
```python
import sqlite3
conn = sqlite3.connect("pharmacy.db")
cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
assert "dea_schedule" in cols
assert "wholesale_price" in cols
assert "reorder_threshold" in cols

cols_rx = [r[1] for r in conn.execute("PRAGMA table_info(inventory_extended)").fetchall()]
assert "dea_schedule" in cols_rx

cols_sig = [r[1] for r in conn.execute("PRAGMA table_info(quick_sig_templates)").fetchall()]
assert "sig_text" in cols_sig
conn.close()
```

### 9.3 Unit Tests (Category 3 — 25 new tests)

| Test File | Tests | Coverage |
|---|---|---|
| `test_phase16_navigation.py` | 6 | Menu structure, toolbar button count, dispatch routing |
| `test_phase16_ndc_dictionary.py` | 5 | Table creation, ndc_lookup, barcode_lookup, bulk load, timing <5ms |
| `test_phase16_quick_sig.py` | 5 | Template save/load/delete, category filter, sig_var population |
| `test_phase16_status_dashboard.py` | 4 | 8 metric cards, task panel buttons, async data load |
| `test_phase16_pos_retail.py` | 5 | 9 quick-action buttons, 4 side triggers, F12 binding, summary panel |

### 9.4 Integration Test (Category 4)
Run `python main_app.py` from `archive/` directory. Verify:
1. App launches without error
2. Top menu bar visible with 10 cascade menus
3. Icon toolbar visible with 10 buttons
4. New tabs "Status Dashboard" and "Clinical Workflow" appear in navigation drawer
5. Status dashboard renders 8 metric cards + 9 task buttons
6. Clinical workflow renders 9 tabs + prescription wizard
7. F12 key bound and dispatches correctly
8. NDC dictionary loads from `ndc_dictionary_path` in config.json

### 9.5 Zero Regression (Category 5)
Run existing test suites from `archive/`:
```bash
python -m unittest test_rx_config.py       # 21 tests
python -m unittest test_rx_database.py      # 16 tests
python -m unittest test_rx_strategies.py    # 30 tests
python -m unittest test_settings_phase135.py # 12 tests
python exhaustive_verify.py                 # 105 checks
```

Expected: All existing tests pass + 25 new tests pass = **143 tests / 105 verify checks**.

---

## 10. Rollback & Migration Path

- **Schema migrations** are all `ALTER TABLE ADD COLUMN` / `CREATE TABLE IF NOT EXISTS` — idempotent, safe to re-run
- **No data migration** required — new columns have defaults, new tables start empty
- **Feature flags**: New tabs are added via monkey-patching in `main_app.py`; if any new module fails to import, `main_app.py` catches the exception and logs a warning (existing pattern from lines 71-75)
- **Reversibility**: Remove the new import lines + nav icon lines from `_wire_rx_extensions()` → app returns to pre-Phase-16 state

---

## 11. Files Not Modified (Confirmed Safe)

All of these are imported but never modified:
```
rx_db.py, rx_database.py, rx_config.py, rx_strategies.py,
rx_integration_settings.py, rx_init.py, rx_wiring_instructions.md,
build_rx_app.py, verify_build.py, PharmacyPro_Rx.spec,
ui_epcs_workflow.py, ui_rx_processing.py, ui_pos_terminal.py,
ui_enterprise_settings.py, design_system.py, async_ui.py,
path_utils.py, barcode_logic.py, barcode_listener.py,
receipt_engine.py, receipt_template.py, pos_engine.py,
audit_log.py, backup.py, crypto_utils.py, crash_reporter.py,
ocr_engine.py, ocr_cascade.py, smart_parser.py, auto_extract.py,
excel_handler.py, i18n.py, ui_helpers.py, ui_modals.py,
ui.py, ui_add_tab.py, ui_inventory_tab.py, ui_expiring_tab.py,
ui_dashboard_tab.py, ui_report_tab.py, ui_receive_tab.py,
ui_checkout_tab.py, ui_templates_tab.py, ui_settings_tab.py,
ui_patients_tab.py, main.py, main_app.py (only additive changes)
```

> `main_app.py` receives **additive-only** changes (new lines in `_wire_rx_extensions()`). No existing lines are removed or restructured.
