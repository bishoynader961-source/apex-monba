# Architectural Plan: Enterprise Settings & POS Terminal Module Integration

## Context & Scope

**Status:** Planning — awaiting approval before implementation

Two new visual modules are to be integrated into the PharmacyPro desktop application (CustomTkinter + Python 3.12). They reside in `archive/` alongside existing Rx workflow modules. The three backend files (`rx_config.py`, `rx_database.py`, `rx_strategies.py`) plus `rx_db.py` are **locked APIs** — import and call only, no modifications to core logic.

### Codebase Reference Summary

| Layer | File | Key APIs (import-only) |
|---|---|---|
| Config | `rx_config.py` | `ConfigManager` (singleton), `set_path`, `load`, `get`, `set`, `get_region`, `set_region`, `set_credential`, `get_credential`, `register_listener`, `encrypt_secret`, `decrypt_secret`, `get_labels` |
| Database | `rx_database.py` | `init_rx_tables`, `get_prescription_by_id`, `add_prescription`, `update_prescription`, `search_prescriptions`, `get_prescriptions_by_patient`, `get_distinct_rx_field_names`, `set_region_config`, `get_region_config`, `hipaa_log_access`, `gdpr_hard_delete_patient`, `update_rx_status`, `update_rx_filled`, `get_rx_audit_log` |
| ORM Layer | `rx_db.py` | `get_session`, `DATABASE_URL`, `init_rx_tables`, `add_prescriber`, `get_prescriber_by_id`, `search_prescribers`, `get_all_prescribers`, `add_inventory_item`, `get_inventory_item`, `search_inventory`, `get_all_inventory`, `update_inventory_on_hand`, `add_rx`, `get_rx_by_id`, `get_rxs_by_patient`, `get_rxs_by_status`, `get_rx_status_counts`, `update_rx_status`, `update_rx_filled`, `get_rx_audit_log`, `add_insurance`, `get_insurance_by_patient`, `get_all_insurance`, `search_insurance`, `set_region_config`, `get_region_config`, `gdpr_hard_delete_patient`, `hipaa_log_access`, `get_prescriber_labels`, `REGION_LABELS`, `RX_STATUSES` |
| Strategies | `rx_strategies.py` | `strategy_factory(region)`, `PharmacyIntegrationStrategy` (ABC), `USBillingStrategy`, `EUBillingStrategy`, `MockProvider` each with: `calculate_patient_cost`, `generate_claim`, `validate_prescription`, `authenticate(credentials) → (bool, str)` |
| Pharmacy DB | `database.py` | `get_db_path`, `get_grouped_products`, `get_product_by_internal_barcode`, `get_product_by_barcode`, `create_receipt`, `get_all_patients`, `add_patient`, `get_sold_items` |
| Audit | `audit_log.py` | `init_audit_db`, `log_action(action, details, user_pin)`, `get_logs(limit, search_query)` |
| Config | `rx_config.json` | `{region, unit_system, compliance, rx_secrets_file:"rx_secrets.json"}` |
| Async | `async_ui.py` | `AsyncUI.get()`, `async_run(func, callback, args, kwargs)` |

### Existing UI Patterns (from `ui.py`, `ui_settings_tab.py`, `ui_checkout_tab.py`)

1. **Tab registration**: `self.tab_<name> = self.tab_view.add(i18n.t("<key>"))` → then `setup_<tab>(self)` populates the frame. Methods attached via monkey-patching: `PharmacyApp.setup_<tab> = setup_<tab>`.
2. **Navigation drawer**: `ui_navigation._NAV_ICONS` dict maps i18n keys → icon strings. `create_navigation_system()` reads this dict at creation time.
3. **Treeview styling**: `apply_treeview_style(tree)` from `ui_helpers.py` (applies odd/even row tags + status tags).
4. **Theme**: `ctk.set_appearance_mode("Dark")`, `ctk.set_default_color_theme("blue")` (global, must not change).
5. **i18n**: `i18n.t("key")` for all display text, `i18n.get_available_languages()` for locale dropdowns.
6. **Layout**: Grid-based with `CTkFrame`, `CTkScrollableFrame`, `ttk.Treeview`, `ttk.Scrollbar`, `CTkButton`, `CTkEntry`, `CTkComboBox`, `CTkSegmentedButton`.
7. **Tab change handling**: `on_tab_change(self)` in `ui.py` — checks `self.tab_view.get()` and calls refresh methods.
8. **Credential storage**: `rx_config.py` stores encrypted creds in `_credentials` dict (in-memory only). `rx_secrets.json` is referenced but does NOT exist — must be created/persisted by the new module.

