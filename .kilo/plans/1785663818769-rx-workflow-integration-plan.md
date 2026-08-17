# Rx Processing Workflow — Multi-Region Enterprise Plan

## 0. Context Summary

**Codebase location**: `archive/`. App runs from `cd archive` (per `TESTING.md`).

**Tech stack**: Python 3.14.3, SQLAlchemy 2.0.51, SQLite, customtkinter 6.0.0,
Pillow, python-barcode, qrcode, cryptography>=42.0, itsdangerous>=2.1.

**Key patterns observed** (all in `archive/`):
- **DB dual-layer**: `db.py` (SQLAlchemy ORM + `text()` + `get_session()`)
  wrapped by `database.py` (sqlite3 + `@_db_fallback` → tries db.py first).
- **UI tabs**: Each tab = `ui_*_tab.py` with functions taking `self` (PharmacyApp).
  Attached in `ui.py` via `PharmacyApp.setup_x_tab = setup_x_tab`.
- **Custom Fields** (`ui_patients_tab.py:125-239`): CTkComboBox + CTkEntry + remove
  button per row, `field_rows` list, `add_field_row()`, `_remove_field()`,
  `_repack_fields()`, "+ Add Field" button. **This is the immutable standard.**
- **BarcodeListener** (`barcode_listener.py`): Inter-key timing detects scanner input.
- **Audit log** (`audit_log.py`): `audit_logs` table; `init_audit_db()` is idempotent.
- **Design system colors** (`ui_navigation.py`): sidebar `#1e1e2e`, cards `#2d2d3a`.

**Constraints**: Cannot modify `ui.py`, `ui_navigation.py`, `ui_patients_tab.py`,
`database.py`, `db.py`, `audit_log.py`, `config.json`, `barcode_listener.py`,
or the application theme. All new code goes in new files under `archive/`.

---

## Delivery Structure (as requested)

1. Configuration Manager & Strategy Pattern Architecture
2. Relational Database Schema
3. Decoupled UI Layout Implementation

---

## 1. Configuration Manager & Strategy Pattern Architecture

### 1.1 ConfigManager Singleton (`archive/rx_config.py`)

Manages regional state (`'US'` or `'EU'`) at runtime — **no hardcoded env vars**.

```python
class ConfigManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._config_path = os.path.join(get_resource_path("."), "rx_config.json")
        self._listeners = []
        self._defaults = {
            "region": "US",
            "unit_system": "imperial",  # US=imperial, EU=metric
            "compliance": "HIPAA",       # US=HIPAA, EU=GDPR
            "labels": REGION_LABELS,     # dict below
        }
        self._load_or_create()
        self._initialized = True
```

**Core API**:
| Method | Returns | Purpose |
|---|---|---|
| `get_region()` | `str` | `'US'` or `'EU'` |
| `set_region(region)` | void | Persists + notifies listeners (triggers UI relabel) |
| `get_unit_system()` | `'imperial'`/`'metric'` | Weight/height units |
| `convert_weight(value, from_u, to_u)` | `float` | lb↔kg (1 lb = 0.453592 kg) |
| `convert_height(value, from_u, to_u)` | `float` | in↔cm (1 in = 2.54 cm) |
| `is_hipaa()` | `bool` | True if region == US |
| `is_gdpr()` | `bool` | True if region == EU |
| `get_label(key)` | `str` | Dynamic UI label (e.g. `"NPI Number"` vs `"Prescriber Reg #"`) |
| `register_listener(cb)` | void | Callback called on region change for live UI updates |
| `get_credential(service)` | `str` | Decrypt & return stored API key/cert path |
| `set_credential(service, value)` | void | Encrypt & persist credential |

**Label registry** (`REGION_LABELS` dict):
```python
REGION_LABELS = {
    "US": {
        "prescriber_id_label": "NPI Number",
        "patient_dob_label": "Date of Birth (MM/DD/YYYY)",
        "weight_label": "Weight (lb)",
        "height_label": "Height (in)",
        "drug_code_label": "NDC Code",
        "insurance_bin_label": "BIN Number",
        "state_field_label": "State License",
    },
    "EU": {
        "prescriber_id_label": "Prescriber Reg #",
        "patient_dob_label": "Date of Birth (DD/MM/YYYY)",
        "weight_label": "Weight (kg)",
        "height_label": "Height (cm)",
        "drug_code_label": "PZN Code",
        "insurance_bin_label": "Scheme/PCN",
        "state_field_label": "Professional Register",
    },
}
```

