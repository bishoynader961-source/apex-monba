# Architectural Plan: Rx Processing Module Integration

## Context & Scope

**Status:** Planning — awaiting approval before implementation

A new visual module `archive/ui_rx_processing.py` is to be integrated into the PharmacyPro desktop application (CustomTkinter + Python 3.12). The four backend files (`rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py`) are **locked APIs** — import and call only; no modifications to core logic, classes, or architecture.

The existing modules `ui_enterprise_settings.py` and `ui_pos_terminal.py` (already implemented in `archive/`) serve as the reference architecture for the monkey-patching integration pattern via `main_app.py`.

---

## 1. Backend API Inventory (Import-Only — LOCKED)

### rx_config.py — ConfigManager Singleton
| Function | Signature | Return |
|---|---|---|
| `ConfigManager()` | — | singleton instance |
| `cm.set_path(path)` | str | void |
| `cm.load()` | — | dict |
| `cm.get(key, default)` | str, any | any |
| `cm.get_region()` | — | str ("US"/"GB"/"DE") |
| `cm.set_region(region)` | str | void (auto-sets unit_system + compliance + notifies listeners) |
| `cm.is_hipaa()` / `cm.is_gdpr()` | — | bool |
| `cm.set_credential(service, value, region)` | str, str, str | void (encrypts via Fernet) |
| `cm.get_credential(service, region)` | str, str | str (plaintext) |
| `cm.register_listener(callback)` | callable | void |
| `get_labels(region)` | str | dict of label_key→str |
| `encrypt_secret(plaintext)` | str | str (Fernet token) |
| `decrypt_secret(token)` | str | str (plaintext) |

### rx_db.py — SQLAlchemy ORM Layer (PRIMARY)
| Function | Signature | Return |
|---|---|---|
| `init_rx_tables()` | — | void (idempotent DDL) |
| `search_inventory(query)` | str | list of tuples: (id, ndc_code, drug_name, strength, dosage_form, ndc_formatted, awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata_json) |
| `get_all_inventory()` | — | list of same tuples |
| `get_inventory_item(ndc_code)` | str | tuple or None |
| `add_rx(patient_id, prescriber_id, drug_ndc, days_supply, daw_code, refills, sig_code, quantity, date_prescribed, notes, regional_metadata)` | (int,int,str,int,str,int,str,int,str,str,dict) | int (rx_id) |
| `add_rx_regional(region, patient_id, prescriber_id, drug_ndc, **fields)` | str,int,int,str,**kw | int (rx_id) |
| `get_rx_by_id(rx_id)` | int | tuple: (id, rx_number, patient_id, prescriber_id, drug_ndc, days_supply, daw_code, refills_remaining, sig_code, quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata_json) |
| `get_rxs_by_status(status)` | str | list of tuples (same schema) |
| `get_rx_status_counts()` | — | dict {status: count, total: N} |
| `update_rx_status(rx_id, new_status, user_pin, role, region, subject_type, subject_id)` | int, str, ... | bool |
| `update_rx_filled(rx_id, user_pin, role, region)` | int, str, str, str | bool |
| `get_rx_audit_log(rx_id, limit)` | int, int | list of audit tuples |
| `search_prescribers(query)` | str | list of tuples: (id, npi, dea_number, state_license, first_name, last_name, phone, email, address, dea_expiration, is_active, regional_metadata_json) |
| `get_all_prescribers()` | — | list of same tuples |
| `get_prescriber_by_id(prescriber_id)` | int | tuple or None |
| `get_prescriber_regional(prescriber_id)` | int | dict (with parsed metadata) |
| `add_insurance(patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata)` | int, str, str, str, str, str, dict | int |
| `get_insurance_by_patient(patient_id)` | int | list of tuples: (id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata_json) |
| `get_all_inventory()` | — | list of inventory tuples |
| `update_inventory_on_hand(ndc_code, on_hand)` | str, int | bool |
| `set_region_config(region)` | str | void |
| `get_region_config()` | — | str or None |
| `get_prescriber_labels(region)` | str | dict |
| `REGION_LABELS` | — | dict (US/EU label maps) |
| `RX_STATUSES` | — | tuple: ("Pending", "Billed", "Filled", "Verified", "Will Call", "Rejected") |
| `HAS_SQLALCHEMY` | — | bool |
| `get_session()` | — | context manager yielding SQLAlchemy session |

