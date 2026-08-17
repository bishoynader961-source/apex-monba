# Architectural Plan: Web-Based EPCS & Prescription Creation Workflow Module

> **Status:** Planning — awaiting approval before any implementation code is written.
> **Target File:** `archive/ui_epcs_workflow.py`
> **Integration Point:** `archive/main_app.py` via `_wire_rx_extensions()` monkey-patching
> **Phase:** Planning (no implementation code generated per Phase Restriction)

---

## 1. Executive Summary

A new **3-step prescription wizard** (`EpcsWorkflowFrame`) will be integrated into the PharmacyPro desktop application as a new tab, providing an Electronic Prescription for Controlled Substances (EPCS) creation workflow. Unlike the existing `RxProcessingFrame` (a multi-panel form with billing + queue management), this module is a **linear wizard** that guides the user through patient selection → medication selection → prescription details + authorization, with four terminal action buttons.

**Key distinction from `ui_rx_processing.py`:**
- Wizard-based (stepped) vs. all-fields-visible (panel-based)
- Multiple action outcomes (Draft / Print-Fax / Inbox / Submit-Authorize) vs. single "Process/Bill" action
- Web-based EPCS authorization via `strategy_factory(region).authenticate()` vs. local billing
- Veterinarian prescriber support (NPI-null prescribers) as first-class concept vs. NPI-required prescribers

**Backend files (`rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py`) are LOCKED:**
only import and call existing functions. No modifications to their core logic, classes, or schema.

---

## 2. Technical Analysis

### 2.1 Backend API Inventory (LOCKED — Import Only)

#### `rx_config.py` — Configuration & Encryption
| Function | Signature | Return |
|---|---|---|
| `ConfigManager()` | — | singleton |
| `cm.get_region()` | — | str (`"US"`/`"GB"`/`"DE"`) |
| `cm.set_region(region)` | str | void (calls listeners with `(old, new)`) |
| `cm.is_hipaa()` / `cm.is_gdpr()` | — | bool |
| `cm.register_listener(callback)` | callable `(old, new)` | void |
| `cm.set_credential(service, value, region=None)` | str, str, str? | void (Fernet-encrypted) |
| `cm.get_credential(service, region=None)` | str, str? | str (decrypted plaintext) |
| `get_labels(region)` | str | dict |
| `REGION_LABELS` | — | dict |
| `encrypt_secret(plaintext)` | str | str |
| `decrypt_secret(token)` | str | str |

#### `rx_db.py` — SQLAlchemy ORM Layer (Primary)
| Function | Signature | Return |
|---|---|---|
| `HAS_SQLALCHEMY` | — | bool |
| `get_session()` | — | `@contextmanager` yielding session |
| `init_rx_tables()` | — | void (idempotent DDL) |
| `search_inventory(query)` | str | `list[tuple]`: `(id, ndc_code, drug_name, strength, dosage_form, ndc_formatted, awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata_json)` |
| `get_all_inventory()` | — | list of same tuples |
| `get_inventory_item(ndc_code)` | str | tuple or None (same 13-element schema) |
| `add_rx(patient_id, prescriber_id, drug_ndc, days_supply=0, daw_code="00", refills=0, sig_code="", quantity=0, date_prescribed="", notes="", regional_metadata=None)` | (int,int,str,int,str,int,str,int,str,str,dict?) | int (rx_id) |
| `add_rx_regional(region, patient_id, prescriber_id, drug_ndc, **fields)` | str,int,int,str,**kw | int (rx_id) |
| `get_rx_by_id(rx_id)` | int | 16-tuple: `(id, rx_number, patient_id, prescriber_id, drug_ndc, days_supply, daw_code, refills_remaining, sig_code, quantity, status, date_prescribed, date_started, date_filled, notes, regional_metadata_json)` |
| `get_rxs_by_status(status)` | str | list of 16-tuples |
| `get_rxs_by_patient(patient_id)` | int | list of 16-tuples |
| `get_rx_status_counts()` | — | dict `{status: count, total: N}` |
| `update_rx_status(rx_id, new_status, user_pin="", role="user", region="US", subject_type="rx", subject_id=None)` | int, str, ... | bool |
| `update_rx_filled(rx_id, user_pin="", role="user", region="US")` | int, ... | bool |
| `get_rx_audit_log(rx_id, limit=100)` | int, int | list of audit tuples |
| `search_prescribers(query)` | str | `list[tuple]`: `(id, npi, dea_number, state_license, first_name, last_name, phone, email, address, dea_expiration, is_active, regional_metadata_json)` |
| `get_all_prescribers()` | — | list of same 12-tuples |
| `get_prescriber_by_id(prescriber_id)` | int | tuple or None |
| `get_prescriber_regional(prescriber_id)` | int | dict with parsed `regional_metadata` |
| `get_prescriber_by_npi(npi)` | str | tuple or None |
| `add_prescriber(npi, dea_number, state_license, first_name, last_name, phone="", email="", address="", dea_expiration="", regional_metadata=None)` | ... | int |
| `add_prescriber_regional(region, **fields)` | str, **kw | int |
| `add_insurance(patient_id, bin_number, pcn, group_number, plan_name="", carrier="", regional_metadata=None)` | int, str, str, str, ... | int |
| `get_insurance_by_patient(patient_id)` | int | list of 8-tuples: `(id, patient_id, bin_number, pcn, group_number, plan_name, carrier, regional_metadata_json)` |
| `add_inventory_item(ndc_code, drug_name, ...)` | ... | int |
| `update_inventory_on_hand(ndc_code, on_hand)` | str, int | bool |
| `set_region_config(region)` | str | void |
| `get_region_config()` | — | str or None |
| `get_prescriber_labels(region)` | str | dict |
| `REGION_LABELS` | — | dict |
| `RX_STATUSES` | — | `("Pending", "Billed", "Filled", "Verified", "Will Call", "Rejected")` |

#### `rx_database.py` — sqlite3 Fallback Layer (Legacy Prescriptions)
| Function | Signature | Return |
|---|---|---|
| `init_rx_tables()` | — | void (creates its own `prescriptions`, `patients` tables) |
| `add_prescription(patient_id, drug_name, dosage, quantity, custom_fields=None)` | int, str, str, str, dict? | int (rx_id) |
| `get_prescription_by_id(rx_id)` | int | tuple or None |
| `update_prescription(rx_id, update_fields=None)` | int, dict | void |
| `get_prescriptions_by_patient(patient_id)` | int | list of dicts |
| `search_prescriptions(query)` | str | list of dicts |
| `delete_prescription(rx_id)` | int | void |
| `get_distinct_rx_field_names()` | — | list of str |