---

## 1. Enterprise Settings Module (`archive/ui_enterprise_settings.py`)

### Purpose
A comprehensive enterprise configuration panel providing region-based billing integration settings, Fernet-encrypted credential persistence to `rx_secrets.json`, connection testing via `strategy.authenticate()`, and a compliance audit log viewer with full Rx-specific column support.

### Existing Foundation
`rx_integration_settings.py` already provides `RxBillingSettingsFrame` with:
- Region selector (`CTkSegmentedButton` with US/GB/DE)
- Dynamic credential fields (US: api_key, switch_id, pharmacy_npi; EU: fmd_api_key, cert_path, ods_code)
- Test connection → `strategy_factory(region).authenticate(creds)` → `(bool, str)`
- Save → `ConfigManager.set_credential(key, value)`
- Limitations: credentials only stored in-memory; no file persistence; no audit log viewer

### Class Structure

```
ui_enterprise_settings.py
├── class EnterpriseSettingsFrame(ctk.CTkFrame)
│   ├── __init__(self, master, config_path, **kwargs)
│   ├── _build_ui(self) — builds region selector, credential card, auth test card, audit log card
│   ├── _rebuild_credential_fields(self) — destroy + recreate cred inputs per region
│   ├── _load_stored_credentials(self) — load from rx_secrets.json → ConfigManager._credentials
│   ├── _collect_credentials(self) → dict[service: value]
│   ├── _on_test_connection(self) — calls strategy_factory(region).authenticate(creds)
│   ├── _on_save(self) — encrypt via ConfigManager → persist to rx_secrets.json
│   ├── _on_region_changed(self, new_region) — ConfigManager.set_region + rebuild + reload creds
│   ├── _on_audit_refresh(self) — reload audit log Treeview
│   ├── _on_audit_search(self) — filter audit log by query
│   ├── _on_audit_clear(self) — clear search filter
│   ├── _load_secrets_file(self) → dict[region: {service: encrypted_token}]
│   ├── _save_secrets_file(self, data) — write rx_secrets.json
│   ├── _refresh_compliance_status(self) — show policy (HIPAA/GDPR) + unit system
│   └── _get_audit_connection(self) — get SQLAlchemy session or sqlite3 connection
├── def setup_enterprise_settings_tab(self) — attaches to PharmacyApp, creates frame in tab
└── def _refresh_enterprise_tab(self) — called from on_tab_change hook
```

### CustomTkinter Layout

```
CTkScrollableFrame (outer container)
├── Title: "Enterprise Settings" (CTkLabel, bold 24pt)
│
├── ── Region & Compliance Card (CTkFrame, fg=#1a1a2e) ──
│   ├── Region selector: CTkSegmentedButton [US | GB | DE]
│   ├── Compliance policy badge: CTkLabel ("HIPAA" / "GDPR")
│   └── Unit system indicator: CTkLabel ("Imperial" / "Metric")
│
├── ── Billing Credentials Card (CTkFrame, fg=#2d2d3a) ──
│   ├── Dynamic credential fields (label + entry per region-specific key)
│   ├── cert_path gets Browse button (filedialog.askopenfilename)
│   └── Status label (green success / red error)
│
├── ── Connection Test Card (CTkFrame, fg=#2d2d3a) ──
│   ├── Test Connection button → strategy_factory(region).authenticate(creds)
│   └── Real-time status indicator
│
├── ── Action Buttons ──
│   ├── Save Credentials button (green)
│   └── Export Audit Report button (blue)
│
└── ── Compliance Audit Log Card (CTkFrame, fg=#1a1a2e) ──
    ├── Search bar: CTkEntry + Search/Clear buttons
    ├── Treeview: (Timestamp, Action, Subject Type, Subject ID, Rx ID, Category, Role, Region, Details, Old→New)
    │   • Uses apply_treeview_style()
    │   • Column widths optimized for audit data
    │   • Row striping via odd/even tags
    │   • gdpr_deleted rows highlighted in red
    ├── Count label: "N log entries found"
    └── Double-click → show full details in messagebox
```

