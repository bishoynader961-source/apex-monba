# Plan: Admin Management CLI & API for Pharmacy Licensing Backend

> **Timestamp:** 2026-08-06 | **Python:** 3.14.3 | **Flask:** 3.1.3 | **SQLite3:** stdlib
> **Status:** Planning — based on M66/M90 foundations (db.py, app.py, Procfile, tests all complete)

---

## 1. Context Assessment

### Already Implemented (M66/M90, verified passing)
| File | Status |
|---|---|
| `backend/db.py` | Complete — `licenses` table (5 cols: license_key, customer_email, order_id, status, hardware_id), `init_db`, `insert_license`, `get_license`, `bind_hardware_id`, `update_license_status`, `clear_licenses`, `set_db_path`. All parameterized. `:memory:` keepalive pattern. |
| `backend/app.py` | Complete — Flask app with `/webhooks/lemon-squeezy` (HMAC-SHA256) + `POST /api/validate` (404/403/400/200 binding logic). Module-level `db.init_db()` call. Dual-mode import (`try: from .db import ... except ImportError: from db import ...`). |
| `backend/test_webhook_lemon_squeezy.py` | Complete — 14/14 tests pass (6 webhook + 8 validate). In-memory DB isolation. |
| `Procfile` | Exists: `web: gunicorn backend.app:app` |
| `.gitignore` | Already includes `*.sqlite`, `*.sqlite3` |
| `requirements.txt` | Already includes `gunicorn>=23.0,<24.0`, `flask>=3.0,<4.0` |

### Missing (This Task)
| Deliverable | Status |
|---|---|
| `backend/admin.py` — CLI tool (list/revoke/reset/generate) | **NOT STARTED** |
| `POST /api/admin/manage` endpoint in `backend/app.py` | **NOT STARTED** |
| `backend/test_admin.py` — tests for CLI + API | **NOT STARTED** |
| `PROJECT_MAP.md` + `FLOW_LOGIC.md` updates | **NOT STARTED** |

### Key Gap: `created_at` column
The `backend/db.py` `licenses` table has **no `created_at` column**. The task's `list` command requires `created_at` in its output. I need to:
1. Add `created_at TEXT DEFAULT CURRENT_TIMESTAMP` to the `licenses` table schema in `db.py`.
2. Update `insert_license` to accept and insert a `created_at` value (or rely on the DEFAULT).
3. Add `get_all_licenses()` helper to `db.py` (used by both CLI `list` and API `list` action).

### Env var naming
Task specifies `ADMIN_SECRET` with default `"default-dev-secret"`. The existing `archive/server_app.py` uses `SERVER_ADMIN_SECRET`. These are **separate systems** — the task explicitly says to use `ADMIN_SECRET`. I will use exactly what the task specifies.

---

## 2. Design Decisions

### D1. `created_at` column — additive, backward-compatible
- Add `created_at TEXT DEFAULT CURRENT_TIMESTAMP` to the `CREATE TABLE` in `db.init_db()`.
- `INSERT INTO licenses` already uses an explicit column list — add `created_at` to it with `CURRENT_TIMESTAMP` via Python `datetime.utcnow().isoformat()`.
- Update `insert_license` signature to accept optional `created_at` param (default `None` → use `CURRENT_TIMESTAMP`).

### D2. New `db.py` helper: `get_all_licenses()`
- Returns all rows ordered by `created_at DESC`.
- Columns: `license_key`, `customer_email`, `order_id`, `status`, `hardware_id`, `created_at`.
- Used by CLI `list` and API `list` action.

### D3. CLI `generate <email>` — no order_id
- The existing `generate_license_key(email, order_id)` requires an `order_id`.
- For the admin CLI, `generate <email>` has no order_id. I'll add a `generate_license_key_direct(email)` function in `app.py` (or call `db.insert_license` directly in admin.py with a generated key).
- **Simplest approach:** `admin.py` generates the key directly (same algorithm as `app.py:generate_license_key`) and calls `db.insert_license`. No need to touch `app.py`'s `generate_license_key`. This keeps `admin.py` self-contained and avoids coupling.

### D4. CLI uses `argparse` with subcommands
- `python backend/admin.py list`
- `python backend/admin.py revoke <key>`
- `python backend/admin.py reset <key>`
- `python backend/admin.py generate <email>`
- Importable functions for testing: `cli_list()`, `cli_revoke(key)`, `cli_reset(key)`, `cli_generate(email)`.

### D5. API endpoint `POST /api/admin/manage`
- Route: `@app.route("/api/admin/manage", methods=["POST"])`
- Auth: `X-Admin-Secret` header checked with `hmac.compare_digest` against `ADMIN_SECRET` env var (default `"default-dev-secret"`).
- Payload: `{"action": "revoke"|"reset"|"list", "license_key": "PHARM-..."}`
- For `list` action: `license_key` not required, returns full list as JSON.
- For `revoke`/`reset`: `license_key` required, returns 404 if not found.
- Status codes: 200 (success), 401 (unauthorized), 400 (invalid/missing action or license_key), 404 (key not found), 500 (DB error).