### rx_database.py — sqlite3 Fallback Layer
| Function | Signature | Return |
|---|---|---|
| `init_rx_tables()` | — | void |
| `add_prescription(patient_id, drug_name, dosage, quantity, custom_fields)` | int, str, str, str, dict | int (rx_id) |
| `get_prescription_by_id(rx_id)` | int | tuple or None |
| `update_prescription(rx_id, update_fields)` | int, dict | void |
| `get_prescriptions_by_patient(patient_id)` | int | list of dicts |
| `search_prescriptions(query)` | str | list of dicts |

### rx_strategies.py — Billing Strategy Pattern
| Function/Class | Signature | Return |
|---|---|---|
| `strategy_factory(region="US")` | str | PharmacyIntegrationStrategy instance |
| `strategy.calculate_patient_cost(unit_price, quantity, insurance_coverage)` | float, int, dict | float (patient pays) |
| `strategy.generate_claim(claim_data)` | dict | dict (claim payload) |
| `strategy.validate_prescription(prescription_data)` | dict | bool (raises ValueError on failure) |
| `strategy.authenticate(credentials)` | dict | (bool, str) |

### database.py — Patients & Core ORM
| Function | Signature | Return |
|---|---|---|
| `database.get_all_patients(search_query=None)` | str or None | list of (pid, name, phone, email, created_at, {field_name: field_value}) |
| `database.get_patient_by_id(patient_id)` | int | (pid, name, phone, email, created_at, {fields}) or None |
| `database.get_db_path()` | — | str |

### audit_log.py — Compliance Logging
| Function | Signature | Return |
|---|---|---|
| `audit_log.log_action(action, details, user_pin)` | str, str, str | void |

### async_ui.py — Non-Blocking Task Runner
| Function | Signature | Return |
|---|---|---|
| `AsyncUI.get()` | — | singleton |
| `AsyncUI.get().run(func, callback, args, kwargs)` | callable, callable, tuple, dict | Future |
| `init_async_ui(root)` | Tk root | AsyncUI (already called in PharmacyApp.__init__) |

### ui_helpers.py
| Function | Signature | Return |
|---|---|---|
| `apply_treeview_style(tree)` | ttk.Treeview | void (configures odd/even + status tags) |

### i18n.py
| Function | Signature | Return |
|---|---|---|
| `i18n.t(key, **kwargs)` | str | str (translated) |

### ui_navigation.py
| Symbol | Type | Usage |
|---|---|---|
| `_NAV_ICONS` | dict | Maps i18n key → icon string; patched by main_app.py |

---

## 2. Rx Processing Module (`archive/ui_rx_processing.py`)

### 2.1 Module Structure

```
ui_rx_processing.py
├── MODULE-LEVEL HELPERS
│   ├── _get_archive_dir() → str          # same as ui_enterprise_settings.py
│   ├── _get_rx_region() → str             # ConfigManager.get_region() with rx_db.get_region_config() fallback
│   ├── _load_patients(search="") → list   # database.get_all_patients() with search filter
│   ├── _load_inventory(query="") → list   # rx_db.search_inventory() with sqlite3 fallback
│   ├── _load_prescribers(query="") → list # rx_db.search_prescribers()
│   ├── _load_insurance(patient_id) → list # rx_db.get_insurance_by_patient()
│   ├── _fetch_rxs_by_status(status) → list # rx_db.get_rxs_by_status()
│   ├── _fetch_rxs_for_queue(queue_name) → list # maps queue name → combined status queries
│   └── _ensure_rx_tables()                # calls rx_db.init_rx_tables() (idempotent)
│
├── class RxProcessingFrame(ctk.CTkFrame)
│   ├── __init__(self, master, **kwargs)
│   ├── _build_ui(self)
│   ├── _build_patient_lookup_panel(self, parent, row)
│   ├── _build_drug_selection_panel(self, parent, row)
│   ├── _build_sig_entry_panel(self, parent, row)
│   ├── _build_prescriber_panel(self, parent, row)
│   ├── _build_action_bar(self, parent, row)
│   ├── _build_queue_tabs(self, parent, row)
│   ├── _populate_patient_fields(self, patient_tuple)
│   ├── _populate_insurance_fields(self, patient_id)
│   ├── _on_patient_search(self, event=None)
│   ├── _on_patient_select(self, event=None)
│   ├── _on_drug_search(self, event=None)
│   ├── _on_drug_select(self, event=None)
│   ├── _on_prescriber_search(self, event=None)
│   ├── _on_prescriber_select(self, event=None)
│   ├── _on_process_bill(self)
│   ├── _on_queue_selection(self, event=None)
│   ├── _on_queue_action(self, action)  # "in_processing" / "rejects" / "ready_pickup"
│   ├── _refresh_queue(self)
│   ├── _refresh_all_queues(self)
│   └── refresh(self)                     # called from on_tab_change
│
├── def setup_rx_processing_tab(self)   # creates RxProcessingFrame in tab
└── def _refresh_rx_processing_tab(self)  # called from on_tab_change hook
```

