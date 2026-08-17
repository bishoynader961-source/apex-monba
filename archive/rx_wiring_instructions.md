# RX Workflow Integration — Wiring Instructions

## Overview

The Rx Workflow module lives entirely in `archive/` to avoid modifying
existing core modules (`ui.py`, `ui_navigation.py`, `ui_patients_tab.py`,
`database.py`, `db.py`, `main.py`, `main_app.py`, `config.json`).

This document describes how to initialize the Rx tables and wire the
Rx settings frame into the existing application **without modifying** any
constrained files.

---

## 1. Initialize Rx Tables

The Rx tables (`prescriptions`, `patients`, `audit_logs` extensions,
`rx_config`) are created/migrated by calling `rx_database.init_rx_tables()`.
This is safe to invoke at import time — it uses `CREATE TABLE IF NOT EXISTS`
plus idempotent `ALTER TABLE` migrations.

### Option A: Via main_app.py (recommended — non-invasive)

After `main.py` launches the app, the Rx tables can be initialized from
a lightweight bootstrap script:

```python
# In your app startup (after database.init_db() in main.py):
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))

import rx_database
rx_database.init_rx_tables()

# Optionally set a default region:
import rx_db
rx_db.set_region_config("US")
```

### Option B: Standalone initialization script

```bash
python archive/rx_init.py
```

`rx_init.py` contents:

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rx_database import init_rx_tables
from rx_config import ConfigManager
cm = ConfigManager()
cm.set_path(os.path.join(os.path.dirname(__file__), "..", "config.json"))
init_rx_tables()
cm.set("rx_region", cm.get("rx_region", "US"))
print("Rx tables initialized.")
```

---

## 2. Wiring the Settings Frame into main_app.py

Since `ui_settings_tab.py` is a constrained file, the Rx settings frame
can be attached after import in `main_app.py` via a monkey-patch or a
post-initialization hook.

### Non-invasive integration pattern:

```python
# After PharmacyApp is created (e.g., in main_app.py after main.main()):
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))

from rx_integration_settings import RxBillingSettingsFrame
from rx_config import ConfigManager
import barcode_logic

config = barcode_logic.load_config()
config_path = os.path.join(os.path.dirname(__file__), "config.json")

cm = ConfigManager()
cm.set_path(config_path)

# Attach to the settings tab (if it uses a known scrollable frame):
if hasattr(app, "settings_frame"):
    rx_frame = RxBillingSettingsFrame(
        app.settings_frame, config_path,
        width=500, height=400,
        corner_radius=10,
    )
    rx_frame.pack(fill="both", expand=True, padx=10, pady=10)
```

If the settings tab does not expose `settings_frame`, create a new
`ctk.CTkTabview` tab dynamically:

```python
if hasattr(app, "_tabview") and hasattr(app, "setup_settings_tab"):
    rx_tab = app._tabview.add("Rx Billing")
    rx_frame = RxBillingSettingsFrame(
        rx_tab, config_path,
        width=600, height=500,
        corner_radius=10,
    )
    rx_frame.pack(fill="both", expand=True, padx=20, pady=20)
```

---

## 3. Wiring the Rx Workflow Dialog into ui_patients_tab.py

The `_open_rx_dialog` function in `ui_rx_workflow.py` is designed to be
attached to the `PharmacyApp` class the same way other module-level
functions are attached (mirroring the pattern in `ui.py:303`):

```python
# In a post-import hook (does NOT modify ui.py):
from archive import ui_rx_workflow
PharmacyApp._open_rx_dialog = ui_rx_workflow._open_rx_dialog
```

Trigger from a button in any view:

```python
ctk.CTkButton(
    parent, text="New Prescription",
    command=lambda: self._open_rx_dialog()
)
```

---

## 4. Required config.json Additions

No changes to `config.json` are mandatory. The Rx module uses
`ConfigManager.set("rx_region", ...)` to store the region, which is
written back to `config.json` via `ConfigManager.set()`. The default
region is `"US"`.

Optional additions to `config.json` for credential persistence:

```json
{
    "pharmacy_name": "My Pharmacy",
    "font_size": 20,
    "include_price": true,
    "db_path": "pharmacy.db",
    "database_url": "",
    "rx_region": "US"
}
```

---

## 5. Dependency Notes

| Dependency       | Required? | Fallback                              |
|---|---|---|
| `cryptography`   | Optional  | stdlib HMAC-SHA256 XOR stream cipher    |
| `SQLAlchemy`     | Optional  | Raw sqlite3 DDL in `rx_database.py`     |
| `customtkinter`  | Required  | N/A (already in main project)           |
| `singleton`      | N/A       | Not needed — `rx_config.py` has own decorator |

---

## 6. File Inventory

| File                          | Purpose                                    |
|---|---|
| `rx_db.py`                    | SQLAlchemy ORM models + session factory    |
| `rx_database.py`              | sqlite3 fallback layer with `@_db_fallback`|
| `rx_config.py`                | ConfigManager, unit conversions, Fernet    |
| `rx_strategies.py`            | Billing strategies + factory               |
| `ui_rx_workflow.py`           | Prescription dialog UI (Custom Fields)     |
| `rx_integration_settings.py`  | Settings frame for credentials + region  |
| `test_rx_config.py`           | 21 tests — config, units, encryption       |
| `test_rx_database.py`         | 16 tests — schema, CRUD, JSON, GDPR        |
| `test_rx_strategies.py`       | 30 tests — factory, US/EU/Mock strategies  |
| `rx_wiring_instructions.md`   | This file                                  |