**IMPORTANT distinction:** `rx_database.py` has its own `prescriptions` table (simple: `patient_id, drug_name, dosage, quantity, status, regional_metadata`). `rx_db.py` has the full `rx_table` (16 columns, linked to `prescriber_table` and `inventory_extended`). For the EPCS wizard the **primary** path is `rx_db.add_rx()` / `rx_db.add_rx_regional()` since it supports prescriber linkage, NDC drug codes, and claim metadata. `rx_database.py` is the fallback layer when SQLAlchemy is unavailable.

#### `rx_strategies.py` — Billing Strategy Pattern
| Function/Class | Signature | Return |
|---|---|---|
| `strategy_factory(region="US")` | str | `USBillingStrategy` / `EUBillingStrategy` / `MockProvider` |
| `strategy.authenticate(credentials)` | dict | `(bool, str)` |
| `strategy.validate_prescription(prescription_data)` | dict | bool (raises `ValueError` on failure) |
| `strategy.generate_claim(claim_data)` | dict | dict (claim payload) |
| `strategy.calculate_patient_cost(unit_price, quantity, insurance_coverage)` | float, int, dict? | float |

#### `audit_log.py` — Compliance Logging
| Function | Signature | Return |
|---|---|---|
| `audit_log.log_action(action, details, user_pin)` | str, str, str | void |

#### Shared Modules
| Module | Function | Usage |
|---|---|---|
| `database` | `get_all_patients(search_query=None)` | Patient search/listing → `[(pid, name, phone, email, created_at, {fields})]` |
| `database` | `get_patient_by_id(patient_id)` | Patient detail lookup |
| `database` | `get_db_path()` | sqlite3 fallback path resolution |
| `i18n` | `t(key, **kwargs)` | Translation lookup |
| `ui_helpers` | `apply_treeview_style(tree)` | ttk.Treeview styling (odd/even tags) |
| `async_ui` | `AsyncUI.get().run(func, callback, args, kwargs)` | Non-blocking DB search |
| `async_ui` | `init_async_ui(root)` | Called in `PharmacyApp.__init__` (ui.py:110) |

### 2.2 Existing UI Module Patterns (Reference Architecture)

Both `ui_rx_processing.py` and `ui_pos_terminal.py` follow this **exact contract**:

```
# Module-level:
log = logging.getLogger("ui_<name>")
_COLOR constants (COLOR_CARD_DARK, COLOR_CARD_MED, COLOR_BG, COLOR_ACCENT, ...)
_MODULE-level helper functions with rx_db → sqlite3 fallback pattern

# Class:
class <Name>Frame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._region = _get_rx_region()
        self._build_ui()
        self._register_region_listener()

    def refresh(self):           # ← called from on_tab_change hook
        ...

# Module-level setup hook:
def setup_<name>_tab(self):
    frame = <Name>Frame(self.tab_<name>, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    self.<name>_frame = frame

def _refresh_<name>_tab(self):
    if hasattr(self, "<name>_frame"):
        self.<name>_frame.refresh()
```

**Monkey-patching pattern in `main_app.py` `_wire_rx_extensions()`:**
1. `ui_navigation._NAV_ICONS["<key>"] = "<emoji>"`
2. `from ui_<name> import setup_<name>_tab`
3. In `_patched_init`, after original:
   - `self.tab_<name> = self.tab_view.add(i18n.t("<key>"))`
   - `setup_<name>_tab(self)`
4. In `_patched_on_tab_change`, add `elif current == i18n.t("<key>"): self.<name>_frame.refresh()`

**Search → Treeview → Detail pattern** (from both modules):
- Search entry with `trace_add("write", ...)` or `<KeyRelease>` binding
- `AsyncUI.get().run(func=_do_search, callback=_on_search_done, args=(query,))`
- Callback clears Treeview, iterates results, inserts with `"even"`/`"odd"` tags
- Treeview `show="headings"`, columns set with explicit `.column()` widths
- `ttk.Scrollbar` + `yscrollcommand` on every Treeview
- `apply_treeview_style()` applied to all Treeviews

### 2.3 Region & Prescriber Model

- `ConfigManager.get_region()` returns `"US"` (default), `"GB"`, or `"DE"`
- Region change fires registered listeners with `(old_region, new_region)`
- `rx_db.REGION_LABELS[region]` provides region-aware field labels:
  - US: `prescriber_id_label="NPI Number"`, `drug_code_label="NDC Code"`, `insurance_bin_label="BIN Number"`, `state_field_label="State License"`
  - EU: `prescriber_id_label="Prescriber Reg #"`, `drug_code_label="PZN Code"`, `insurance_bin_label="Scheme/PCN"`, `state_field_label="Professional Register"`
- `rx_db.RX_STATUSES` = `("Pending", "Billed", "Filled", "Verified", "Will Call", "Rejected")`
- Prescriber `npi` is **nullable** (NULL for EU prescribers without NPI; also NULL for veterinarians)
- `state_license` is **NOT NULL** — universal identifier across all prescriber types

### 2.4 Data Flow Reference

From `FLOW_LOGIC.md §8` (Rx Workflow Data Flow):
- **Dual-Layer DB Access:** UI calls `rx_database.py` functions → `@_db_fallback` decorator tries `rx_db.py` SQLAlchemy ORM first; falls back to raw `sqlite3.Row` queries. Both use `PRAGMA foreign_keys = ON`.
- **Regional Strategy:** `rx_config.ConfigManager` loads region → `rx_strategies.strategy_factory(region)` returns strategy → UI applies region-specific labels from `rx_config.get_labels()` / `rx_db.get_prescriber_labels()`.

---

## 3. EPCS Workflow Module Architecture

### 3.1 Module Structure