### Database Integration Hooks

| Backend Function | Module | Usage |
|---|---|---|
| `ConfigManager.set_region(region)` | rx_config.py | Updates region + auto-sets unit_system + compliance; triggers listener callbacks |
| `ConfigManager.get_region()` | rx_config.py | Read current region for credential lookups |
| `ConfigManager.set_credential(service, value, region)` | rx_config.py | Encrypts via `encrypt_secret()` → stores in `_credentials[region][service]` |
| `ConfigManager.get_credential(service, region)` | rx_config.py | Decrypts via `decrypt_secret()` → returns plaintext |
| `ConfigManager.register_listener(callback)` | rx_config.py | Register callback for region changes to rebuild UI |
| `encrypt_secret(plaintext)` | rx_config.py | Fernet encryption with stdlib fallback; used for rx_secrets.json persistence |
| `decrypt_secret(token)` | rx_config.py | Fernet decryption |
| `strategy_factory(region)` | rx_strategies.py | Returns US/EU/Mock strategy for connection testing |
| `strategy.authenticate(credentials)` | rx_strategies.py | Returns `(bool, str)` for connection test result |
| `get_labels(region)` | rx_config.py | Region-specific field labels |
| `rx_db.get_session()` | rx_db.py | SQLAlchemy session for querying extended audit_logs table |
| `rx_db.init_rx_tables()` | rx_db.py | Ensure audit_logs has compliance columns (called at startup) |
| `audit_log.log_action(action, details, user_pin)` | audit_log.py | Log credential save/test events |

### rx_secrets.json Persistence Design

The file does NOT exist yet. The module creates it with the following schema:

```json
{
    "US": {
        "api_key": "<fernet_token>",
        "switch_id": "<fernet_token>",
        "pharmacy_npi": "<fernet_token>"
    },
    "GB": {
        "fmd_api_key": "<fernet_token>",
        "cert_path": "<fernet_token>",
        "ods_code": "<fernet_token>"
    }
}
```

- Path resolved from `rx_config.json` → `rx_secrets_file` key → resolved relative to `archive/` directory
- File permissions: standard filesystem (no special perms on Windows)
- Load flow: `_load_secrets_file()` → for each region/service → `decrypt_secret(token)` → `ConfigManager.set_credential(service, plaintext, region)` → populates in-memory cache
- Save flow: `ConfigManager.set_credential(service, value, region)` → `encrypt_secret(value)` → collect all `_credentials` → `_save_secrets_file(data)` writes JSON

### Compliance Audit Log Viewer

The extended `audit_logs` table (columns added by `rx_db.init_rx_tables()`):

| Column | Type | Source |
|---|---|---|
| id | INTEGER PK | `audit_log.py` / `rx_db.AuditLogEntry` |
| timestamp | TEXT | `audit_log.py` |
| action | TEXT | `audit_log.py` |
| user_pin | TEXT | `audit_log.py` |
| details | TEXT | `audit_log.py` |
| region | TEXT DEFAULT 'US' | `rx_db.py` — added via ALTER |
| category | TEXT DEFAULT '' | `rx_db.py` — added via ALTER |
| subject_type | TEXT DEFAULT '' | `rx_db.py` — added via ALTER |
| subject_id | INTEGER | `rx_db.py` — added via ALTER |
| rx_id | INTEGER | `rx_db.py` — added via ALTER |
| old_value | TEXT DEFAULT '' | `rx_db.py` — added via ALTER |
| new_value | TEXT DEFAULT '' | `rx_db.py` — added via ALTER |
| role | TEXT DEFAULT 'user' | `rx_db.py` — added via ALTER |
| gdpr_deleted | INTEGER DEFAULT 0 | `rx_db.py` — added via ALTER |

Query approach: Since `rx_database.py` only provides `get_rx_audit_log(rx_id)` (filtered by Rx), and `audit_log.py` only returns 4 columns, the module must query the full table. Two paths:
1. **SQLAlchemy path** (preferred): `rx_db.get_session()` + `text("SELECT ... FROM audit_logs ORDER BY id DESC LIMIT :limit")`
2. **SQLite fallback**: `sqlite3.connect(database.get_db_path())` with same SELECT

The query returns all 13 columns. Search filters on `action`, `details`, `subject_type`, `subject_id`, `rx_id`, `user_pin`.