**Credential storage**: Uses `cryptography.fernet.Fernet`. Key derived from
`license_gate.get_device_mac()` (existing HWID) + app salt, stored in
`rx_secrets.json`. In dev mode (no license gate), falls back to env var
`RX_SECRET_KEY` or a dev default.

### 1.2 Strategy Pattern (`archive/rx_strategies.py`)

Abstract base + concrete implementations + factory.

```python
from abc import ABC, abstractmethod

class PharmacyIntegrationStrategy(ABC):
    """Abstract base for regional pharmacy integration strategies."""

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the regional clearinghouse / API."""

    @abstractmethod
    def verify_medicine(self, drug_code: str, lot: str, expiry: str) -> dict:
        """EU FMD: verify medicine batch/serial against safety features.
           US: validate NDC format and check against DEA watchlist.
           Returns {'verified': bool, 'details': str, 'warnings': list}"""

    @abstractmethod
    def submit_claim(self, claim_data: dict) -> dict:
        """US NCPDP: submit insurance claim.
           EU: submit stock-verification request to national system.
           Returns {'status': str, 'transaction_id': str, 'amount': float}"""

    @abstractmethod
    def get_capabilities(self) -> dict:
        """Return metadata about what this strategy supports."""
```

**Concrete implementations**:

| Class | Region | Key Methods |
|---|---|---|
| `USBillingStrategy` | US | `authenticate()` → NCPDP SCRIPT SOAP; `verify_medicine()` → NDC check + DEA; `submit_claim()` → NCPDP 5.1 JSON |
| `EUBillingStrategy` | EU | `authenticate()` → EU FMD hub; `verify_medicine()` → FMD batch/serial/expiry verification; `submit_claim()` → national reimbursement |
| `MockProvider` | Both | All methods return canned test data; never makes real network calls |

**Factory function**:
```python
def create_integration_strategy(region: str = None) -> PharmacyIntegrationStrategy:
    """Resolve the correct strategy based on ConfigManager region.
    Uses 'Bring Your Own Credentials' — reads encrypted API keys from
    ConfigManager.get_credential()."""
    if region is None:
        region = ConfigManager().get_region()

    if region == "EU":
        creds = ConfigManager().get_credential("eu_fmd_api_key")
        if not creds:
            return MockProvider("EU")
        return EUBillingStrategy(creds)
    elif region == "US":
        creds = ConfigManager().get_credential("us_ncpdp_api_key")
        if not creds:
            return MockProvider("US")
        return USBillingStrategy(creds)
    else:
        return MockProvider("US")
```

### 1.3 Files in Phase 1

| File | Purpose |
|---|---|
| `archive/rx_config.py` | ConfigManager singleton + REGION_LABELS + credential encryption |
| `archive/rx_strategies.py` | PharmacyIntegrationStrategy ABC + USBillingStrategy + EUBillingStrategy + MockProvider + factory |
| `archive/test_rx_config.py` | unittest: region persistence, unit conversion, label resolution, credential encrypt/decrypt round-trip |
| `archive/test_rx_strategies.py` | unittest: factory resolution, mock fallback when no creds, strategy method contracts |

---

## 2. Relational Database Schema

### 2.1 Multi-Region Table DDL

All tables use `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` with try/except
for idempotent migrations (same pattern as `database.py:init_db()` lines 56-90).
Foreign keys to the existing `patients` table use `REFERENCES patients(id)`.
Each connection sets `PRAGMA foreign_keys=ON`.

#### `prescriber_table` (with regional_metadata JSON)

```sql
CREATE TABLE IF NOT EXISTS prescriber_table (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    npi             TEXT,                           -- US NPI (nullable for EU)
    dea_number      TEXT,                           -- US DEA (nullable for EU)
    state_license   TEXT NOT NULL,                  -- US: state license; EU: professional register
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    phone           TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    address         TEXT DEFAULT '',
    dea_expiration  TEXT DEFAULT '',
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT '',
    regional_metadata TEXT DEFAULT '{}'             -- JSON: US {npi, dea} | EU {registration_id, qualification}
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prescriber_npi ON prescriber_table(npi) WHERE npi IS NOT NULL AND npi != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_prescriber_dea ON prescriber_table(dea_number) WHERE dea_number IS NOT NULL AND dea_number != '';
```