### 2.2 State Management

The `RxProcessingFrame` instance stores all mutable state on `self`:

```python
# ── Selection State ──
self._selected_patient_id: int = None       # currently selected patient
self._selected_patient: tuple = None         # full patient tuple from DB
self._selected_prescriber_id: int = None
self._selected_prescriber: tuple = None      # full prescriber tuple
self._selected_drug_ndc: str = None          # selected ndc_code from inventory_extended
self._selected_drug: tuple = None            # full inventory tuple

# ── Form State ──
self._sig_var: ctk.StringVar                   # directions text (multiline)
self._qty_var: ctk.StringVar                    # quantity
self._days_supply_var: ctk.StringVar            # days supply
self._refills_var: ctk.StringVar                # refills remaining
self._daw_var: ctk.StringVar                    # DAW code (default "00")
self._notes_var: ctk.StringVar                  # clinical notes

# ── Queue State ──
self._queue_selection: str = "in_processing"   # active queue tab
self._processing_rxs: list = []                 # Rx rows in "In Processing"
self._rejects_rxs: list = []                     # Rx rows in "Rejects"
self._ready_rxs: list = []                       # Rx rows in "Ready for Pickup"

# ── Computed State ──
self._patient_cost: float = 0.0                 # from strategy.calculate_patient_cost
self._insurance_cost: float = 0.0               # base_cost - patient_cost
self._claim_data: dict = None                    # from strategy.generate_claim
```

### 2.3 CustomTkinter Layout

The module follows the exact visual conventions of `ui_pos_terminal.py` and `ui_enterprise_settings.py`:
- Dark theme (global, not modified)
- Card backgrounds: `#1a1a2e` (darkest), `#2d2d3a` (medium), `#2b2b2b/#1e1e1e` (treeview)
- Accent: `#3b82f6` (blue), `#10b981` (green/success), `#ef4444` (red/error), `#f59e0b` (amber/warning)
- `apply_treeview_style(tree)` applied to all ttk.Treeviews
- Layout: `self.grid_columnconfigure(...)` / `self.grid_rowconfigure(...)` for fluid resizing
- `pack_propagate(False)` where fixed-height elements are needed

