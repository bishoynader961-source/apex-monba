# FLOW_LOGIC

## 1. Authentication Flow
- `main.py` starts `license_gate.py`.
- If `~/.pharmacy_dev.key` exists OR `PHARMACY_DEV_MODE=1` in Env: skip to `PharmacyApp`.
- Else: Check Cache -> Check Remote Server -> Return Valid/Invalid.

## 2. Point of Sale Flow
- Barcode is scanned (keyboard listener catches global input).
- `pos_engine.py` receives barcode -> checks `database.py`.
- If valid: item added to in-memory cart -> UI is updated.
- On Confirm: `pos_engine.py` -> `database.create_receipt()` -> `receipt_engine.generate()`.
- End: Clear cart, notify dashboard/inventory to refresh.

## 3. Database Modifications
- Products are deducted using `internal_unique_barcode` to ensure strict FIFO.
- Batch logic (manufacture/expiry dates) is preserved in `receipt_items`.