#### `inventory_extended` (NDC / PZN formats)

```sql
CREATE TABLE IF NOT EXISTS inventory_extended (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ndc_code        TEXT UNIQUE NOT NULL,           -- US NDC or EU PZN
    drug_name       TEXT NOT NULL,
    strength        TEXT DEFAULT '',
    dosage_form     TEXT DEFAULT '',
    ndc_formatted   TEXT DEFAULT '',                -- US: 00015-0411-01 | EU: 01234568
    awp             REAL DEFAULT 0.0,
    mac             REAL DEFAULT 0.0,
    lot_number      TEXT DEFAULT '',
    expiration_date TEXT DEFAULT '',
    on_hand         INTEGER DEFAULT 0,
    supplier        TEXT DEFAULT '',
    regional_metadata TEXT DEFAULT '{}'             -- JSON: {region, code_format, pzn_check_digit, ...}
);
```

#### `rx_table` (with regional_metadata JSON, status queue, auto-gen Rx number)

```sql
CREATE TABLE IF NOT EXISTS rx_table (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rx_number       TEXT UNIQUE NOT NULL,           -- Auto: RX-YYYY-MM-NNNNNN
    patient_id      INTEGER NOT NULL,
    prescriber_id   INTEGER NOT NULL,
    drug_ndc        TEXT NOT NULL,                  -- FK to inventory_extended.ndc_code
    days_supply     INTEGER DEFAULT 0,
    daw_code        TEXT DEFAULT '00',              -- US NCPDP DAW code
    refills_remaining INTEGER DEFAULT 0,
    sig_code        TEXT DEFAULT '',                -- Directions (Sig)
    quantity        INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'Pending',       -- Pending→Billed→Filled→Verified→Will Call
    date_prescribed TEXT DEFAULT '',
    date_started    TEXT DEFAULT '',
    date_filled     TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    regional_metadata TEXT DEFAULT '{}'             -- JSON: US {claim_id, pcn} | EU {fmd_verification, nhs_number}
    FOREIGN KEY (patient_id)   REFERENCES patients(id),
    FOREIGN KEY (prescriber_id) REFERENCES prescriber_table(id),
    FOREIGN KEY (drug_ndc)     REFERENCES inventory_extended(ndc_code)
);
```

#### `insurance_table` (with regional_metadata JSON)

```sql
CREATE TABLE IF NOT EXISTS insurance_table (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL,
    bin_number      TEXT,                           -- US BIN (nullable for EU)
    pcn             TEXT,                           -- Processor Control Number
    group_number    TEXT,
    plan_name       TEXT DEFAULT '',
    carrier         TEXT DEFAULT '',
    regional_metadata TEXT DEFAULT '{}'             -- JSON: EU {nhs_number, eligibility} | US {processing_status}
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);
```

#### `audit_logs` — Extension for HIPAA/GDPR compliance

Extend the **existing** `audit_logs` table (created by `audit_log.py`):

```sql
ALTER TABLE audit_logs ADD COLUMN region TEXT DEFAULT 'US';
ALTER TABLE audit_logs ADD COLUMN category TEXT DEFAULT '';  -- access|modify|delete|export
ALTER TABLE audit_logs ADD COLUMN subject_type TEXT DEFAULT '';  -- patient|rx|prescriber|inventory|insurance
ALTER TABLE audit_logs ADD COLUMN subject_id INTEGER DEFAULT NULL;
ALTER TABLE audit_logs ADD COLUMN rx_id INTEGER DEFAULT NULL;
ALTER TABLE audit_logs ADD COLUMN old_value TEXT DEFAULT '';
ALTER TABLE audit_logs ADD COLUMN new_value TEXT DEFAULT '';
ALTER TABLE audit_logs ADD COLUMN role TEXT DEFAULT 'user';
ALTER TABLE audit_logs ADD COLUMN gdpr_deleted INTEGER DEFAULT 0;  -- GDPR: hard-delete flag
```
Each `ALTER TABLE` wrapped in `try/except sqlite3.OperationalError` (duplicate column → skip).

**GDPR hard-delete capability**: `rx_database.gdpr_hard_delete_patient(patient_id)` —
physically DELETEs audit_logs rows where `subject_type='patient' AND subject_id=patient_id`.
This contrasts with HIPAA which requires retention — the `region` column determines policy.

### 2.2 SQLAlchemy ORM Models (`rx_db.py`)