```
RxProcessingFrame (grid)
├── Row 0: Title Bar
│   ├── CTkLabel "Rx Processing" (font=CTkFont(size=24, weight="bold"))
│   └── CTkLabel subtitle (text_color="#94a3b8")

├── Row 1: Main Workspace (grid, 2 columns)
│   ├── Left Column (weight=3) — form pipeline
│   │   ├── Patient Lookup Card (fg=#2d2d3a)
│   │   │   ├── CTkEntry (search by name/phone/insurance)
│   │   │   ├── Treeview results (small, height=6): Patient Name | Phone | DOB | Insurance
│   │   │   └── Detail display frame (read-only labels populated on selection)
│   │   │       - Demographic fields: name, DOB, phone, email, address (from database.get_patient_by_id)
│   │   │       - Insurance fields: carrier, BIN, PCN, group, plan (from rx_db.get_insurance_by_patient)
│   │
│   │   ├── Prescriber Card (fg=#2d2d3a)
│   │   │   ├── CTkEntry (search by name/NPI/DEA)
│   │   │   ├── Treeview results (height=6): Name | NPI/Reg # | License | Phone
│   │   │   └── Detail display frame (regenerative labels from rx_db.get_prescriber_labels(region))
│   │   ├── Drug Selection Card (fg=#2d2d3a)
│   │   │   ├── CTkEntry (search NDC/PZN/drug name) → bind <KeyRelease> for async search
│   │   │   ├── Treeview results (height=8): NDC | Drug Name | Strength | Form | AWP | On Hand | Lot | Expiry
│   │   │   └── Detail display frame (populated on selection)
│   │   │       - Full drug metadata: NDC, name, strength, form, AWP, MAC, lot, expiry, supplier
│   │   ├── SIG Entry Card (fg=#2d2d3a)
│   │   │   ├── CTkEntry "Directions/SIG" (multiline, width=400)
│   │   │   ├── CTkEntry "Quantity" (with label)
│   │   │   ├── CTkEntry "Days Supply" (with label)
│   │   │   ├── CTkEntry "Refills" (with label)
│   │   │   ├── CTkEntry "DAW Code" (default "00", region-aware)
│   │   │   └── CTkEntry "Notes" (optional)
│   │   └── Action Bar (fg=#2d2d3a, height=60, pack_propagate(False))
│   │       ├── CTkButton "Process / Bill" (fg=#10b981, hover=#059669, large)
│   │       ├── CTkLabel "Patient Cost: $0.00" (text_color=#10b981)
│   │   │   └── CTkLabel "Insurance: $0.00 (status)" (text_color=#3b82f6)
│   │
│   └── Right Column (weight=1) — quick reference
│       ├── CTkLabel "Region: US/HIPAA" (dynamic from ConfigManager)
│       ├── CTkLabel "Tax Rate: X%" (from barcode_logic.load_config)
│       ├── CTkFrame (transparent) — empty spacer for balance
│       └── (optional) CTkButton "Clear Form" (fg=#6c757d)
│
└── Row 2: Queue Tabbed Interface (CTkTabview — 3 tabs)
    ├── Tab "In Processing"
    │   └── Treeview: Rx Number | Patient | Drug | Qty | SIG | Status | Date | Actions
    │       (columns: rx_number, patient_name, drug_name, quantity, sig_code, status, date_prescribed)
    │       → context menu: "Mark Filled", "Reject", "Move to Ready"
    ├── Tab "Rejects"
    │   └── Treeview: Rx Number | Patient | Drug | Qty | Status | Rejection Reason | Date
    │       → context menu: "Re-process", "Delete Permanently"
    └── Tab "Ready for Pickup"
        └── Treeview: Rx Number | Patient | Drug | Qty | Date Ready | Status
            → context menu: "Mark Picked Up"
```

**Queue ↔ Status Mapping** (using `rx_db.RX_STATUSES`):

| Queue Tab | rx_table.status values | Logic |
|---|---|---|
| In Processing | Pending, Billed, Verified | Active workflow — not yet dispensed |
| Rejects | Rejected | Claim rejected, requires attention |
| Ready for Pickup | Will Call | Dispensed, waiting for patient pick-up |

> **Note:** "Filled" is a transient state — after filling, `update_rx_filled()` moves it to "Will Call" automatically. The queue tabs filter by `get_rxs_by_status()`.

### 2.4 Billing & Processing Flow (Process/Bill Button)

```
_on_process_bill(self):
    1. Validate required inputs:
       - Patient selected (self._selected_patient_id is not None)
       - Prescriber selected (self._selected_prescriber_id is not None)
       - Drug selected (self._selected_drug_ndc is not None)
       - Quantity, days supply, SIG not empty
    2. Read region: self._region = _get_rx_region()  # ConfigManager.get_region()
    3. Resolve strategy: strategy = strategy_factory(self._region)
    4. Build claim_data dict:
       {
           "drug_name": ..., "ndc": ..., "quantity": int,
           "days_supply": int, "insurance_id": ...,
           "prescriber_npi": ..., "pharmacy_npi": ...,
           "nhs_number": ..., (EU only)
       }
    5. Build prescription_data dict:
       {
           "drug_name": ..., "dosage": ..., "quantity": ...,
           "prescriber_npi": ... (or prescriber_ods for EU)
       }
    6. Call strategy.validate_prescription(prescription_data)
       → if ValueError, show error message, abort
    7. Call strategy.calculate_patient_cost(unit_price, quantity, insurance_coverage)
       → patient_cost = result
       → insurance_cost = base_cost - patient_cost
    8. Call strategy.generate_claim(claim_data)
       → self._claim_data = result (contains claim payload)
    9. Insert Rx record via rx_db.add_rx() or rx_db.add_rx_regional()
       → rx_id = result
    10. Update rx status: rx_db.update_rx_status(rx_id, "Billed", ...)
    11. Log via audit_log.log_action("RX_PROCESS_BILL", details)
    12. Clear form, refresh all queues
    13. Show success message: "Rx #XXXX processed and billed — Patient pays $X.XX"
```