### D6. Admin secret configuration
- Add `ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "default-dev-secret")` to `app.py` module level (alongside `SIGNATURE_SECRET`).
- Use `hmac.compare_digest` for constant-time comparison.

### D7. Test isolation
- `backend/test_admin.py` uses `db.init_db(":memory:")` pattern (same as existing test file).
- Tests import `db` first, init `:memory:`, then import `app` and `admin`.
- Set `os.environ["ADMIN_SECRET"] = "test-admin-secret"` before importing.

### D8. File layout
- `backend/admin.py` — CLI tool + importable functions.
- `backend/app.py` — add `ADMIN_SECRET` + `/api/admin/manage` route.
- `backend/db.py` — add `created_at` column + `get_all_licenses()`.
- `backend/test_admin.py` — comprehensive tests.

---

## 3. Affected Files

| File | Action | Change Description |
|---|---|---|
| `backend/db.py` | Modify | Add `created_at` column to schema; update `insert_license` to accept optional `created_at`; add `get_all_licenses()` function |
| `backend/app.py` | Modify | Add `ADMIN_SECRET` env var; add `from datetime import datetime` import; add `@app.route("/api/admin/manage")` endpoint |
| `backend/admin.py` | New | `argparse`-based CLI with `list`/`revoke`/`reset`/`generate` subcommands + importable functions |
| `backend/test_admin.py` | New | Unit tests for CLI functions + API endpoint (auth, revoke, reset, list, not-found, DB error) |
| `PROJECT_MAP.md` | Modify | Add `backend/admin.py` to file tree; add M91 milestone row |
| `FLOW_LOGIC.md` | Modify | Add §13C documenting admin CLI + API flow |

---

## 4. Implementation Steps (Ordered)

### Step 1 — Modify `backend/db.py`
1a. Add `created_at TEXT DEFAULT CURRENT_TIMESTAMP` to the `licenses` table schema.
1b. Update `insert_license(license_key, customer_email, order_id, created_at=None)` to accept optional `created_at` param. When `None`, use `datetime.utcnow().isoformat()`.
1c. Add `from datetime import datetime` import.
1d. Add `get_all_licenses()` function returning all rows ordered by `created_at DESC`.

### Step 2 — Modify `backend/app.py`
2a. Add `import hmac` (already present) and `ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "default-dev-secret")` after `SIGNATURE_SECRET`.
2b. Add `@app.route("/api/admin/manage", methods=["POST"])` endpoint below `/api/validate`:
- Check `X-Admin-Secret` header → 401 if missing/invalid.
- Parse JSON → 400 if missing.
- Route on `action` field: `list` / `revoke` / `reset`.
- For `list`: call `db.get_all_licenses()`, return JSON array.
- For `revoke`: call `db.update_license_status(key, "revoked")`, return 200 or 404.
- For `reset`: call `db.clear_hardware_id(key)` — **new helper in db.py**, return 200 or 404.
- Wrap DB ops in `try/except sqlite3.Error` → 500.
2c. Add `clear_hardware_id(license_key)` to `db.py` (sets `hardware_id = NULL`).

### Step 3 — Create `backend/admin.py` (CLI tool)
- `argparse` with subparsers: `list`, `revoke`, `reset`, `generate`.
- `cli_list()` — calls `db.get_all_licenses()`, prints ASCII table.
- `cli_revoke(key)` — calls `db.update_license_status(key, "revoked")` via `db.get_license` existence check.
- `cli_reset(key)` — calls `db.clear_hardware_id(key)`.
- `cli_generate(email)` — generates `PHARM-XXXX-XXXX-XXXX` key, calls `db.insert_license`.
- `main()` — parses args, dispatches to CLI functions.
- ASCII table formatting using string formatting (`| {:<18} | {:<25} | ...`).

### Step 4 — Create `backend/test_admin.py`
Test classes:
- `AdminCLIListTests` — test `cli_list()` output contains expected rows.
- `AdminCLIRevokeTests` — test revoke sets status, output message.
- `AdminCLIResetTests` — test reset clears hardware_id.
- `AdminCLIGenerateTests` — test generate creates new active key.
- `AdminAPIAuthTests` — unauthorized (missing/invalid secret) → 401.
- `AdminAPIRevokeTests` — authorized revoke → 200; key not found → 404.
- `AdminAPIResetTests` — authorized reset → 200; key not found → 404.
- `AdminAPIListTests` — authorized list → 200 with correct data.
- `AdminAPIEdgeCases` — missing action → 400; invalid action → 400; missing license_key for revoke → 400.