```
ui_epcs_workflow.py
├── MODULE-LEVEL CONSTANTS
│   ├── COLOR_* constants (identical to ui_rx_processing.py: #1a1a2e, #2d2d3a, #2b2b2b, etc.)
│   ├── _VALID_REGIONS = ["US", "GB", "DE"]
│   ├── _WIZARD_STEPS = ["step_patient", "step_medication", "step_prescription"]
│   └── _DRAFT_STATUS = "Pending"  # Rx created as draft, not yet billed
│
├── MODULE-LEVEL HELPERS (rx_db → sqlite3 fallback pattern)
│   ├── _get_archive_dir() → str
│   ├── _get_rx_region() → str  (ConfigManager.get_region() → rx_db.get_region_config() → "US")
│   ├── _ensure_rx_tables() → void
│   ├── _load_patients(search="") → list  (database.get_all_patients())
│   ├── _load_inventory(query="") → list  (rx_db.search_inventory() + sqlite3 fallback)
│   ├── _load_prescribers(query="") → list (rx_db.search_prescribers() + sqlite3 fallback)
│   ├── _get_patient_detail(patient_id) → tuple (database.get_patient_by_id())
│   ├── _get_drug_detail(ndc_code) → tuple (rx_db.get_inventory_item())
│   ├── _get_prescriber_detail(prescriber_id) → dict (rx_db.get_prescriber_regional())
│   ├── _create_prescription(...) → int  (rx_db.add_rx_regional() / rx_db.add_rx())
│   └── _resolve_prescriber_display(row) → (name, id_label, license_val, phone)
│       # Handles vet NPI-null: displays DEA or state_license as primary ID
│
├── class EpcsWorkflowFrame(ctk.CTkFrame)
│   ├── __init__(self, master, **kwargs)
│   ├── _register_region_listener()
│   ├── _on_region_changed(self)
│   ├── _build_ui(self)                    # Wizard container + step indicator + stacked pages
│   ├── _build_wizard_header(self, parent)  # Title + step breadcrumb
│   ├── _build_step_patient(self, parent)  # Step 1: Patient search + Treeview + detail
│   ├── _build_step_medication(self, parent) # Step 2: Drug search + Treeview + detail
│   ├── _build_step_prescription(self, parent) # Step 3: Form fields + prescriber + actions
│   ├── _build_action_bar(self, parent)     # Back/Next + Draft/Print/Authorize buttons
│   ├── _on_patient_search(self, event=None)
│   ├── _on_patient_search_done(self, results, error=None)
│   ├── _on_patient_select(self, event=None)
│   ├── _on_drug_search(self, event=None)
│   ├── _on_drug_search_done(self, results, error=None)
│   ├── _on_drug_select(self, event=None)
│   ├── _on_prescriber_search(self, event=None)
│   ├── _on_prescriber_search_done(self, results, error=None)
│   ├── _on_prescriber_select(self, event=None)
│   ├── _on_next(self)                     # Validate step, advance wizard
│   ├── _on_back(self)                     # Go back one step
│   ├── _on_save_draft(self)               # Create Rx with status="Pending", note="DRAFT"
│   ├── _on_print_fax(self)                # Generate printable prescription
│   ├── _on_save_inbox(self)              # Create Rx with status="Pending", metadata.inbox=True
│   ├── _on_submit_authorize(self)        # EPCS auth → claim → rx_db.add_rx → update_rx_status
│   ├── _on_clear_form(self)
│   ├── _update_step_indicator(self)      # Highlight active step
│   ├── _validate_step(self, step) → bool  # Required fields per step
│   ├── _refresh_labels(self)             # Update region-aw labels
│   ├── _update_cost_display(self)        # Patient/insurance cost labels
│   └── refresh(self)                      # Called from on_tab_change
│
├── Module-level setup hooks
│   ├── setup_epcs_workflow_tab(self)
│   └── _refresh_epcs_workflow_tab(self)
│
└── No monkey-patching of own methods (unlike ui_rx_processing's _build_queue_tabs patch)
```

### 3.2 Wizard State Machine

The wizard uses a **stacked-frame pattern** (not a CTkTabview): three `ctk.CTkFrame` pages are created in a container, and only the active one is `tkraise()`-d to the front. This gives precise control over step transitions and allows validation before advancing.

```
WizardContainer (parent=frame, uses .pack or .grid)
├── self._step_pages: dict[str, ctk.CTkFrame]
│   ├── "step_patient"      → populated by _build_step_patient()
│   ├── "step_medication"   → populated by _build_step_medication()
│   └── "step_prescription" → populated by _build_step_prescription()
├── self._current_step: str = "step_patient"
```

**State variables on `self` (all initialized in `__init__`):**

| Variable | Type | Purpose |
|---|---|---|
| `self._current_step` | str | Active wizard step key |
| `self._step_pages` | dict[str, Frame] | Three step page frames |
| `self._step_indicator` | CTkFrame | Visual breadcrumb (3 numbered circles + labels) |
| `self._region` | str | Current region from `_get_rx_region()` |
| `self._labels` | dict | `get_labels(self._region)` for region-aware labels |
| `self._selected_patient_id` | int\|None | Selected patient PK |
| `self._selected_patient` | tuple\|None | Full patient tuple from `database.get_all_patients()` |
| `self._selected_drug_ndc` | str\|None | Selected inventory NDC code |
| `self._selected_drug` | tuple\|None | Full inventory tuple from `rx_db.search_inventory()` |
| `self._drug_awp` | float | AWP for cost calculation |
| `self._selected_prescriber_id` | int\|None | Selected prescriber PK |
| `self._selected_prescriber` | tuple\|None | Full prescriber tuple |
| `self._prescriber_display_cache` | dict | Cached parsed prescriber details |
| `self._qty_var` | StringVar | Quantity |
| `self._frequency_var` | StringVar | Dosage frequency (e.g., "BID", "TID") |
| `self._directions_var` | StringVar | Directions/SIG (free text) |
| `self._duration_var` | StringVar | Duration in days |
| `self._refills_var` | StringVar | Refills remaining |
| `self._notes_var` | StringVar | Special notes |
| `self._patient_cost_val` | float | From strategy calculation |
| `self._insurance_cost_val` | float | Computed |
| `self._claim_data` | dict\|None | Claim payload from `generate_claim()` |
| `self._strategy` | strategy\|None | Cached strategy instance |
| `self._draft_rx_id` | int\|None | Rx ID if saved as draft (for resubmit) |

### 3.3 CustomTkinter Layout

The frame uses a **single-column grid** (like `ui_rx_processing.py`):