**NOTE**: `rx_db.py` was already partially created. The implementation agent MUST
update it to add:
- `regional_metadata` column (SQLAlchemy `Text` type, serialized as JSON) on
  `Prescriber`, `InventoryExtended`, `RxTable`, `Insurance`
- `region`, `category`, `subject_type`, `subject_id`, `rx_id`, `old_value`,
  `new_value`, `role`, `gdpr_deleted` columns on the AuditLog model
- Conditional uniqueness on NPI/DEA (SQLite doesn't enforce partial unique indexes
  via ORM; use raw DDL in `init_rx_tables()`)

**Models** (add the `regional_metadata` column to each):
```python
class Prescriber(Base):
    __tablename__ = "prescriber_table"
    id = Column(Integer, primary_key=True, autoincrement=True)
    npi = Column(String(20), nullable=True)        # nullable for EU
    dea_number = Column(String(20), nullable=True) # nullable for EU
    state_license = Column(String(50), nullable=False)
    # ... existing fields ...
    regional_metadata = Column(Text, default="{}")

class InventoryExtended(Base):
    __tablename__ = "inventory_extended"
    ndc_code = Column(String(20), unique=True, nullable=False)
    # ... existing fields ...
    regional_metadata = Column(Text, default="{}")

class RxTable(Base):
    __tablename__ = "rx_table"
    rx_number = Column(String(30), unique=True, nullable=False)
    # ... existing fields ...
    regional_metadata = Column(Text, default="{}")

class Insurance(Base):
    __tablename__ = "insurance_table"
    bin_number = Column(String(20), nullable=True)  # nullable for EU
    # ... existing fields ...
    regional_metadata = Column(Text, default="{}")
```

### 2.3 Database Query Functions (`rx_database.py`)

Mirror the `database.py` + `db.py` dual-layer pattern. `rx_db.py` provides
SQLAlchemy implementations; `rx_database.py` provides sqlite3 with
`@_db_fallback` decorator.

**New functions for multi-region support**:

| Function | Purpose |
|---|---|
| `set_region_config(region)` | Store region preference in DB (table: `rx_config`) |
| `get_region_config()` | Read current region from DB |
| `add_prescriber_regional(region, **fields)` | Insert prescriber with regional_metadata |
| `get_prescriber_regional(prescriber_id)` | Return prescriber + parsed regional_metadata JSON |
| `add_inventory_item_regional(region, **fields)` | Insert inventory with NDC/PZN regional_metadata |
| `add_rx_regional(region, patient_id, prescriber_id, drug_ndc, **fields)` | Insert Rx with regional_metadata |
| `get_rx_status_counts()` | Dict `{status: count, total: N}` (existing) |
| `gdpr_hard_delete_patient(patient_id)` | Physically delete audit_logs for patient |
| `hipaa_log_access(subject_type, subject_id, role, pin)` | HIPAA-compliant access log entry |
| `get_prescriber_labels(region)` | Return region-appropriate field labels from DB |

**JSON handling**: For sqlite3 fallback, serialize with `json.dumps()` and
deserialize with `json.loads()`. For SQLAlchemy, use `text()` queries with
parameter binding — SQLAlchemy `JSON` type maps to `TEXT` in SQLite.

### 2.4 Rx Number Auto-Generation

Format: `RX-{YYYY-MM}-{NNNNNN}` (6-digit sequential, resets per year-month).
```python
def _generate_rx_number():
    # Query MAX(rx_number) WHERE rx_number LIKE 'RX-YYYY-MM-%' in same transaction
    # Extract sequence, increment, format as RX-2024-08-000042
```

### 2.5 Files in Phase 2

| File | Purpose |
|---|---|
| `archive/rx_db.py` | SQLAlchemy ORM (UPDATE existing — add regional_metadata + audit columns) |
| `archive/rx_database.py` | sqlite3 + `_db_fallback` → rx_db (NEW) |
| `archive/test_rx_database.py` | unittest: table existence, FK integrity, JSON regional_metadata round-trip, GDPR delete, Rx number uniqueness |

---

## 3. Decoupled UI Layout Implementation

### 3.1 Module: `ui_rx_workflow.py`

**Entry point**: `setup_rx_workflow(self, parent_frame)`

Takes the `PharmacyApp` instance (`self`) and any parent frame (e.g. a new
tab created via `self.tab_view.add("Rx Workflow")`).

### 3.2 Layout Hierarchy

