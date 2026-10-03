# Demo dataset (fake data for screenshots & sales demos)

ALL data is fake and clearly marked. No real patients, phones, or prescriptions.

## Files
- `seed_demo.json` — the dataset: 20 drugs (with expiry dates), 5 fake patients, 2 fake suppliers, 10 fake receipts (21 line items).
- `load_demo.py` — loads the dataset into a **fresh** SQLite database using the app's own schema/seeding logic, creates a demo admin (`demo`), and sets `setup_complete=true` so the first-run wizard does not block screenshots.
- `pharmacy-demo.db` — generated output (regenerable; safe to delete).

## Usage (from the repo root)

```bash
# 1. Load into the default target (release/demo/pharmacy-demo.db)
backend_fastapi/.venv/Scripts/python release/demo/load_demo.py

# 2. Or point at a custom path
backend_fastapi/.venv/Scripts/python release/demo/load_demo.py --db C:/demos/demo.db

# 3. Reload over an existing demo DB (deletes only DEMO-marked rows first)
backend_fastapi/.venv/Scripts/python release/demo/load_demo.py --clean

# Custom demo password (default: demo-admin-2026 — change before PUBLIC demos)
backend_fastapi/.venv/Scripts/python release/demo/load_demo.py --admin-password 'your-password'
```

The script refuses to overwrite an existing DB without `--clean` (or deleting the file) so it can never touch user data unless you explicitly point `--db` at it.

## Login for demos
- Username: `demo`
- Password: `demo-admin-2026` (or whatever you passed via `--admin-password`)

## Markers (so demo rows are recognizable / cleanable)
- Internal barcodes: `DEMO-P0001`…
- Supplier tax IDs: `DEMO-TAX-001`…
- Patient names end with `(demo)`.
- Receipts were created by user `demo` with `client_tx_id = DEMO-TXnnnn`.