```
EpcsWorkflowFrame (grid, single column)
├── Row 0: Header
│   ├── CTkLabel "EPCS Workflow" (CTkFont size=24, weight="bold")
│   └── CTkLabel subtitle (text_color="#94a3b8")

├── Row 1: Step Indicator (breadcrumb)
│   ├── self._step_indicator (CTkFrame, transparent)
│   │   ├── [● Step 1: Patient] → [● Step 2: Medication] → [● Step 3: Prescription]
│   │   └── CTkProgressBar or segmented indicator showing progress

├── Row 2: Wizard Container (EXPANDS — weight=1)
│   ├── self._wizard_container (CTkFrame, fg_color="transparent")
│   │   └── self._step_pages["step_patient"]      (stacked, active shown via tkraise)
│   │   └── self._step_pages["step_medication"]   (stacked)
│   │   └── self._step_pages["step_prescription"] (stacked)

├── Step 1 Page Layout (step_patient):
│   ├── Patient Search Card (fg=COLOR_CARD_DARK)
│   │   ├── CTkEntry (search, placeholder="Search patients...")
│   │   ├── Treeview results (Patient | Phone | Email | DOB) + Scrollbar
│   │   └── Detail frame (read-only labels: name, DOB, phone, email, address, insurance)

├── Step 2 Page Layout (step_medication):
│   ├── Drug Search Card (fg=COLOR_CARD_DARK)
│   │   ├── CTkEntry (search, placeholder="Search NDC/PZN or drug name...")
│   │   ├── Treeview results (NDC | Drug | Strength | Form | AWP | On Hand | Lot | Expiry) + Scrollbar
│   │   └── Detail frame (full drug metadata)

├── Step 3 Page Layout (step_prescription):
│   ├── Prescription Form Card (fg=COLOR_CARD_MED)
│   │   ├── Prescriber search (entry + Treeview)  ← "Veterinarian/Prescriber"
│   │   ├── Quantity entry
│   │   ├── Frequency entry (preset dropdown: QD, BID, TID, QID, QHS, etc.)
│   │   ├── Directions/SIG entry (multiline)
│   │   ├── Duration entry (days)
│   │   ├── Refills entry (default 0)
│   │   ├── Special Notes entry (multiline)
│   │   ├── DAW Code entry (region-aware: visible for US, hidden/grayed for EU)
│   │   └── Cost preview (Patient Cost / Insurance Cost labels)

├── Row 3: Action Bar (fixed height, pack_propagate(False))
│   ├── CTkButton "Back" (gray)
│   ├── CTkButton "Next" (blue)
│   ├── CTkButton "Save in Draft" (amber, visible on step 3)
│   ├── CTkButton "Print/Fax" (gray, enabled when Rx exists or is valid)
│   ├── CTkButton "Save to Inbox" (gray, visible on step 3)
│   └── CTkButton "Submit/Authorize" (green, visible on step 3)
```

**Action bar button visibility rules:**
- Steps 1–2: Only "Back" (or hidden on step 1) + "Next"
- Step 3: "Back" + "Next"(hidden/disabled) + "Save in Draft" + "Print/Fax" + "Save to Inbox" + "Submit/Authorize"

**Layout elasticity guarantees** (per VERIFICATION_CHECKLIST.md):
- All Treeviews have `ttk.Scrollbar` + `apply_treeview_style()`
- `pack_propagate(False)` on the fixed-height action bar
- Grid weights on the wizard container so it expands/shrinks with window
- `tkraise()` for step switching — no widget creation/destruction per step

### 3.4 Wizard State Management

The wizard does **not** persist intermediate state to the database until an action button is clicked. All selections are held in-memory on `self`.

**Step advancement validation:**
- Step 1 → Step 2: `self._selected_patient_id is not None`
- Step 2 → Step 3: `self._selected_drug_ndc is not None`
- Step 3 actions: require patient + prescriber + drug + quantity + directions

**EPCS authorization flow (`_on_submit_authorize`):**
```
1. Validate all required fields (patient, prescriber, drug, qty, directions)
2. region = _get_rx_region()
3. strategy = strategy_factory(region)  — cached on self._strategy
4. Build claim_data dict:
   {
       "drug_name": drug_name,
       "ndc": self._selected_drug_ndc,
       "quantity": qty,
       "days_supply": int(duration) if duration else 0,
       "prescriber_npi" or "prescriber_ods": prescriber_identifier,
       "pharmacy_npi": from barcode_logic.load_config(),
       "insurance_id": from rx_db.get_insurance_by_patient(patient_id),
   }
5. Build prescription_data dict (for validate_prescription):
   {
       "drug_name": drug_name,
       "dosage": directions,
       "quantity": qty,
       "prescriber_npi" or "prescriber_ods": prescriber_identifier,
   }
6. strategy.authenticate(credentials)
   → credentials from cm.get_credential("api_key", region) etc.
   → if (False, msg): show error, abort
7. strategy.validate_prescription(prescription_data)
   → if ValueError: show error, abort
8. strategy.generate_claim(claim_data)
   → self._claim_data = result
9. strategy.calculate_patient_cost(unit_price=awp, quantity=qty, insurance_coverage)
   → self._patient_cost_val, self._insurance_cost_val
10. rx_db.add_rx_regional(region, patient_id, prescriber_id, drug_ndc,
       days_supply=int(duration), daw_code=daw, refills=int(refills),
       sig_code=directions, quantity=int(qty), date_prescribed=now,
       notes=notes, regional_metadata={claim_id, pcn, etc.})
   → rx_id
11. rx_db.update_rx_status(rx_id, "Billed", user_pin="", role="user", region=region)
   → bool
12. audit_log.log_action("EPCS_SUBMIT", f"Rx #{rx_id} authorized and submitted")
13. Show success: "Rx #{rx_id} submitted and authorized — Patient pays $X.XX"
14. self._on_clear_form()
```

**Draft save flow (`_on_save_draft`):**
```
1. Validate required fields
2. rx_id = rx_db.add_rx_regional(region, patient_id, prescriber_id, drug_ndc,
       days_supply, daw_code, refills, sig_code=directions, quantity, date_prescribed=now,
       notes="[DRAFT] " + notes, regional_metadata={"region": region, "draft": True})
3. audit_log.log_action("EPCS_DRAFT", f"Rx #{rx_id} saved as draft")
4. Show: "Draft saved — Rx #{rx_id}"
5. Clear form, set self._draft_rx_id = rx_id
```

**Inbox save flow (`_on_save_inbox`):**
```
1. Validate required fields
2. Same as draft but metadata={"region": region, "inbox": True, "inbox_timestamp": now}
   and notes tag "[INBOX]"
3. audit_log.log_action("EPCS_INBOX", f"Rx #{rx_id} saved to inbox")
```

**Print/Fax flow (`_on_print_fax`):**
```
1. Validate the form is complete
2. If no Rx exists yet (not submitted), still allow printing the prescription form
3. Generate a printable prescription using existing label/thermal print infrastructure:
   - Reuse barcode_logic.create_label() or receipt_engine patterns
   - Include: patient name, drug name/strength/dosage, SIG, qty, refills, prescriber, date
4. If an Rx ID exists (draft/inbox), include rx_number on the printout
```

### 3.5 Prescriber (Veterinarian) Selection

The prescriber search in Step 3 uses `rx_db.search_prescribers(query)` which returns 12-tuples with a **nullable** `npi` field.

**Display logic (`_resolve_prescriber_display(row)`):**
```python
name = f"{row[4]} {row[5]}".strip()       # first_name + last_name
npi = row[1] or ""                          # may be NULL for vets
dea = row[2] or ""                         # DEA (may exist for vets with controlled substances)
license_val = row[3] or ""                 # state_license (always present)
phone = row[6] or ""

# Primary ID label: show NPI if present, else DEA, else "License: <state_license>"
if npi:
    id_label_val = npi
elif dea:
    id_label_val = dea
else:
    id_label_val = f"License: {license_val}"
```