```
parent_frame (grid)
├── Row 0: top_ribbon (height=52, pack_propagate(False))
│   └── 6 CTkButtons: Intake | Adjudication | DUR | Filling | Verification | POS
│       (active: fg="#3b82f6" text=white; inactive: fg="transparent" text="#a0a0a0")
├── Row 1: center_container (grid_weight=1)
│   ├── left: main_content (weight=1) — packs sub-views
│   └── right: right_sidebar (width=210, pack_propagate(False))
│       ├── "Workflow Status" header
│       ├── Counter labels per status (queried via ConfigManager.get_label)
│       │   e.g. "12 Pending", "3 Rejected", "45 Filled"
│       └── Total counter (auto-refresh every 30s via self.after())
└── Row 2: status_bar (height=24, optional) — Rx number + region indicator
```

**Grid config**:
```python
parent_frame.grid_columnconfigure(0, weight=1)
parent_frame.grid_columnconfigure(1, weight=0)  # sidebar fixed
parent_frame.grid_rowconfigure(1, weight=1)
```

### 3.3 View Switching (geometry-safe)

```python
WORKFLOW_STAGES = ["Intake", "Adjudication", "DUR", "Filling", "Verification", "POS"]

def _switch_rx_view(self, stage):
    # Destroy old view entirely — prevents pack/grid conflicts
    if self._rx_current_view is not None:
        self._rx_current_view.destroy()
    self._rx_current_view = ctk.CTkFrame(self.rx_main_content, fg_color="transparent")
    self._rx_current_view.pack(fill="both", expand=True)

    view_map = {
        "Intake": _setup_intake_view,
        "Adjudication": _setup_adjudication_view,
        "DUR": _setup_dur_view,
        "Filling": _setup_filling_view,
        "Verification": _setup_verification_view,
        "POS": _setup_pos_view,
    }
    builder = view_map.get(stage)
    if builder:
        builder(self, self._rx_current_view)

    # Barcode listener only active on Intake
    if stage == "Intake":
        self._rx_barcode_listener.start()
    else:
        self._rx_barcode_listener.stop()
```

### 3.4 Dynamic Localization

Every UI label queries `ConfigManager().get_label(key)`:
```python
from rx_config import ConfigManager
cm = ConfigManager()

# Patient section header changes by region:
label = cm.get_label("drug_code_label")  # "NDC Code" (US) / "PZN Code" (EU)

# Unit display:
weight_label = cm.get_label("weight_label")  # "Weight (lb)" / "Weight (kg)"
auto_converted = cm.convert_weight(150, "lb", "kg")  # → 68.04
```

When region changes, `ConfigManager.set_region()` notifies registered listeners:
```python
def _on_region_changed(self):
    # Relabel all visible UI elements
    cm = ConfigManager()
    self.rx_prescriber_label.configure(text=cm.get_label("prescriber_id_label"))
    # ... relabel other fields ...
    self._refresh_rx_dashboard()  # Recount may differ by region
```

### 3.5 Intake View (Task 3)

Built by `_setup_intake_view(self, parent)` — three color-tinted sections
in a scrollable `CTkScrollableFrame`.

**Color tints** (subtle on dark theme):
| Section | bg fg_color | Left border | Accent |
|---|---|---|---|
| Patient (Green) | `#223222` | `#22c55e` (border_width=3, border_color) | success |
| Prescriber (Red) | `#322323` | `#ef4444` | error |
| Drug (Blue) | `#202a35` | `#3b82f6` | blue |

**Patient section fields** (Green):
- Patient search dropdown (CTkComboBox populated from `database.get_all_patients()`)
- "+ New Patient" button → opens standard Add Patient modal (not modified)
- DOB entry, Phone entry, Emergency Contact
- **Dynamic Custom Fields** below (exact replica of `ui_patients_tab.py:125-239`):
  - `DEFAULT_RX_PATIENT_FIELDS = ["Allergies", "Insurance", "Notes", "Blood Type"]`
  - combobox + value entry + remove button per row, "+ Add Field" button

**Prescriber section fields** (Red):
- Prescriber search dropdown (from `rx_database.get_all_prescribers()`)
- "+ New Prescriber" button → opens a prescriber entry modal (using the SAME
  Custom Fields pattern, NOT modifying the patient modal)
- Prescriber ID field (label changes: "NPI Number" / "Prescriber Reg #")
- DEA / Registration ID, State License / Professional Register, Phone, Email