---

## 2. POS Terminal Module (`archive/ui_pos_terminal.py`)

### Purpose
A point-of-sale terminal optimized for the Rx workflow, using `inventory_extended` for drug lookup, with real-time tax/total calculation, and an action bar for transaction logging across four sale types (Delivery, OTC, Rx OTC, Loyalty).

### Existing Foundation
`ui_checkout_tab.py` provides the standard pharmacy checkout pattern with:
- Barcode scan entry + Treeview cart
- Qty adjust buttons (+1/-1/remove/clear)
- Patient selection combo
- Payment method (Cash/Card/Insurance)
- Total calculation
- Receipts history Treeview
- Uses `database.create_receipt()` and `database.get_product_by_internal_barcode()`

The POS Terminal uses the **Rx inventory** (`inventory_extended` table via `rx_db.py`), not the standard `products` table.

### Class Structure

```
ui_pos_terminal.py
├── class PosTerminalFrame(ctk.CTkFrame)
│   ├── __init__(self, master, **kwargs)
│   ├── _build_ui(self) — builds action bar, lookup panel, cart, order summary, txn log
│   ├── _on_sale_type(self, sale_type) — set active sale type + highlight button
│   ├── _on_search_change(self, query) — filter inventory_extended by NDC/name
│   ├── _on_add_to_cart(self, ndc_code) — add inventory item to cart
│   ├── _on_qty_change(self, index, new_qty) — update cart qty
│   ├── _on_remove_item(self, index) — remove from cart
│   ├── _on_clear_cart(self) — clear all items
│   ├── _recalculate_totals(self) — subtotal, tax, total (real-time)
│   ├── _on_complete_sale(self) — log transaction + decrement inventory
│   ├── _refresh_txn_log(self) — reload transaction log Treeview
│   └── _export_receipt(self, receipt_data) — print/export thermal receipt
├── def setup_pos_terminal_tab(self) — attaches to PharmacyApp, creates frame in tab
└── def _refresh_pos_tab(self) — called from on_tab_change hook
```

### CustomTkinter Layout

```
self.tab_pos_terminal (grid: row 0 = action bar, row 1 = main workspace)
├── ── Action Bar (row 0) ──
│   CTkFrame (fg=#2d2d3a, height=50)
│   ├── CTkButton "Delivery" (purple)
│   ├── CTkButton "OTC" (blue)
│   ├── CTkButton "Rx OTC" (green)
│   ├── CTkButton "Loyalty" (amber)
│   └── CTkLabel "Mode: <active>" (dynamic indicator)
│   Grid: 4 columns for buttons, 1 for indicator
│   pack_propagate(False) to protect height
│
├── ── Main Workspace (row 1, grid 2 columns) ──
│   ├── Left Panel (60% width)
│   │   ├── Product Lookup Card (CTkFrame)
│   │   │   ├── CTkEntry "Search NDC or drug name..." (bind <KeyRelease>)
│   │   │   └── Treeview: search results
│   │   │       Columns: NDC, Drug Name, Strength, Form, On Hand, AWP, MAC, Supplier, Expiry
│   │   │       Double-click → add to cart
│   │   │
│   │   └── Cart Card (CTkFrame)
│   │       ├── CTkLabel "Cart" (bold)
│   │       ├── Treeview: cart items
│   │       │   Columns: Item, NDC, Strength, Qty, Unit Price, Line Total
│   │       │   Inline qty Entry in Qty column (editable, auto-recalc)
│   │       │   Odd/even row striping via apply_treeview_style
│   │       └── Button row: Qty+1, Qty-1, Remove, Clear All
│   │
│   └── Right Panel (40% width)
│       ├── Order Summary Card (CTkFrame, fg=#1a1a2e)
│       │   ├── CTkLabel "Subtotal: $0.00"
│       │   ├── CTkLabel "Tax: $0.00" (rate from config.json)
│       │   ├── CTkLabel "Total: $0.00" (bold, large)
│       │   └── CTkLabel "Items: 0"
│       │
│       ├── Payment + Complete Card
│       │   ├── CTkSegmentedButton [Cash | Card | Transfer]
│       │   ├── CTkEntry "Amount Tendered" (for change calculation)
│       │   ├── CTkLabel "Change: $0.00"
│       │   └── CTkButton "Complete Transaction" (green, large)
│       │
│       └── Transaction Log Card (CTkFrame, fg=#2d2d3a)
│           ├── CTkLabel "Recent Transactions"
│           └── Treeview: (Time, Type, Items, Total, Payment, Status)
│               Limited to last 50 entries
```