This handles:
- **Medical prescribers (US):** NPI present → displayed as primary ID
- **EU prescribers:** NPI may be NULL → DEA or state license shown
- **Veterinarians:** NPI NULL, DEA may be present (for controlled substances) → DEA or license shown

The prescriber Treeview displays columns: `Prescriber | NPI/ID | License | Phone`
On selection, `rx_db.get_prescriber_regional(prescriber_id)` is called to get the parsed dict (with `regional_metadata` as a proper dict), which can contain vet-specific fields in the JSON.

### 3.6 Search Asynchronicity (AsyncUI)

All three search entry points follow the `ui_rx_processing.py` / `ui_pos_terminal.py` pattern:

```python
# In _build_step_patient / _build_step_medication / _build_step_prescription:
self._patient_search_var = ctk.StringVar()
self._patient_search_var.trace_add("write", lambda *_: self._on_patient_search())

def _on_patient_search(self, event=None):
    query = self._patient_search_var.get().strip()
    if not query:
        self._tree_patients.delete(*self._tree_patients.get_children())
        # Optionally: load all if empty
        return
    if _HAS_ASYNC:
        AsyncUI.get().run(
            func=lambda q: _load_patients(q),
            callback=self._on_patient_search_done,
            args=(query,),
        )
    else:
        results = _load_patients(query)
        self._on_patient_search_done(results, None)

def _on_patient_search_done(self, results, error=None):
    # Runs on main thread — safe to touch TK widgets
    for item in self._tree_patients.get_children():
        self._tree_patients.delete(item)
    if error or not results:
        return
    for idx, row in enumerate(results):
        tag = "even" if idx % 2 == 0 else "odd"
        # extract fields from row tuple
        self._tree_patients.insert("", "end", values=(name, phone, email, dob), tags=(tag,))
```

A **debounce** mechanism is recommended (300ms delay) on the `trace_add` callback to avoid firing a search on every keystroke. This is NOT present in the existing modules but is a best-practice addition for the wizard's patient search (which queries `database.get_all_patients()` — a heavier query than rx_db inventory search).

### 3.7 sqlite3 Fallback Patterns

Every `rx_db` / `database` call is wrapped in `try/except` with a raw `sqlite3` fallback query, exactly mirroring `ui_rx_processing.py` (lines 121-371). The fallback queries operate on the same tables:

| Primary API (rx_db) | Fallback Table | Fallback Query Pattern |
|---|---|---|
| `search_inventory(query)` | `inventory_extended` | `WHERE ndc_code LIKE ? OR drug_name LIKE ? OR ndc_formatted LIKE ?` |
| `get_inventory_item(ndc_code)` | `inventory_extended` | `WHERE ndc_code = ?` |
| `search_prescribers(query)` | `prescriber_table` | `WHERE first_name LIKE ? OR last_name LIKE ? OR npi LIKE ? OR dea_number LIKE ? OR state_license LIKE ?` |
| `add_rx(...)` / `add_rx_regional(...)` | `rx_table` | `INSERT INTO rx_table (...) VALUES (...)` with `rx_number` generation |
| `update_rx_status(rx_id, ...)` | `rx_table` | `UPDATE rx_table SET status = ?, date_started = ? WHERE id = ?` |
| `update_rx_filled(rx_id, ...)` | `rx_table` | `UPDATE rx_table SET status = 'Filled', date_filled = ? WHERE id = ?` |

The `add_rx` fallback must generate `rx_number` using the same `RX-YYYY-MM-NNNNNN` pattern as `_generate_rx_number()`.

---

## 4. Backend Function Mapping (EPCS Workflow → Locked APIs)

| Wizard Operation | Backend Function Called | Layer |
|---|---|---|
| Patient search | `database.get_all_patients(search_query)` | database.py |
| Patient detail | `database.get_patient_by_id(patient_id)` | database.py |
| Medication search | `rx_db.search_inventory(query)` | rx_db.py (SQLAlchemy) |
| All medications | `rx_db.get_all_inventory()` | rx_db.py |
| Drug detail | `rx_db.get_inventory_item(ndc_code)` | rx_db.py |
| Inventory on-hand (post-fill) | `rx_db.update_inventory_on_hand(ndc_code, new_value)` | rx_db.py |
| Prescriber search | `rx_db.search_prescribers(query)` | rx_db.py |
| All prescribers | `rx_db.get_all_prescribers()` | rx_db.py |
| Prescriber detail | `rx_db.get_prescriber_by_id(id)` / `rx_db.get_prescriber_regional(id)` | rx_db.py |
| Prescriber labels | `rx_db.get_prescriber_labels(region)` | rx_db.py |
| Region | `rx_config.ConfigManager().get_region()` | rx_config.py |
| Region fallback | `rx_db.get_region_config()` | rx_db.py |
| Region labels | `rx_config.get_labels(region)` | rx_config.py |
| Region change listener | `ConfigManager().register_listener(callback)` | rx_config.py |
| Billing strategy | `rx_strategies.strategy_factory(region)` | rx_strategies.py |
| Auth check | `strategy.authenticate(credentials)` | rx_strategies.py |
| Prescription validation | `strategy.validate_prescription(prescription_data)` | rx_strategies.py |
| Claim generation | `strategy.generate_claim(claim_data)` | rx_strategies.py |
| Patient cost | `strategy.calculate_patient_cost(unit_price, qty, insurance_coverage)` | rx_strategies.py |
| Rx creation (submit) | `rx_db.add_rx_regional(region, ...)` | rx_db.py |
| Rx creation (draft/inbox) | `rx_db.add_rx(...)` | rx_db.py |
| Status transition | `rx_db.update_rx_status(rx_id, new_status, ...)` | rx_db.py |
| Mark filled | `rx_db.update_rx_filled(rx_id, ...)` | rx_db.py |
| Audit log | `audit_log.log_action(action, details)` | audit_log.py |
| Rx lookup (audit trail) | `rx_db.get_rx_audit_log(rx_id, limit)` | rx_db.py |
| Insurance lookup | `rx_db.get_insurance_by_patient(patient_id)` | rx_db.py |
| Rx counts | `rx_db.get_rx_status_counts()` | rx_db.py |
| Config (pharmacy NPI, tax) | `barcode_logic.load_config()` | barcode_logic.py |
| Treeview styling | `ui_helpers.apply_treeview_style(tree)` | ui_helpers.py |
| Async search | `AsyncUI.get().run(func, callback, args)` | async_ui.py |

**No function in any backend file will be called outside its documented signature.** All `rx_db` calls are guarded by `HAS_SQLALCHEMY` checks with sqlite3 fallbacks (same pattern as existing modules).

---

## 5. i18n Requirements

### 5.1 Existing Keys Reused
The following keys already exist in all 6 locale files and are reused without modification:

