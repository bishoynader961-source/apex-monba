# CustomTkinter App - Master Architecture & Refinement Blueprint

## 1. System Overview
*   **UI Framework:** CustomTkinter 5.2+ / Tkinter (Python 3.10+)
*   **Database:** SQLite 3 (via SQLAlchemy 2.0 ORM) — **Single Layer Mandatory**
*   **Threading Strategy:** `concurrent.futures.ThreadPoolExecutor` with `root.after()` callbacks for UI updates
*   **Packaging Target:** PyInstaller `.spec` → MSIX Installer (Microsoft Store)
*   **License Model:** Store build bypasses hardware/RSA activation; Enterprise build uses `license_gate.py`

## 2. Codebase Map (Exact Module Paths)

### 2.1 Main Window & Navigation
| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `archive/main.py` | Primary entry point; crash reporter, i18n, license gate, DB init | `main()` |
| `archive/main_app.py` | Extended entry with RBAC startup gate, monkey-patches enterprise tabs | `main()`, `_wire_rx_extensions()`, `_wire_rbac()` |
| `archive/ui.py` | **God Class** `PharmacyApp(ctk.CTk)` — 633 lines, 150+ monkey-patched methods | `PharmacyApp`, tab setup/load methods |
| `archive/ui_navigation.py` | `NavigationDrawer` + `TabViewCompat` shim (drop-in CTkTabview replacement) | `create_navigation_system()`, `NavigationDrawer`, `TabViewCompat`, `_NAV_ICONS`, `NAV_PERMISSIONS` |

### 2.2 Database Layer (Dual — MUST CONSOLIDATE)
| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `archive/database.py` | Raw SQLite with `_db_fallback` decorator delegating to `db.py` | `init_db()`, `get_db_path()`, `add_product()`, `get_all_products()`, `mark_item_as_sold()`, RBAC functions (50+) |
| `archive/db.py` | SQLAlchemy 2.0 ORM + raw SQL fallbacks; SQLite & PostgreSQL | `init_db()`, `get_session()`, `reconnect_db()`, ORM models (`Product`, `Receipt`, `Patient`, `Supplier`, `PurchaseOrder`, `Role`, `User`, `Permission`), 50+ query functions |
| `archive/path_utils.py` | Runtime path resolution (`sys._MEIPASS` compatible) | `get_resource_path()`, `ensure_runtime_directories()`, `get_writable_config_path()` |

### 2.3 UI Views & Controllers (26 Modules)

#### POS / Checkout
*   `archive/ui_checkout_tab.py` — Checkout cart, patient selection, payment, receipt printing
*   `archive/ui_pos_terminal.py` — Enterprise POS terminal (monkey-patched via `main_app.py`)
*   `archive/ui_pos_retail.py` — Enterprise POS Retail with insurance panel
*   `archive/ui_pos_panels.py` — Reusable POS panel components

#### Inventory / Data Management
*   `archive/ui_inventory_tab.py` — Main inventory grid, search, batch editing, label printing
*   `archive/ui_inventory_management.py` — Enterprise inventory management tab
*   `archive/ui_receive_tab.py` — Purchase order receiving, vendor management, AI invoice parsing
*   `archive/ui_expiring_tab.py` — Expiring soon dashboard with vendor summaries

#### Reports / Analytics
*   `archive/ui_dashboard_tab.py` — Main dashboard with metrics cards
*   `archive/ui_report_tab.py` — Sales reports, analytics, refunds, CSV export
*   `archive/ui_status_dashboard.py` — Enterprise status dashboard

#### Settings & Configurations
*   `archive/ui_settings_tab.py` — DB path, backup, email, cascade, language, region, tax
*   `archive/ui_templates_tab.py` — Product template CRUD
*   `archive/ui_admin_roles.py` — RBAC role/permission matrix UI
*   `archive/ui_enterprise_settings.py` — Enterprise settings tab

#### Clinical / Rx Workflow
*   `archive/ui_patients_tab.py` — Patient CRUD, custom fields
*   `archive/ui_rx_processing.py` — Prescription processing workflow
*   `archive/ui_epcs_workflow.py` — EPCS (electronic prescribing) workflow
*   `archive/ui_clinical_workflow.py` — Clinical workflow with prescription wizard