### Cart State Management

Cart is a list of dicts stored as `self.pos_cart`:

```python
self.pos_cart = [
    {
        "ndc_code": str,          # from inventory_extended.ndc_code
        "drug_name": str,
        "strength": str,
        "dosage_form": str,
        "qty": int,
        "unit_price": float,       # from inventory_extended.awp or mac
        "on_hand": int,            # from inventory_extended (for stock validation)
        "supplier": str,
        "lot_number": str,
        "expiration_date": str,
    }
]
```

### Real-Time Tax/Total Calculations

1. **Subtotal**: `sum(item.qty * item.unit_price for item in cart)`
2. **Tax rate**: Read from `barcode_logic.load_config().get("tax_rate", 0.0)` → stored as percentage (e.g., 8.5 = 8.5%)
3. **Tax amount**: `subtotal * (tax_rate / 100)`
4. **Total**: `subtotal + tax_amount`
5. Recalculation triggered on: qty change, item add, item remove, clear cart, sale type change
6. Tax is shown as a line item in the order summary

### Sale Types & Transaction Logging

| Sale Type | Description | Audit Log Action |
|---|---|---|
| Delivery | Prescription delivery to patient | `POS_SALE_DELIVERY` |
| OTC | Over-the-counter sale | `POS_SALE_OTC` |
| Rx OTC | Pharmacy-counter sale | `POS_SALE_RX_OTC` |
| Loyalty | Loyalty member sale | `POS_SALE_LOYALTY` |

Each sale type:
- Sets `self.pos_sale_type` (default: "OTC")
- Highlights the active button (fg_color changes)
- Logged via `audit_log.log_action("POS_SALE_<TYPE>", details)` on complete

### Inventory Decrement on Sale

After sale completion:
1. For each cart item: `rx_db.update_inventory_on_hand(ndc_code, new_qty)` where `new_qty = current_on_hand - sold_qty`
2. If insufficient stock: show error, abort transaction
3. Log each decrement via `audit_log.log_action("INVENTORY_DECREMENT", details)`

### Database Integration Hooks

| Backend Function | Module | Usage |
|---|---|---|
| `rx_db.get_all_inventory()` | rx_db.py | Load all inventory_extended rows for initial display |
| `rx_db.search_inventory(query)` | rx_db.py | Filter by NDC/drug_name/ndc_formatted |
| `rx_db.get_inventory_item(ndc_code)` | rx_db.py | Get single item by NDC for detailed view |
| `rx_db.update_inventory_on_hand(ndc_code, new_qty)` | rx_db.py | Decrement stock after sale |
| `rx_db.init_rx_tables()` | rx_db.py | Ensure inventory_extended exists at startup |
| `database.get_db_path()` | database.py | Fallback sqlite3 connection if SQLAlchemy unavailable |
| `database.create_receipt(method, items, patient_id)` | database.py | Reuse existing receipt creation for standard sales (optional) |
| `barcode_logic.load_config()` | barcode_logic.py | Get tax_rate, pharmacy_name for receipt |
| `audit_log.log_action(action, details, user_pin)` | audit_log.py | Transaction logging |
| `receipt_engine.generate_receipt(receipt_id, cart, total, ...)` | receipt_engine.py | Thermal receipt generation |

---

## 3. Integration Strategy

### Approach: Non-Invasive Monkey-Patching via `main_app.py`

Per `rx_wiring_instructions.md`, the integration is performed in `archive/main_app.py` without modifying `ui.py`, `ui_navigation.py`, `main.py`, or any backend file. The pattern follows the existing module attachment in `ui.py` (monkey-patching `PharmacyApp` methods).

### Step-by-Step Roadmap

#### Phase 1: Enterprise Settings Module