| Key | English Value |
|---|---|
| `quantity` | Quantity |
| `directions` | Directions |
| `refills` | Refills |
| `days_supply` | Days Supply |
| `daw_code` | DAW Code |
| `draft` | Draft |
| `save` | Save |
| `cancel` | Cancel |
| `search` | Search |
| `clear` | Clear |
| `continue` | Continue |
| `success` | Success |
| `warning` | Warning |
| `error` | Error |
| `patient_lookup` | Patient Lookup |
| `patient_search_placeholder` | Search patients... |
| `drug_selection` | Drug / Product Selection |
| `search_ndc_or_drug` | Search NDC/PZN or drug name... |
| `no_patients_found` | No patients found. |
| `no_drugs_found` | No drugs found in inventory. |
| `prescriber_lookup` | Prescriber Lookup |
| `prescriber_search_placeholder` | Search prescriber by name, NPI, or DEA... |
| `sig_entry` | SIG / Directions |
| `process_bill` | Process / Bill |
| `process_success` | Rx #{rx_number} processed and billed — Patient pays ${cost} |
| `select_patient_first` | Please select a patient first. |
| `missing_fields_error` | Please select a patient, prescriber, and drug, and enter quantity. |
| `patient_cost` | Patient Cost |
| `insurance_cost` | Insurance Cost |
| `clear_form` | Clear Form |
| `submit_claim` | Submit Claim |
| `drug_verification` | Drug Verification |
| `claim_number` | Claim Number |
| `claim_status` | Claim Status |

### 5.2 New i18n Keys to Add (6 files: en, de, es, fr, pt, ar)

| Key | English Value | Used In |
|---|---|---|
| `epcs_workflow` | "EPCS Workflow" | Tab label + nav icon |
| `epcs_workflow_subtitle` | "Electronic prescription creation and EPCS authorization" | Subtitle |
| `step_patient` | "Step 1: Patient Selection" | Wizard step indicator |
| `step_medication` | "Step 2: Medication Selection" | Wizard step indicator |
| `step_prescription` | "Step 3: Prescription Details" | Wizard step indicator |
| `back` | "Back" | Action button |
| `next` | "Next" | Action button |
| `save_draft` | "Save in Draft" | Action button |
| `print_fax` | "Print/Fax" | Action button |
| `save_to_inbox` | "Save to Inbox" | Action button |
| `submit_authorize` | "Submit/Authorize" | Action button |
| `frequency` | "Frequency" | Form field label |
| `duration` | "Duration" | Form field label |
| `duration_days` | "Duration (days)" | Form field label |
| `special_notes` | "Special Notes" | Form field label |
| `veterinarian_prescriber` | "Veterinarian/Prescriber" | Section label |
| `prescriber_search_box_placeholder` | "Search prescriber or veterinarian..." | Search entry placeholder |
| `frequency_placeholder` | "e.g. BID, TID, QID, QD" | Entry placeholder |
| `directions_placeholder` | "e.g. Take 1 tablet by mouth twice daily" | Entry placeholder |
| `notes_placeholder` | "Additional clinical notes..." | Entry placeholder |
| `insufficient_fields` | "Please complete all required fields." | Validation error |
| `draft_saved` | "Draft saved — Rx #{rx_id}" | Success message |
| `inbox_saved` | "Saved to Inbox — Rx #{rx_id}" | Success message |
| `authorize_failed` | "EPCS authorization failed: {error}" | Error message |
| `claim_generated` | "Claim generated — Rx #{rx_id}" | Success message |
| `prescriber_required` | "Please select a prescriber." | Validation error |
| `drug_required` | "Please select a medication." | Validation error |
| `patient_required` | "Please select a patient." | Validation error |
| `print_label` | "Print Label" | Print/fax action |
| `no_prescribers_found` | "No prescribers found." | Alert |
| `select_prescriber_first` | "Please select a prescriber first." | Alert |
| `rx_number_short` | "Rx #" | Column/header label (may reuse `rx_number` if exists) |

> Note: `rx_number` does NOT exist in en.json and must be added. All other new keys are unique.

---

## 6. Integration Strategy (main_app.py Monkey-Patching)

### 6.1 The Integration Pattern

The EPCS Workflow module integrates via the **exact same** architecture as the existing `ui_rx_processing.py` and `ui_pos_terminal.py` modules, through non-invasive monkey-patching in `main_app.py`'s `_wire_rx_extensions()` function.

**Current `_wire_rx_extensions()` structure** (archive/main_app.py:58-108):

```python
def _wire_rx_extensions():
    import i18n
    import ui_navigation
    import ui

    ui_navigation._NAV_ICONS["enterprise_settings"] = "🏢"
    ui_navigation._NAV_ICONS["pos_terminal"] = "🔢"
    ui_navigation._NAV_ICONS["rx_processing"] = "💊"

    # init_rx_tables() called here...

    from ui_enterprise_settings import setup_enterprise_settings_tab
    from ui_pos_terminal import setup_pos_terminal_tab
    from ui_rx_processing import setup_rx_processing_tab

    PharmacyApp = ui.PharmacyApp
    _orig_init = PharmacyApp.__init__

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        self.tab_enterprise = self.tab_view.add(i18n.t("enterprise_settings"))
        self.tab_pos = self.tab_view.add(i18n.t("pos_terminal"))
        self.tab_rx_processing = self.tab_view.add(i18n.t("rx_processing"))
        setup_enterprise_settings_tab(self)
        setup_pos_terminal_tab(self)
        setup_rx_processing_tab(self)

    PharmacyApp.__init__ = _patched_init

    _orig_on_tab_change = PharmacyApp.on_tab_change

    def _patched_on_tab_change(self):
        _orig_on_tab_change(self)
        current = self.tab_view.get()
        if current == i18n.t("enterprise_settings"):
            if hasattr(self, "enterprise_settings_frame"):
                self.enterprise_settings_frame.refresh()
        elif current == i18n.t("pos_terminal"):
            if hasattr(self, "pos_terminal_frame"):
                self.pos_terminal_frame.refresh()
        elif current == i18n.t("rx_processing"):
            if hasattr(self, "rx_processing_frame"):
                self.rx_processing_frame.refresh()

    PharmacyApp.on_tab_change = _patched_on_tab_change
```

### 6.2 Step-by-Step Development Roadmap

#### Phase 1: i18n Key Addition

1. Add all new keys from §5.2 to `archive/locales/en.json` (English values)
2. Add translated values to `archive/locales/de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`
3. Verify no duplicate keys conflict (e.g., `save`, `cancel`, `search` already exist)
4. Verify `rx_number` is NOT already present (it is not — confirmed via key listing)