#### Auth / Licensing / Banners
*   `archive/license_gate.py` — Startup license validation (signed cache, server, local DB fallback)
*   `archive/ui_auth.py` — Login dialog, owner creation, PIN auth, force re-login
*   `archive/ui_banner.py` — Region banner, notification banners
*   `archive/ui_region_banner.py` — Interactive region change banner
*   `archive/ui_region_fields.py` — Region-specific field rendering

#### Supporting UI Modules
*   `archive/ui_modals.py` — `LabelDesignerPopup`, `QuickReceiveModal`, `BulkAddModal`, `BulkLabelPrintDialog`, `EditBatchDialog`
*   `archive/ui_helpers.py` — Variable extraction utilities
*   `archive/ui_tooltip.py` — Tooltip attachment system
*   `archive/ui_add_tab.py` — Add product tab, bulk add, template resolution
*   `archive/ui_bulk_import.py` — Bulk import tab (Excel/CSV)
*   `archive/ui_enterprise_navigation.py` — Enterprise menu bar + icon toolbar

### 2.4 Cross-Cutting Concerns
| Module | Purpose |
|--------|---------|
| `archive/i18n.py` | Translation system (JSON locales, listener pattern for live language switch) |
| `archive/localization_manager.py` | Singleton `LocalizationManager` — region, currency, tax term |
| `archive/barcode_logic.py` | Barcode generation, config.json management |
| `archive/native_accel.py` | Rust extension binding (`hw_client`, barcode batch generation) |
| `archive/auth_crypto.py` | Argon2 password hashing, secret verification |
| `archive/auth_session.py` | In-memory session timer, auto-logout on idle |
| `archive/authz.py` | `require_permission()` decorator, `check_permission()` |
| `archive/audit_log.py` | Audit trail logging to DB |
| `archive/async_ui.py` | `AsyncTaskManager` — background tasks with `root.after()` completion |

---

## 3. Microsoft Store Requirements (MSIX / PyInstaller)

### 3.1 Filesystem Isolation (Mandatory)
All persistent writes **must** target `%LOCALAPPDATA%\PharmacySuite\`:
| File Type | Current Path | Store-Compliant Path |
|-----------|--------------|---------------------|
| SQLite DB | `get_resource_path("pharmacy.db")` | `%LOCALAPPDATA%\PharmacySuite\pharmacy.db` |
| Config JSON | `get_resource_path("config.json")` | `%LOCALAPPDATA%\PharmacySuite\config.json` |
| Receipts | `archive/receipts/` | `%LOCALAPPDATA%\PharmacySuite\receipts\` |
| Backups | `archive/backups/` | `%LOCALAPPDATA%\PharmacySuite\backups\` |
| Labels | `archive/labels/` | `%LOCALAPPDATA%\PharmacySuite\labels\` |
| License Cache | `.license_cache` (exe dir) | `%LOCALAPPDATA%\PharmacySuite\.license_cache` |
| Logs | Console only | `%LOCALAPPDATA%\PharmacySuite\logs\` |

**Implementation:** Modify `path_utils.get_writable_config_path()` and `database.get_db_path()` to use a single `get_app_data_dir()` resolver. Remove all writes to `sys._MEIPASS` or application directory.

### 3.2 Licensing Bypass Switch
Add `STORE_BUILD` flag to `license_gate.py`:
```python
# license_gate.py — add at module top
STORE_BUILD = os.environ.get("PHARMACY_STORE_BUILD") == "1" or getattr(sys, "frozen", False) and "MSIX" in os.environ.get("APPX_PACKAGE_FULL_NAME", "")

def is_dev_mode() -> bool:
    if STORE_BUILD:
        return True  # Bypass license gate entirely for Store builds
    # ... existing logic