1. **Create `archive/ui_enterprise_settings.py`**
   - Define `EnterpriseSettingsFrame(ctk.CTkFrame)` class
   - Implement `_build_ui()`, `_rebuild_credential_fields()`, `_load_stored_credentials()`
   - Implement `_load_secrets_file()` / `_save_secrets_file()` for `rx_secrets.json` persistence
   - Implement `_on_test_connection()` using `strategy_factory(region).authenticate(creds)`
   - Implement `_on_save()` — calls `ConfigManager.set_credential()` + persists to file
   - Implement `_on_region_changed()` — calls `ConfigManager.set_region()` + rebuilds cred fields
   - Implement audit log Treeview with full 13-column schema
   - Define `setup_enterprise_settings_tab(self)` function
   - Import: `rx_config`, `rx_strategies`, `rx_db`, `audit_log`, `database`, `barcode_logic`, `i18n`, `ui_helpers`

2. **Add i18n keys** to `archive/locales/en.json` (all 6 locale files):
   - `enterprise_settings`, `enterprise_settings_subtitle`
   - `region_label`, `compliance_policy`, `unit_system`
   - `billing_credentials`, `connection_test`, `save_credentials`
   - `audit_log_compliance`, `audit_search`, `audit_clear`, `audit_entries`
   - `secret_key`, `switch_id`, `pharmacy_npi`, `fmd_api_key`, `cert_path`, `ods_code`
   - `test_connection`, `connection_success`, `connection_failed`, `credentials_saved`

3. **Verify**: Import smoke test, credential round-trip, audit log query

#### Phase 2: POS Terminal Module

1. **Create `archive/ui_pos_terminal.py`**
   - Define `PosTerminalFrame(ctk.CTkFrame)` class
   - Implement action bar with 4 sale type buttons (Delivery/OTC/Rx OTC/Loyalty)
   - Implement product lookup Treeview using `rx_db.search_inventory()`
   - Implement cart Treeview with inline qty editing
   - Implement `_recalculate_totals()` — subtotal, tax (from config), total
   - Implement `_on_complete_sale()` — validate stock, decrement via `rx_db.update_inventory_on_hand()`, log via `audit_log.log_action()`
   - Implement transaction log Treeview
   - Define `setup_pos_terminal_tab(self)` function
   - Import: `rx_db`, `rx_strategies`, `database`, `barcode_logic`, `audit_log`, `receipt_engine`, `i18n`, `ui_helpers`, `async_ui`

2. **Add i18n keys**:
   - `pos_terminal`, `pos_terminal_subtitle`
   - `sale_delivery`, `sale_otc`, `sale_rx_otc`, `sale_loyalty`
   - `search_ndc`, `search_placeholder`
   - `cart`, `subtotal`, `tax`, `total`, `items_count`
   - `complete_transaction`, `amount_tendered`, `change_due`
   - `transaction_log`, `recent_transactions`

3. **Verify**: Import smoke test, cart calculation test, tax formula test

#### Phase 3: Navigation & Tab Integration (modify `main_app.py`)

1. **Patch `_NAV_ICONS` before app creation**:
   ```python
   # In main_app.py, before calling pharmacy_main():
   import ui_navigation as _nav
   _nav._NAV_ICONS["enterprise_settings"] = "🏢"
   _nav._NAV_ICONS["pos_terminal"] = "💎"
   ```

2. **Patch `PharmacyApp.__init__` to add new tabs**:
   ```python
   # Save original __init__, wrap it:
   _orig_init = PharmacyApp.__init__

   def _patched_init(self):
       _orig_init(self)
       # Add new tabs after existing setup
       self.tab_enterprise = self.tab_view.add("Enterprise Settings")
       self.tab_pos_terminal = self.tab_view.add("POS Terminal")
       setup_enterprise_settings_tab(self)
       setup_pos_terminal_tab(self)
       # Initialize Rx tables
       from rx_database import init_rx_tables
       init_rx_tables()
       # Initialize secrets file
       from rx_config import ConfigManager
       config_path = ...
       cm = ConfigManager()
       cm.set_path(config_path)

   PharmacyApp.__init__ = _patched_init
   ```

3. **Patch `on_tab_change` to handle new tabs**:
   ```python
   _orig_on_tab_change = PharmacyApp.on_tab_change

   def _patched_on_tab_change(self):
       _orig_on_tab_change(self)
       current = self.tab_view.get()
       if current == "Enterprise Settings":
           self._refresh_enterprise_tab()
       elif current == "POS Terminal":
           self._refresh_pos_tab()

   PharmacyApp.on_tab_change = _patched_on_tab_change
   ```