**Drug section fields** (Blue):
- **Barcode scanner search entry** (auto-focused by RxBarcodeListener)
- Drug name, NDC/PZN code (label from `ConfigManager.get_label("drug_code_label")`)
- Strength, Dosage Form, AWP, MAC, Lot Number, Expiration Date, On Hand
- **Dynamic Custom Fields** (exact replica pattern):
  - `DEFAULT_RX_DRUG_FIELDS = ["Route", "Frequency", "Duration", "Special Instructions"]`

**Barcode Scanner Listener** (`RxBarcodeListener` class):
```python
class RxBarcodeListener:
    """Scoped barcode scanner detector for Rx Workflow Intake view.
    Mirrors barcode_listener.BarcodeListener but auto-focuses the
    Drug/NDC search entry on scan."""
    def __init__(self, app, search_entry, on_scan_callback):
        # Same inter-key timing detection (50ms threshold)
    def start(self): app.bind("<Key>", self._on_key, add="+")
    def stop(self):  app.unbind("<Key>"); app.unbind("<Return>")
    def _on_key(self, event): ...  # buffer rapid keystrokes
    def _on_return(self, event):   # auto-focus + populate drug field
        code = "".join(self._buffer)
        self._buffer.clear()
        if len(code) >= 3:
            self.search_entry.focus()
            self.search_entry.insert(0, code)
            self.on_scan(code)
```

**Integration with data layer**: On scan, calls
`rx_database.search_inventory(code)` or `database.search_products(code)` to
auto-populate drug fields from DB.

### 3.6 Integrations & Credentials Settings View (`rx_integration_settings.py`)

A secure settings frame within the Rx Workflow (accessible via a gear icon
in the right sidebar or a dedicated "Settings" ribbon sub-view).

**UI elements**:
- Region selector: CTkSegmentedButton ["US", "EU"] (triggers ConfigManager.set_region)
- Credential inputs (password-style Entry):
  - US: NCPDP API Key, BIN/PCN, Switch ID
  - EU: FMD API Key, Professional Register ID, Certificate path (file picker)
- "Test Connection" button → calls `strategy.authenticate()`
- "Save" button → encrypts via ConfigManager.set_credential() and persists

**Security**: All API keys encrypted with Fernet (key derived from HWID).
Stored in `rx_secrets.json` (never in plaintext).

### 3.7 Files in Phase 3 & 4

| File | Purpose |
|---|---|
| `archive/ui_rx_workflow.py` | Complete Rx Workflow UI (ribbon, sidebar, view switching, Intake view, Adjudication/DUR/Filling/Verification/POS placeholders) |
| `archive/ui_rx_workflow.py` (intake section) | Intake view built inside `setup_rx_workflow` — includes `RxBarcodeListener` + 3 color-tinted sections + Custom Fields pattern |
| `archive/rx_integration_settings.py` | Integrations & Credentials settings frame |
| `archive/test_rx_ui.py` | UI smoke tests: instantiate on Tk root, verify layout geometry, verify label switching |

---

## 4. Integration Steps (existing app — user adds these lines)

**In `ui.py`** (one addition — does NOT modify existing sidebar/modules/theme):
```python
# After existing tab setup (line 154):
from ui_rx_workflow import setup_rx_workflow

self.tab_rx_workflow = self.tab_view.add("Rx Workflow")
setup_rx_workflow(self, self.tab_rx_workflow)
```

**In `main.py`** (one addition):
```python
import rx_db
rx_db.init_rx_tables()
```

**No existing files are modified.** The new tab appears as a new button in
the navigation drawer (via the existing `create_navigation_system` pattern).
The left sidebar navigation continues to work unchanged.

---

## 5. Validation Plan

### 5.1 Database Tests (`test_rx_database.py`)
```python
class TestRxDatabase(unittest.TestCase):
    def setUp(self): use temp DB; init_rx_tables()
    def test_tables_exist(self): all 5 new tables + audit_logs extended columns
    def test_fk_constraints(self): insert Rx with bad patient_id → IntegrityError
    def test_regional_metadata_json(self): add_rx_regional('EU', ...) then read back JSON
    def test_rx_number_uniqueness(self): add 2 Rxs → different numbers
    def test_add_prescriber_us_eu(self): US (npi set, dea set) vs EU (npi NULL, metadata has registration_id)
    def test_gdpr_hard_delete(self): add audit entry → gdpr_hard_delete_patient → entry gone
    def test_status_counts(self): add 3 Rxs in different statuses → correct dict
    def test_update_status_audit_trail(self): update_rx_status → audit_logs has entry
```