**Verification:3.1:** `python -c "import i18n; i18n.init(); print(i18n.t('epcs_workflow'))"` prints "EPCS Workflow"

#### Phase 2: Create `archive/ui_epcs_workflow.py`

2a. **Module header & imports** (mirror `ui_pos_terminal.py:18-51`):
```python
import os, sys, json, sqlite3, logging
from datetime import datetime
import customtkinter as ctk
from tkinter import ttk, messagebox
import i18n
import database
import barcode_logic
import audit_log
from ui_helpers import apply_treeview_style
from rx_config import ConfigManager, get_labels
from rx_strategies import strategy_factory
from rx_database import init_rx_tables

try:
    import rx_db as _rx_db
    _HAS_RX_DB = True
except Exception:
    _rx_db = None
    _HAS_RX_DB = False

try:
    from async_ui import AsyncUI
    _HAS_ASYNC = True
except ImportError:
    AsyncUI = None
    _HAS_ASYNC = False

log = logging.getLogger("ui_epcs_workflow")
```

2b. **Color constants & module constants** (identical to `ui_rx_processing.py:69-78`):
```python
COLOR_CARD_DARK = "#1a1a2e"
COLOR_CARD_MED = "#2d2d3a"
COLOR_BG = "#2b2b2b"
COLOR_BG_ALT = "#1e1e1e"
COLOR_ACCENT = "#3b82f6"
COLOR_SUCCESS = "#10b981"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_TEXT_PRIMARY = "#f0f0f0"
COLOR_TEXT_SECONDARY = "#a0a0a0"

_VALID_REGIONS = ["US", "GB", "DE"]
_WIZARD_STEPS = ["step_patient", "step_medication", "step_prescription"]
```

2c. **Module-level helper functions** (§3.1):
- `_get_archive_dir()` — same as `ui_rx_processing.py:81`
- `_get_rx_region()` — same pattern as `ui_rx_processing.py:86`
- `_ensure_rx_tables()` — same as `ui_rx_processing.py:104`
- `_load_patients(search)` — calls `database.get_all_patients(search)`
- `_load_inventory(query)` — calls `rx_db.search_inventory()` + sqlite3 fallback on `inventory_extended`
- `_load_prescribers(query)` — calls `rx_db.search_prescribers()` + sqlite3 fallback on `prescriber_table`
- `_get_patient_detail(patient_id)` — calls `database.get_patient_by_id()`
- `_get_drug_detail(ndc_code)` — calls `rx_db.get_inventory_item()` + sqlite3 fallback
- `_get_prescriber_regional(prescriber_id)` — calls `rx_db.get_prescriber_regional()`
- `_resolve_prescriber_display(row)` — extracts name, id, license, phone; handles NPI-null (veterinarian) case
- `_create_rx(...)` — calls `rx_db.add_rx()` or `rx_db.add_rx_regional()` with sqlite3 fallback for `rx_table`
- `_generate_rx_number_fallback()` — `RX-YYYY-MM-NNNNNN` pattern for sqlite3 fallback

2d. **`EpcsWorkflowFrame(ctk.CTkFrame)` class**:
- `__init__`: Initialize all state vars (§3.2), `_ensure_rx_tables()`, `_build_ui()`, `_register_region_listener()`
- `_build_ui`: Grid with 4 rows (header, step indicator, wizard container [weight=1], action bar [fixed])
- `_build_wizard_header`: Title + subtitle labels
- `_build_step_indicator`: 3 numbered step widgets in a horizontal CTkFrame; calls `_update_step_indicator()`
- `_build_step_patient`: Search entry + Treeview + detail frame (pattern from `ui_rx_processing._build_patient_lookup_panel` but scoped to wizard)
- `_build_step_medication`: Search entry + Treeview + detail frame (pattern from `ui_rx_processing._build_drug_selection_panel`)
- `_build_step_prescription`: Prescriber search + Treeview + form fields (qty, frequency, directions, duration, refills, notes, DAW) + cost display
- `_build_action_bar`: Back/Next buttons (always) + 4 action buttons (Draft/Print/Inbox/Submit, visible only on step 3)
- Event handlers: `_on_patient_search/_done/_select`, `_on_drug_search/_done/_select`, `_on_prescriber_search/_done/_select`, `_on_next`, `_on_back`, `_on_save_draft`, `_on_print_fax`, `_on_save_inbox`, `_on_submit_authorize`, `_on_clear_form`, `_on_step_indicator_click` (optional), `_refresh_labels`, `_update_cost_display`, `_validate_step`
- `refresh()`: Re-read region, refresh labels, reload prescription status counts, clear draft state

2e. **Module-level setup hooks** (exact pattern from `ui_pos_terminal.py:734-752`):
```python
def setup_epcs_workflow_tab(self):
    frame = EpcsWorkflowFrame(
        self.tab_epcs_workflow,
        fg_color="transparent",
    )
    frame.pack(fill="both", expand=True, padx=4, pady=4)
    self.epcs_workflow_frame = frame

def _refresh_epcs_workflow_tab(self):
    if hasattr(self, "epcs_workflow_frame"):
        self.epcs_workflow_frame.refresh()
```

**Verification:3.2:** `python -c "from ui_epcs_workflow import EpcsWorkflowFrame, setup_epcs_workflow_tab"` succeeds (run from `archive/` dir)

#### Phase 3: Modify `archive/main_app.py`

Add the EPCS Workflow tab to `_wire_rx_extensions()`, following the **exact same** additive-only pattern:

**3a. Add Nav Icon** (after the existing `rx_processing` icon, line 67):
```python
ui_navigation._NAV_ICONS["epcs_workflow"] = "📝"
```

**3b. Add Import** (after line 77, the `ui_rx_processing` import):
```python
from ui_epcs_workflow import setup_epcs_workflow_tab
```

**3c. Patch `_patched_init`** — add after the `setup_rx_processing_tab(self)` call (line 89):
```python
self.tab_epcs_workflow = self.tab_view.add(i18n.t("epcs_workflow"))
setup_epcs_workflow_tab(self)
```

**3d. Patch `_patched_on_tab_change`** — add an `elif` branch after the `rx_processing` block (line 106):
```python
elif current == i18n.t("epcs_workflow"):
    if hasattr(self, "epcs_workflow_frame"):
        self.epcs_workflow_frame.refresh()
```

**No existing lines in `main_app.py` are removed or restructured.** Only 4 lines are added.

#### Phase 4: Verification

4.1. **Import smoke test**: `python -c "from ui_epcs_workflow import EpcsWorkflowFrame, setup_epcs_workflow_tab, _refresh_epcs_workflow_tab"`

4.2. **Backend function smoke test**: Verify all referenced `rx_db`, `rx_config`, `rx_strategies`, `database`, `audit_log` functions are callable with documented signatures (§2.1)