### Step 5 — Update `PROJECT_MAP.md`
- Add `backend/admin.py` to §3 root structure tree (line ~354 area).
- Add M91 milestone row in milestones table.
- Update §7 licensing backend section to include `admin.py` and `/api/admin/manage`.

### Step 6 — Update `FLOW_LOGIC.md`
- Add §13C: Admin Management Flow documenting CLI + API.

### Step 7 — Run tests and verify
- `python backend/test_admin.py` → all pass.
- `python backend/test_webhook_lemon_squeezy.py` → 14/14 still pass (no regression).
- Manual CLI test: `python backend/admin.py list` (after seeding DB).

---

## 5. Test Cases (Exact)

### CLI Tests (`backend/test_admin.py`)
| # | Test | Setup | Action | Expected |
|---|---|---|---|---|
| C1 | `test_cli_list_empty` | clear DB | `cli_list()` | prints "No licenses found" |
| C2 | `test_cli_list_with_licenses` | insert 2 keys | `cli_list()` | output contains both keys + email + status + hardware_id |
| C3 | `test_cli_revoke_success` | insert key | `cli_revoke(key)` | status='revoked' in DB, output says "revoked" |
| C4 | `test_cli_revoke_not_found` | empty DB | `cli_revoke("PHARM-NOPE")` | output says "not found" |
| C5 | `test_cli_reset_success` | insert+bind hwid | `cli_reset(key)` | hardware_id=NULL in DB, output says "reset" |
| C6 | `test_cli_reset_not_found` | empty DB | `cli_reset("PHARM-NOPE")` | output says "not found" |
| C7 | `test_cli_generate_creates_active_key` | empty DB | `cli_generate("test@exam.com")` | new key in DB, status='active', hardware_id=NULL |

### API Tests (`backend/test_admin.py`)
| # | Test | Headers | Payload | Expected |
|---|---|---|---|---|
| A1 | `test_api_unauthorized_missing_header` | none | `{"action":"list"}` | 401 |
| A2 | `test_api_unauthorized_wrong_secret` | X-Admin-Secret: wrong | `{"action":"list"}` | 401 |
| A3 | `test_api_list_authorized` | valid secret | `{"action":"list"}` | 200, JSON with licenses array |
| A4 | `test_api_revoke_success` | valid secret | `{"action":"revoke","license_key":"<key>"}` | 200 + DB status='revoked' |
| A5 | `test_api_revoke_not_found` | valid secret | `{"action":"revoke","license_key":"PHARM-NOPE"}` | 404 |
| A6 | `test_api_reset_success` | valid secret | `{"action":"reset","license_key":"<key>"}` | 200 + DB hardware_id=NULL |
| A7 | `test_api_reset_not_found` | valid secret | `{"action":"reset","license_key":"PHARM-NOPE"}` | 404 |
| A8 | `test_api_missing_action` | valid secret | `{}` | 400 |
| A9 | `test_api_invalid_action` | valid secret | `{"action":"delete"}` | 400 |
| A10 | `test_api_revoke_missing_key` | valid secret | `{"action":"revoke"}` | 400 |

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Schema migration** — existing `license_db.sqlite` won't have `created_at`. | `CREATE TABLE IF NOT EXISTS` with new column. For existing DBs, add `ALTER TABLE licenses ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP` in `init_db()` wrapped in try/except (column may already exist). Tests use `:memory:` so always fresh schema. |
| **Admin API on same Flask app** — must not conflict with existing routes. | Route is `POST /api/admin/manage` — no conflict with `/webhooks/lemon-squeezy` or `/api/validate`. |
| **CLI `generate` key format** — must match `app.py:generate_license_key`. | Same algorithm: `PHARM-{'-'.join([uuid4().hex[:4].upper() for _ in range(3)])}`. |
| **`ADMIN_SECRET` vs `SERVER_ADMIN_SECRET`** confusion with legacy `archive/server_app.py`. | Intentionally different env var per task spec. `backend/app.py` is the new authoritative backend. Legacy `archive/` is not modified. |

---

## 7. Validation Checklist
1. `python backend/test_admin.py` → all tests pass (7 CLI + 10 API = 17).
2. `python backend/test_webhook_lemon_squeezy.py` → 14/14 still pass (no regression).
3. `python backend/admin.py list` (manual) → prints ASCII table or "No licenses found".
4. `python backend/admin.py generate test@example.com` (manual) → prints generated key.
5. `python backend/admin.py revoke <key>` (manual) → prints revocation confirmation.
6. `python backend/admin.py reset <key>` (manual) → prints reset confirmation.
7. No new `.sqlite` files on disk after test runs (all use `:memory:`).
8. `git diff --stat` shows only the 6 files listed in §3.