### 2.5 Module-Level Helper Functions

All helpers follow the same resilience pattern as `ui_pos_terminal.py`:
- Try `rx_db` (SQLAlchemy) first
- Fall back to raw `sqlite3` queries on failure
- Always catch exceptions and log via `logging.getLogger("ui_rx_processing")`

```python
def _get_rx_region():
    """Return current region: ConfigManager > rx_db.get_region_config > ConfigManager.get_region()."""
    try:
        from rx_config import ConfigManager
        region = ConfigManager().get_region()
        if region:
            return region
    except Exception:
        pass
    try:
        import rx_db
        if rx_db.HAS_SQLALCHEMY:
            cfg = rx_db.get_region_config()
            if cfg:
                return cfg
    except Exception:
        pass
    return "US"  # ultimate fallback

def _load_patients(search=""):
    """Return patient list from database.get_all_patients()."""
    try:
        import database
        return database.get_all_patients(search or None)
    except Exception as e:
        log.warning("Failed to load patients: %s", e)
        return []

def _load_inventory(query=""):
    """Return inventory from rx_db.search_inventory() with sqlite3 fallback."""
    try:
        import rx_db
        if rx_db.HAS_SQLALCHEMY:
            return rx_db.search_inventory(query)
    except Exception as e:
        log.debug("rx_db.search_inventory failed, falling back to sqlite3: %s", e)
    # Fallback: raw sqlite3
    try:
        import database, sqlite3
        conn = sqlite3.connect(database.get_db_path())
        cursor = conn.cursor()
        like = f"%{query}%"
        cursor.execute("""
            SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                   awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
            FROM inventory_extended
            WHERE ndc_code LIKE ? OR drug_name LIKE ? OR ndc_formatted LIKE ?
            ORDER BY drug_name ASC
        """, (like, like, like))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log.error("Inventory fallback failed: %s", e)
        return []
```

### 2.6 i18n Keys Required (New)

The following keys must be added to **all 6 locale files** (`en.json`, `de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`):

| Key | English Value | Used In |
|---|---|---|
| `rx_processing` | "Rx Processing" | Tab label / nav icon |
| `rx_processing_subtitle` | "Prescription intake, billing, and queue management" | Subtitle |
| `patient_lookup` | "Patient Lookup" | Panel title |
| `patient_search_placeholder` | "Search patients by name, phone, or insurance..." | Search entry |
| `active_insurance` | "Active Insurance" | Section label |
| `carrier` | "Carrier" | Insurance field |
| `bin_number` | "BIN Number" | Insurance field |
| `pcn` | "PCN" | Insurance field |
| `group_number` | "Group Number" | Insurance field (reuse existing) |
| `no_patients_found` | "No patients found." | Alert |
| `drug_selection` | "Drug / Product Selection" | Panel title |
| `search_ndc_or_drug` | "Search NDC/PZN or drug name..." | Search entry |
| `no_drugs_found` | "No drugs found in inventory." | Alert |
| `sig_entry` | "SIG / Directions" | Panel title |
| `directions` | "Directions" | SIG label |
| `quantity_label` | "Quantity" | Qty label (reuse existing `quantity`) |
| `days_supply` | "Days Supply" | Field label |
| `refills` | "Refills" | Field label |
| `daw_code` | "DAW Code" | Field label |
| `prescriber_lookup` | "Prescriber Lookup" | Panel title |
| `prescriber_search_placeholder` | "Search prescriber by name, NPI, or DEA..." | Search entry |
| `state_license` | "State License" | Field label (reuse from rx_db.REGION_LABELS) |
| `process_bill` | "Process / Bill" | Action button |
| `patient_cost` | "Patient Cost" | Display label |
| `insurance_cost` | "Insurance Cost" | Display label |
| `clear_form` | "Clear Form" | Button |
| `process_success` | "Rx #{rx_number} processed and billed — Patient pays ${cost}" | Success message |
| `missing_fields_error` | "Please select a patient, prescriber, and drug, and enter quantity." | Validation error |
| `queue_in_processing` | "In Processing" | Tab label |
| `queue_rejects` | "Rejects" | Tab label |
| `queue_ready_pickup` | "Ready for Pickup" | Tab label |
| `rx_number` | "Rx Number" | Treeview column |
| `patient_name` | "Patient" | Treeview column |
| `drug_name` | "Drug" | Treeview column |
| `qty` | "Qty" | Treeview column |
| `status` | "Status" | Treeview column (reuse existing or add) |
| `date` | "Date" | Treeview column |
| `mark_filled` | "Mark Filled" | Context menu |
| `mark_rejected` | "Reject" | Context menu |
| `move_to_ready` | "Move to Ready" | Context menu |
| `mark_picked_up` | "Mark Picked Up" | Context menu |
| `reprocess` | "Re-process" | Context menu (rejects) |
| `no_issues` | "No issues" | Empty state |
| `select_patient_first` | "Please select a patient first." | Alert |