4. **Add path setup in `main_app.py`**:
   ```python
   sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
   ```
   (Already present — `main_app.py` adds its own directory to sys.path)

#### Phase 4: Verification & Testing

1. **Run existing Rx tests**: `python test_rx_config.py`, `python test_rx_strategies.py`, `python test_rx_database.py` — ensure zero regressions
2. **Import smoke test**: `python -c "from ui_enterprise_settings import EnterpriseSettingsFrame; from ui_pos_terminal import PosTerminalFrame"` 
3. **Credential round-trip**: Call `ConfigManager.set_credential()` → `_save_secrets_file()` → `_load_secrets_file()` → `ConfigManager.get_credential()` — verify plaintext matches
4. **Audit log query**: Verify the Treeview can display rows from the extended `audit_logs` table
5. **POS cart calculation**: Verify subtotal + tax + total formula with sample cart data
6. **Layout stress test** (per VERIFICATION_CHECKLIST.md): Long drug names in Treeview, extreme qty values, window resize at minimum size
7. **Update `PROJECT_MAP.md`**: Add new modules to file inventory, mark milestones complete

### Integration Points Summary

```
main_app.py (entry point)
  ├── sys.path includes archive/ (already done)
  ├── Patch ui_navigation._NAV_ICONS ← "enterprise_settings", "pos_terminal"
  ├── import ui_enterprise_settings  (setup_enterprise_settings_tab, EnterpriseSettingsFrame)
  ├── import ui_pos_terminal         (setup_pos_terminal_tab, _refresh_pos_tab)
  ├── Patch PharmacyApp.__init__     → add tab frames + call setup functions
  ├── Patch PharmacyApp.on_tab_change → add refresh hooks for new tabs
  └── Patch PharmacyApp methods      → attach setup functions via monkey-patch

ui.py (NOT MODIFIED) 
  ← PharmacyApp.__init__ patched from main_app.py
  ← on_tab_change patched from main_app.py

ui_navigation.py (NOT MODIFIED)
  ← _NAV_ICONS patched from main_app.py
```

### Constraints Compliance

| Constraint | How Addressed |
|---|---|
| Backend Immutability | `rx_config.py`, `rx_database.py`, `rx_strategies.py` imported only — no modifications proposed |
| UI Consistency | Dark theme + blue color scheme preserved; uses `apply_treeview_style()`; same component patterns (CTkCard, CompactCard); new tabs use same grid layout approach |
| Phase Restriction | No implementation code generated in this plan — awaiting approval |
| No placeholders/TODOs | All functions fully specified with inputs/outputs/return values |
| Layout elasticity | Treeviews use scrollbars; CTkScrollableFrame for forms; pack_propagate(False) on fixed-height elements |
| Async non-blocking | `AsyncUI` used for inventory search + audit log loading (background thread → `after()` callback) |

---

## Open Questions

1. **Tab labels**: Should the new tabs use i18n keys (`i18n.t("enterprise_settings")`) or hardcoded strings? The existing pattern uses i18n keys. The plan includes adding keys to all locale files, but this requires modifying 6 JSON files. Alternative: use hardcoded English strings (simpler, but breaks i18n consistency). **Recommendation**: Add i18n keys for full consistency.

2. **rx_secrets.json location**: The `rx_config.json` has `"rx_secrets_file": "rx_secrets.json"` (relative path). Should this resolve relative to: (a) the `archive/` directory, (b) the project root, or (c) the user home directory? **Recommendation**: `archive/` directory (same as `rx_config.json`).

3. **POS Terminal inventory source**: Should the POS terminal use `inventory_extended` (Rx drug inventory) exclusively, or should it also support the standard `products` table? The user spec says "inventory lookup via the inventory_extended table", so **inventory_extended only**.

4. **Receipt generation in POS**: Should the POS Terminal use the existing `receipt_engine.generate_receipt()` or a new thermal format? **Recommendation**: Reuse `receipt_engine` for consistency with `ui_checkout_tab.py`, but add sale-type metadata to the receipt.

5. **Audit log write permissions**: The extended `audit_logs` table is created/migrated by `rx_db.init_rx_tables()`. Should `init_rx_tables()` be called from the Enterprise Settings module or from the main_app.py wiring hook? **Recommendation**: Call from `main_app.py` during `__init__` patch (one-time, idempotent).