### 5.2 Config Tests (`test_rx_config.py`)
```python
class TestRxConfig(unittest.TestCase):
    def test_singleton(self): ConfigManager() is ConfigManager()
    def test_region_persistence(self): set_region('EU') → reload → still 'EU'
    def test_unit_conversion(self): convert_weight(154, 'lb', 'kg') ≈ 69.85
    def test_labels(self): US → 'NPI Number', EU → 'Prescriber Reg #'
    def test_credential_encrypt_decrypt(self): set_credential → get_credential round-trip
```

### 5.3 Strategy Tests (`test_rx_strategies.py`)
```python
class TestStrategies(unittest.TestCase):
    def test_factory_us(self): create_integration_strategy('US') → USBillingStrategy or MockProvider
    def test_factory_eu(self): create_integration_strategy('EU') → EUBillingStrategy or MockProvider
    def test_mock_verify_medicine(self): MockProvider.verify_medicine() → {'verified': True, ...}
    def test_mock_submit_claim(self): MockProvider.submit_claim({}) → {'status': 'approved', ...}
```

### 5.4 UI Tests (`test_rx_ui.py`)
- Instantiate `setup_rx_workflow` on a Tk root with `.withdraw()`
- Run `_debug_layout_geometry()`: assert sidebar ≥ 200px, ribbon = 52px, no clipping
- Test label switching: set region EU → verify labels change to "Prescriber Reg #"

### 5.5 Run Commands
```bash
cd archive
python test_rx_database.py
python test_rx_config.py
python test_rx_strategies.py
python -c "import rx_db; rx_db.init_rx_tables(); print('Schema OK')"
```

---

## 6. File Inventory (All NEW — no existing files modified)

| File | Phase | Pattern Of |
|---|---|---|
| `archive/rx_config.py` | 1 | Config singleton (like `config.json` reader in `db.py`) |
| `archive/rx_strategies.py` | 1 | Strategy pattern (new, no existing equivalent) |
| `archive/rx_db.py` | 2 | `db.py` (UPDATE existing partial file — add regional_metadata + audit columns) |
| `archive/rx_database.py` | 2 | `database.py` (new file — sqlite3 + `_db_fallback`) |
| `archive/ui_rx_workflow.py` | 3 | `ui_checkout_tab.py` + `ui_modals.py` (new file) |
| `archive/rx_integration_settings.py` | 3 | `ui_settings_tab.py` (new file) |
| `archive/test_rx_config.py` | 1 | `test_server.py` pattern |
| `archive/test_rx_database.py` | 2 | `test_server.py` pattern |
| `archive/test_rx_strategies.py` | 1 | `test_server.py` pattern |
| `archive/test_rx_ui.py` | 3 | Manual geometry verification |

---

## 7. Constraints Checklist

- [x] Left sidebar navigation NOT modified
- [x] Existing modules NOT modified (only new files created)
- [x] Application theme NOT changed (uses existing dark/blue CTk theme)
- [x] "Add Patient" modal NOT modified (unchanged in `ui_patients_tab.py`)
- [x] Custom Fields pattern treated as standard (replicated verbatim in all new
      dynamic field implementations)
- [x] Region resolved dynamically at runtime via ConfigManager (not env vars)
- [x] All 5 new tables have `regional_metadata` JSON column
- [x] Audit log supports both HIPAA (retention) and GDPR (hard-delete)
- [x] Strategy pattern enables US NCPDP + EU FMD via factory
- [x] UI dynamically relabels based on ConfigManager region

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `ALTER TABLE audit_logs` conflicts if column exists | try/except `sqlite3.OperationalError` — same as database.py init_db |
| FK to `patients` fails on fresh DB (patients table empty) | FK is structural; insert prescriber/inventory/Rx before linking to patient |
| Regional label mismatch | All labels go through `ConfigManager.get_label()` — single source of truth |
| Credential storage insecure | Fernet encryption with HWID-derived key; never plaintext |
| View switching geometry crash | Always `destroy()` old frame; never mix pack/grid on same parent |
| Barcode listener conflict with global listener | RxBarcodeListener only binds when Intake is active; unbinds on switch |
| `rx_db.py` partial file needs updating | Plan §2.2 documents exact columns to add |