> **Note:** `group_number` already exists in en.json (line 180). `quantity` already exists (line 25). These are reused, not re-added.

### 2.7 Region-Aware Behavior

The module must adapt to the current region (set by `ui_enterprise_settings.py`):

| Aspect | US | EU |
|---|---|---|
| Label source | `rx_db.get_prescriber_labels("US")` or `rx_config.get_labels("US")` | `rx_db.get_prescriber_labels("EU")` or `rx_config.get_labels("EU")` |
| Prescriber ID label | "NPI Number" | "Prescriber Reg #" |
| Drug code label | "NDC Code" | "PZN Code" |
| Insurance label | "BIN Number" | "Scheme/PCN" |
| State field label | "State License" | "Professional Register" |
| DAW code | visible, default "00" | hidden or "N/A" |
| Claim data fields | `prescriber_npi`, `insurance_id` | `prescriber_ods`, `nhs_number` |
| Strategy | `USBillingStrategy` | `EUBillingStrategy` |

The module reads the region at module load time and registers a `ConfigManager.register_listener()` callback to rebuild labels on region change.

---

## 3. Integration Strategy

### 3.1 Approach: Non-Invasive Monkey-Patching via `main_app.py`

The integration follows the **exact same architecture** as `ui_enterprise_settings.py` and `ui_pos_terminal.py`, which are already wired through `_wire_rx_extensions()` in `archive/main_app.py`.

### 3.2 Step-by-Step Development Roadmap

#### Phase 1: i18n Key Addition

1. Add all new keys listed in §2.6 to `archive/locales/en.json` (English values)
2. Add translated values to `archive/locales/de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`
3. Keys already present (`group_number`, `quantity`, `save`, `cancel`, `search`, `clear`) are NOT re-added

#### Phase 2: Create `archive/ui_rx_processing.py`

1. **Module header & imports**
   - `import logging`, `import os`, `import sys`, `import sqlite3`, `import json`
   - `from datetime import datetime`
   - `import customtkinter as ctk`
   - `from tkinter import ttk, messagebox`
   - `import i18n`
   - Import backend (all optional/try-except guarded):
     - `from rx_config import ConfigManager, get_labels, encrypt_secret, decrypt_secret`
     - `from rx_strategies import strategy_factory`
     - `from rx_db import search_inventory, get_all_inventory, get_inventory_item, add_rx, add_rx_regional, get_rxs_by_status, get_rx_by_id, update_rx_status, update_rx_filled, get_rx_status_counts, search_prescribers, get_all_prescribers, get_insurance_by_patient, set_region_config, get_region_config, get_prescriber_labels, RX_STATUSES, HAS_SQLALCHEMY`
     - `import database` (for `get_all_patients`, `get_patient_by_id`, `get_db_path`)
     - `import barcode_logic` (for `load_config`)
     - `import audit_log` (for `log_action`)
     - `from ui_helpers import apply_treeview_style`
     - `from async_ui import AsyncUI` (with try/except fallback)

2. **Module-level helper functions** (§2.5)
   - `_get_archive_dir()`, `_get_rx_region()`, `_load_patients()`, `_load_inventory()`, `_load_prescribers()`, `_load_insurance()`
   - `_fetch_rxs_by_status()` (wraps `rx_db.get_rxs_by_status`)
   - `_fetch_rxs_for_queue()` (maps queue name → statuses, calls `get_rxs_by_status` for each)
   - `_ensure_rx_tables()` (idempotent `rx_db.init_rx_tables()`)