```
**PyInstaller Spec:** Inject via `--runtime-hook` or `--env PHARMACY_STORE_BUILD=1` at build time.

### 3.3 PyInstaller `.spec` Data Dependencies
```python
# pharmacy.spec — datas section
datas = [
    ("archive/locales", "locales"),
    ("archive/assets", "assets"),
    ("archive/label_engine", "label_engine"),
    ("venv/Lib/site-packages/customtkinter", "customtkinter"),  # theme JSONs
]
hiddenimports = [
    "customtkinter", "PIL", "sqlite3", "sqlalchemy", "itsdangerous",
    "requests", "hw_client", "native_accel", "i18n", "localization_manager",
]
```

### 3.4 MSIX Manifest Settings
*   **Identity:** `PharmacySuite_<publisherId>` (reserved in Partner Center)
*   **Capabilities:** `runFullTrust` (for local DB), `internetClient` (license validation)
*   **Entry Point:** `PharmacySuite.exe` (single executable)
*   **Auto-Update:** Use Windows Package Manager (`winget`) or Store automatic updates; disable `check_for_updates()` in Store build

---

## 4. Tkinter Quality & Stability Checklist
1.  **Thread Safety:** Long-running DB/network operations **must NOT** run on main Tkinter thread. All background thread completion handlers **MUST** use `root.after()` or `AsyncTaskManager`.
2.  **Explicit Asset Paths:** All image, icon, theme `.json` files loaded via `path_utils.get_resource_path()` (PyInstaller `sys._MEIPASS` compatible).
3.  **Exception Handling:** Wrap all GUI button callbacks with global catcher `tkinter.Tk.report_callback_exception` → `CTkMessagebox` user-friendly popups.
4.  **DPI Scaling:** Verify `customtkinter.set_widget_scaling()` and window geometry render cleanly across resolutions.
5.  **Layout Integrity:** Use `ttk.PanedWindow`, scrollable viewports, `canvasx()` for coordinate mapping; `pack_propagate(False)` on control panels.

---

## 5. Verified Architecture (Post-Refactor Target)

### 5.1 Database Layer (Single Source)
```
db.py (SQLAlchemy 2.0 ONLY)
├── ORM Models: Product, Receipt, ReceiptItem, Patient, PatientField, Supplier, PurchaseOrder, PoItem, Role, User, Permission, AuditLog, QuickSigTemplate
├── Session Factory: get_session() context manager (auto-commit/rollback)
├── Query Functions: 50+ typed functions returning tuples (backward compat)
├── Migration: init_db() runs raw SQLite ALTER TABLE for legacy schema parity
└── Connection: SQLite (WAL mode) default; PostgreSQL via DATABASE_URL env
```
**Eliminated:** `database.py` (raw SQLite), `_db_fallback` decorator, `_not_available` stubs.

### 5.2 Tab Composition (Explicit Registry)
```python
# ui/tab_registry.py (NEW)
class TabRegistry:
    def __init__(self): self._tabs: dict[str, TabModule] = {}
    def register(self, key: str, module, permission: str = None): ...
    def get_all(self) -> list[TabModule]: ...
    def get_permitted(self, user_id: int) -> list[TabModule]: ...

