# PROJECT_MAP

## [TECH_STACK]
- UI: CustomTkinter, Tkinter (Treeview)
- DB: SQLite3
- File Handling: openpyxl
- OS Integration: subprocess, sys, os, platform
- Other: hashlib, uuid, json, requests

## [SYSTEM_FLOW]
- **Entry Point:** `main.py` -> `main_app.py`
- **License Gate:** `license_gate.py` intercepts launch, verifies auth.
- **Main App:** `ui.py` sets up `PharmacyApp` and initializes tabs.
- **Tabs:** Dedicated modules (`ui_dashboard_tab.py`, `ui_checkout_tab.py`, etc.) handle GUI.
- **Database:** `database.py` manages all DB ops (Products, Receipts, Patients).
- **Extracted Engines:**
  - `pos_engine.py`: Encapsulates checkout/cart state.
  - `receipt_engine.py`: Generates receipts (PDF/TXT).
  - `backup.py`: DB snapshots.
  - `audit_log.py`: Logs actions.

## [ARCHITECTURE]
- Monolithic desktop app with isolated logic engines.
- Shared state is minimized; UI queries DB or Engines.
- CustomTkinter is used for modern aesthetics. Grid geometry management is preferred.

## [ORPHANS & PENDING]
- [PENDING] Update `license_gate.py` to remove `DEV-PASS` and use Ghost Token/Env Var.
- [PENDING] Establish Smart, Modern UI/UX Design System in `ui.py`.
- [PENDING] Extract `pos_engine.py` from `ui_checkout_tab.py`.
- [PENDING] Extract `receipt_engine.py`.
- [PENDING] Implement `backup.py`.
- [PENDING] Implement `audit_log.py`.
- [PENDING] Update 12 core capabilities.