3. **`RxProcessingFrame(ctk.CTkFrame)` class**
   - `__init__`: Initialize state vars (§2.3), call `_build_ui()`
   - `_build_ui`: Grid with 3 rows (title, main workspace, queue tabs); `pack_propagate(False)` on fixed-height elements
   - `_build_patient_lookup_panel`: Search entry + Treeview + detail frame; uses `AsyncUI` for search
   - `_build_prescriber_panel`: Search entry + Treeview + detail frame; labels from `get_prescriber_labels(region)`
   - `_build_drug_selection_panel`: Search entry + Treeview (13 columns from inventory_extended) + detail frame
   - `_build_sig_entry_panel`: SIG entry, qty, days supply, refills, DAW code, notes
   - `_build_action_bar`: "Process / Bill" button (green), patient cost display, insurance cost display
   - `_build_queue_tabs`: `ttk.Notebook` or `ctk.CTkTabview` with 3 tabs; each tab has a Treeview with queue-specific columns + context menu
   - Event handlers: `_on_patient_search`, `_on_patient_select`, `_on_drug_search`, `_on_drug_select`, `_on_prescriber_search`, `_on_prescriber_select`, `_on_process_bill`, `_on_queue_action`, `_refresh_queue`, `_refresh_all_queues`
   - `refresh()`: called from `on_tab_change` — refreshes all queues + clears selection cache

4. **Tab setup function**
   ```python
   def setup_rx_processing_tab(self):
       frame = RxProcessingFrame(self.tab_rx_processing, fg_color="transparent")
       frame.pack(fill="both", expand=True, padx=4, pady=4)
       frame.refresh()
       self.rx_processing_frame = frame
   ```

5. **Refresh hook function**
   ```python
   def _refresh_rx_processing_tab(self):
       if hasattr(self, "rx_processing_frame"):
           self.rx_processing_frame.refresh()
   ```

#### Phase 3: Modify `archive/main_app.py`

Add the Rx Processing tab to the existing `_wire_rx_extensions()` function, following the **exact same pattern** as enterprise settings and POS terminal:

**3a. Add Nav Icon** (after line 66-67):
```python
ui_navigation._NAV_ICONS["rx_processing"] = "💊"
```

**3b. Add Import** (after line 75):
```python
from ui_rx_processing import setup_rx_processing_tab
```

**3c. Patch `__init__`** — add inside `_patched_init` (after the existing `setup_pos_terminal_tab(self)` call, ~line 85):
```python
self.tab_rx_processing = self.tab_view.add(i18n.t("rx_processing"))
setup_rx_processing_tab(self)
```

**3d. Patch `on_tab_change`** — add an `elif` branch in `_patched_on_tab_change` (after the `pos_terminal` block, ~line 99):
```python
elif current == i18n.t("rx_processing"):
    if hasattr(self, "rx_processing_frame"):
        self.rx_processing_frame.refresh()
```

**3e. Region sync** — Add a region change listener so the Rx Processing UI updates when Enterprise Settings changes the region:
```python
# In _patched_init, after setup_rx_processing_tab(self):
from rx_config import ConfigManager
cm = ConfigManager()
def _on_region_change(old_region, new_region):
    if hasattr(self, "rx_processing_frame"):
        self.rx_processing_frame._on_region_changed()
cm.register_listener(_on_region_change)
```

**No existing lines in `main_app.py` are removed or restructured.** Only additions are made to the existing `_wire_rx_extensions()` function.

#### Phase 4: Verification

1. **Import smoke test**: `python -c "from ui_rx_processing import RxProcessingFrame, setup_rx_processing_tab"` (run from `archive/` directory)
2. **Backend function smoke test**: Verify all `rx_db`, `rx_config`, `rx_strategies`, `database`, `audit_log` functions are callable with the signatures documented in §1
3. **Strategy routing test**: Instantiate `strategy_factory("US")` and `strategy_factory("GB")` and verify they respond to `calculate_patient_cost()` / `generate_claim()` / `validate_prescription()` / `authenticate()`
4. **Queue status mapping test**: Verify `_fetch_rxs_for_queue("in_processing")` returns Rx rows with status in (Pending, Billed, Verified)
5. **Layout stress test**: Instantiate `RxProcessingFrame` on a `ctk.CTk()` root, call `root.update_idletasks()`, then log dimensions:
   - Assert queue Treeviews have scrollbar attached
   - Assert action bar has `pack_propagate(False)`
   - Assert main workspace grid has `weight=3` for left column and `weight=1` for right column