4.3. **Strategy routing test**: `strategy = strategy_factory("US")` and `strategy_factory("GB")` — verify they respond to `authenticate()`, `validate_prescription()`, `generate_claim()`, `calculate_patient_cost()`

4.4. **Prescriber display test**: Create mock prescriber rows with NULL NPI (veterinarian) and verify `_resolve_prescriber_display()` shows DEA or state license

4.5. **Wizard step validation test**: Verify `_validate_step("step_patient")` returns False when no patient selected, True when selected; same for step_medication

4.6. **Layout stress test**: Instantiate `EpcsWorkflowFrame` on a `ctk.CTk()` root, call `root.update_idletasks()`, log dimensions:
- Assert all Treeviews have scrollbars attached
- Assert action bar has `pack_propagate(False)`
- Assert wizard container grid has weight=1 (expands)
- Assert step pages use `tkraise()` pattern correctly

4.7. **Integration test**: Run `main_app.py`, switch to "EPCS Workflow" tab, verify `refresh()` runs without error and step indicator is visible

4.8. **Zero regression**: Run existing test suite from `archive/` directory: `test_rx_config.py`, `test_rx_strategies.py`, `test_rx_database.py`

4.9. **Backend immutability check**: Confirm no changes to `rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py` (git diff on these 4 files must be empty)

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `rx_db` not available (SQLAlchemy missing) | All `rx_db` imports guarded with `try/except`; `_HAS_RX_DB` flag gates SQLAlchemy-only features; sqlite3 fallback queries defined for inventory, prescribers, prescription CRUD |
| `init_rx_tables()` already called by main_app.py | Module calls `_ensure_rx_tables()` which calls `rx_database.init_rx_tables()` — both are idempotent (CREATE IF NOT EXISTS) |
| `rx_db.add_rx()` not available in fallback layer | The sqlite3 fallback for prescription creation uses direct `INSERT INTO rx_table` with `rx_number` generation via the `RX-YYYY-MM-NNNNNN` pattern |
| Region mismatch (ConfigManager vs rx_db) | `_get_rx_region()` tries `ConfigManager.get_region()` first, falls back to `rx_db.get_region_config()`, then hardcodes `"US"` — identical to `ui_rx_processing.py:86` |
| Veterinarian NPI is NULL | `_resolve_prescriber_display()` checks NPI field, falls back to DEA, then state license. Treeview "NPI/ID" column handles empty values gracefully |
| Treeview column overflow with long drug names | Columns have explicit `width=` set; `stretch=False` on some; horizontal content clipped via column width with tooltip on hover (optional) |
| Wizard state lost on tab switch | `refresh()` does NOT clear selections — it only re-reads region and refreshes queues/labels. State persists in `self` attributes. Tab switching is cheap. |
| EPCS auth failure (fake/test environment) | `strategy.authenticate()` returns `(False, message)` — UI shows error but does NOT crash. User can still save as draft without auth |
| `AsyncUI` not initialized | `init_async_ui(root)` is called in `PharmacyApp.__init__` (ui.py:110). If unavailable, `_HAS_ASYNC = False` and the module falls back to synchronous execution |
| EPCS submit requires network/API keys | Credentials read from `ConfigManager.get_credential()`. If empty, `authenticate()` fails gracefully with a warning message guiding the user to Enterprise Settings |
| Prescriber search returns too many results | Search is debounced (300ms) and returns max 100 rows; Treeview height=6 with scrollbar |
| rx_number collision in sqlite3 fallback | The `RX-YYYY-MM-NNNNNN` pattern uses `MAX(rx_number)` + 1 within the same year-month, same as `_generate_rx_number()` in rx_db.py |

---

## 8. File Changes Summary

| File | Change Type | Description |
|---|---|---|
| `archive/ui_epcs_workflow.py` | **NEW** | Full EPCS Workflow module (~500-600 lines): `EpcsWorkflowFrame` class, module helpers, wizard state management, 3-step UI, 4 action buttons, EPCS auth flow |
| `archive/main_app.py` | **Edit (additive only)** | Add 4 lines to `_wire_rx_extensions()`: nav icon, import, tab creation + setup call, on_tab_change elif branch |
| `archive/locales/en.json` | **Edit (add keys)** | Add ~28 new i18n keys from §5.2 |
| `archive/locales/de.json` | **Edit (add keys)** | Add German translations |
| `archive/locales/es.json` | **Edit (add keys)** | Add Spanish translations |
| `archive/locales/fr.json` | **Edit (add keys)** | Add French translations |
| `archive/locales/pt.json` | **Edit (add keys)** | Add Portuguese translations |
| `archive/locales/ar.json` | **Edit (add keys)** | Add Arabic translations |
| `rx_config.py` | **LOCKED — no changes** | |
| `rx_database.py` | **LOCKED — no changes** | |
| `rx_strategies.py` | **LOCKED — no changes** | |
| `rx_db.py` | **LOCKED — no changes** | |

---

## 9. Verifiable Goals

1. **Module imports cleanly**: `from ui_epcs_workflow import EpcsWorkflowFrame, setup_epcs_workflow_tab` succeeds with no ImportError
2. **Wizard renders**: `EpcsWorkflowFrame` instantiates on a `ctk.CTkRoot`, all 3 step pages are created, step indicator shows "Step 1 / Step 2 / Step 3"
3. **Patient search works**: Typing in the patient search entry queries `database.get_all_patients()` via `AsyncUI` without blocking the UI thread
4. **Drug search works**: Typing in the medication search queries `rx_db.search_inventory()` with sqlite3 fallback
5. **Prescriber search works**: Prescriber search returns results including veterinarians (NPI-null) with proper display fallback
6. **Step navigation**: "Next" button validates Step 1 (patient selected) before advancing to Step 2; validates Step 2 (drug selected) before advancing to Step 3
7. **Draft save**: "Save in Draft" creates an Rx record with `status="Pending"` and `notes` prefixed with `[DRAFT]`, displays success message with rx_id
8. **Inbox save**: "Save to Inbox" creates an Rx with `regional_metadata={"inbox": True}` and displays success
9. **EPCS submit**: "Submit/Authorize" calls `strategy.authenticate()` → `strategy.validate_prescription()` → `strategy.generate_claim()` → `rx_db.add_rx_regional()` → `rx_db.update_rx_status(rx_id, "Billed")` → `audit_log.log_action()`, with proper error handling at each step
10. **Print/Fax**: "Print/Fax" generates a printable prescription document using existing label/thermal print infrastructure
11. **No regression**: Existing `test_rx_config.py`, `test_rx_strategies.py`, `test_rx_database.py` pass unchanged
12. **Backend immutability**: `git diff` on `rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py` returns empty