# main_app.py — explicit registration
registry = TabRegistry()
registry.register("dashboard", ui_dashboard_tab, None)
registry.register("pos_terminal", ui_pos_terminal, "pos.sell")
registry.register("rx_processing", ui_rx_processing, "pos.sell")
# ... all tabs registered once at startup
```
**Eliminated:** `__init__` monkey-patching in `main_app.py:65-195`, `_wire_rx_extensions()`, `_wire_rbac()`.

### 5.3 Extracted Controllers (from `PharmacyApp`)
| Controller | Responsibility | Source Methods |
|------------|----------------|----------------|
| `NavigationController` | Drawer state, tab switching, badge updates, permission gating | `on_tab_change`, `_update_tab_badges`, `nav_drawer` ops |
| `BarcodeRouter` | Global barcode listener, dispatch to active tab handler | `_handle_global_scan`, `_barcode_listener` |
| `TabManager` | Tab lifecycle (setup/load/refresh), RBAC-gated rendering | `setup_*_tab`, `load_*`, `refresh_*` |
| `AlertEngine` | Startup expiry check, low-stock/expiring badge calculation | `_check_startup_expiry`, `_calculate_alert_counts` |
| `ConfigBroadcaster` | Config change propagation (`_notify_inventory_updated`, `_notify_config_updated`) | `_notify_*` methods |

---

## 6. Refactor Roadmap (Verifiable Goals)

### Milestone 1: Database Consolidation (Priority 1)
- [ ] **M1.1** Delete `archive/database.py`; update all imports to `from db import ...`
- [ ] **M1.2** Remove `_db_fallback` decorator; ensure all query functions use `get_session()`
- [ ] **M1.3** Delete `_not_available` stubs in `db.py:154-196`; raise `ImportError` if SQLAlchemy missing
- [ ] **M1.4** Add `get_app_data_dir()` to `path_utils.py`; migrate `get_db_path()` and `get_writable_config_path()`
- [ ] **M1.5** Verify: `init_db()` creates identical schema; all existing tests pass

### Milestone 2: Monkey-Patch Removal (Priority 2)
- [ ] **M2.1** Create `ui/tab_registry.py` with `TabRegistry` class
- [ ] **M2.2** Move all tab registration from `main_app.py:_wire_rx_extensions()` to explicit `registry.register()` calls
- [ ] **M2.3** Replace `PharmacyApp.__init__` monkey-patch with `TabManager(registry, app).initialize_all()`
- [ ] **M2.4** Remove `_wire_rbac()` monkey-patch; move RBAC gate to explicit `AuthController.startup_gate(app)`
- [ ] **M2.5** Verify: App launches with all 19 tabs; RBAC hides correct tabs per role

### Milestone 3: God Class Extraction (Priority 3)
- [ ] **M3.1** Extract `NavigationController` from `PharmacyApp` (nav drawer, tab switching, badges)
- [ ] **M3.2** Extract `BarcodeRouter` (global scan dispatch)
- [ ] **M3.3** Extract `TabManager` (tab setup/load/refresh lifecycle)
- [ ] **M3.4** Extract `AlertEngine` (expiry/low-stock checks)
- [ ] **M3.5** Extract `ConfigBroadcaster` (change notification)
- [ ] **M3.6** `PharmacyApp` becomes thin orchestrator (~150 lines) composing controllers
- [ ] **M3.7** Verify: Layout integrity test passes (no clipping, elastic overflow)

### Milestone 4: Store Hardening
- [ ] **M4.1** Implement `STORE_BUILD` bypass in `license_gate.py`
- [ ] **M4.2** Update `path_utils.py` for `%LOCALAPPDATA%\PharmacySuite\` isolation
- [ ] **M4.3** Create `pharmacy.spec` with all data dependencies
- [ ] **M4.4** Add MSIX manifest template (`Package.appxmanifest`)
- [ ] **M4.5** Verify: PyInstaller build runs; MSIX installs; DB writes to AppData

---

## 7. Orphans & Pending
*   [ ] `archive/updater.py` — referenced in `main.py:11` but not found in scan; verify existence
*   [ ] `archive/ui_tooltip.py` — used by `ui_navigation.py:199-204`; confirm integration
*   [ ] `archive/quick_sig.py` — referenced in `main_app.py:119`; verify module exists
*   [ ] `backend_fastapi/` — separate FastAPI backend; confirm no desktop app dependency
*   [ ] `archive/ocr_engine.py`, `archive/ocr_cascade.py` — OCR pipeline; verify UI integration points
*   [ ] `archive/crash_reporter.py` — installed in `main.py:13`; verify Store compatibility (no crash dumps to Program Files)

---

## 8. Verification Checklist (Per Protocol II.A)
Run after each milestone:
```python
def _debug_layout_geometry(app):
    app.update_idletasks()
    # Sidebar width >= 220px (minsize from ui_navigation.py:518)
    assert app.nav_drawer.winfo_width() >= 220, "Sidebar crushed"
    # Content area visible
    assert app.tab_view._content.winfo_width() > 0, "Content collapsed"
    # No widget clips off-screen
    for child in app.winfo_children():
        x, y = child.winfo_x(), child.winfo_y()
        w, h = child.winfo_width(), child.winfo_height()
        assert x + w <= app.winfo_width(), f"Clip: {child} at {x}+{w} > {app.winfo_width()}"
```