6. **Integration test**: Run `main_app.py` (or `main.py`) end-to-end, switch to the new "Rx Processing" tab, verify `refresh()` runs without error
7. **Zero regression**: Run existing test suite `test_rx_config.py`, `test_rx_strategies.py`, `test_rx_database.py` from `archive/`

---

## 4. Constraints Compliance

| Constraint | How Addressed |
|---|---|
| **Backend Immutability** | All 4 backend files (`rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py`) are imported only — functions are called with their existing signatures. No modifications to core logic, classes, or architecture proposed. |
| **UI Consistency** | New module uses identical color variables (`#1a1a2e`, `#2d2d3a`, `#3b82f6`, `#10b981`), same `apply_treeview_style()` helper, same grid layout patterns, same `CTkScrollableFrame`/`CTkTabview`/`ttk.Treeview` components. Global theme (`ctk.set_appearance_mode("Dark")`, `ctk.set_default_color_theme("blue")`) is untouched. |
| **Phase Restriction** | No implementation code is generated in this plan. The plan is written to `.kilo/plans/` and awaits approval before any code is written. |
| **No placeholders/TODOs** | Every function is fully specified with inputs, outputs, and return types in §2.1 and §2.5. |
| **Layout elasticity** | All Treeviews have `ttk.Scrollbar` + `apply_treeview_style()`. Fixed-height elements use `pack_propagate(False)`. Grid weights defined for all containers. |
| **Async non-blocking** | Patient search, inventory search, and queue loading use `AsyncUI.get().run()` with `self.after()` callback marshaling — never touches Tkinter widgets from background threads. |
| **Backend fall-through** | Every `rx_db` call is wrapped in try/except with sqlite3 fallback (same pattern as `ui_pos_terminal.py` lines 360-383). |

---

## 5. Risk Analysis & Mitigations

| Risk | Mitigation |
|---|---|
| `rx_db` import fails (no SQLAlchemy) | All rx_db imports guarded with `try/except ImportError`; `_HAS_RX_DB` flag gates SQLAlchemy-only features; sqlite3 fallback queries defined for inventory/prescriber/insurance lookups |
| `init_rx_tables()` already called by `main_app.py` | Module calls `_ensure_rx_tables()` which is idempotent (CREATE IF NOT EXISTS + try/except ALTER) |
| Region mismatch between ConfigManager and rx_db | `_get_rx_region()` tries ConfigManager first, falls back to `rx_db.get_region_config()`, then hardcodes "US" |
| Treeview column overflow with long drug names | Columns have explicit `width=` set; `stretch=False` on some; horizontal scrollbar available via `Treeview` xscroll (not just yscroll) |
| Queue Treeview data staleness after Process/Bill | `refresh()` calls `_refresh_all_queues()` which re-queries all 3 status groups |
| Strategy `validate_prescription` raises `ValueError` on missing fields | Caught in `_on_process_bill()`, user shown error dialog with specific missing field list |
| Patient has no insurance record | `_load_insurance(patient_id)` returns empty list; insurance fields display as "N/A" or empty |
| Prescriber NPI/DEA null for EU patients | UI dynamically relabels using `get_prescriber_labels(region)` — "Prescriber Reg #" for EU, "State License" field still required in DDL |
| `async_ui.AsyncUI.get()` not initialized | `init_async_ui(root)` is called in `PharmacyApp.__init__` (line 110 of ui.py) before tab setup; if missing, module falls back to synchronous execution |

---

## 6. File Changes Required

| File | Change Type | Description |
|---|---|---|
| `archive/locales/en.json` | Edit (add keys) | Add all new i18n keys from §2.6 |
| `archive/locales/de.json` | Edit (add keys) | Add German translations |
| `archive/locales/es.json` | Edit (add keys) | Add Spanish translations |
| `archive/locales/fr.json` | Edit (add keys) | Add French translations |
| `archive/locales/pt.json` | Edit (add keys) | Add Portuguese translations |
| `archive/locales/ar.json` | Edit (add keys) | Add Arabic translations |
| `archive/ui_rx_processing.py` | **NEW** | Full module (class + setup functions + helpers) |
| `archive/main_app.py` | Edit (additive only) | Add nav icon, import, 2 lines in `_patched_init`, 3 lines in `_patched_on_tab_change`, region listener |

**No backend files modified.** `rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py` — untouched.
