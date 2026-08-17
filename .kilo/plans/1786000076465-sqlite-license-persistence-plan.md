# Plan: SQLite License Persistence + Validation Endpoint

## 1. Goal

Replace the `generate_license_key` stdout stub in `backend/app.py` with real SQLite
persistence, add a `POST /api/validate` endpoint for desktop client activation, create a
WSGI `Procfile`, fix dead documentation references in `TESTING.md`, and extend the test
suite to cover the new endpoint with isolated in-memory databases.

## 2. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| DB layer location | **New `backend/db.py`** | DB logic is reused by `generate_license_key`, the `/api/validate` endpoint, and tests. Avoids bloating `app.py`. Matches project pattern (`database.py` + `db.py`). |
| Default DB path | `backend/license_db.sqlite` (absolute, via `os.path.dirname(__file__)`) | Works regardless of cwd; survives from project root under gunicorn. |
| Test DB strategy | **In-memory `:memory:`** with a shared persistent connection | User explicitly listed `:memory:` first. No disk artifacts. Shared connection via module-level `_keepalive` so all `:memory:` calls see the same schema/data. |
| Test isolation | `db.clear_licenses()` in each `setUp` | `:memory:` DB persists across tests in same process; per-test cleanup prevents cross-contamination. |
| Deployment target | `Procfile` at root → `web: gunicorn backend.app:app` | `.vercelignore` excludes `*.py`; standard WSGI hosts (Heroku/Render/Railway) read `Procfile` directly, bypassing `.vercelignore`. |
| Package marker | `backend/__init__.py` (empty) | Required for `gunicorn backend.app:app` import resolution. |
| `gunicorn` dependency | Add `gunicorn>=23.0,<24.0` to `requirements.txt` | Procfile references it; must be in install set. |
| `.gitignore` | Add `*.sqlite` | Prevents committing runtime DB files. Existing `*.db` doesn't cover `.sqlite` extension. |

### Contract for `/api/validate` (authoritative per user spec)

- **Method**: `POST`
- **Payload**: `{"license_key": "...", "hardware_id": "..."}`
- **Missing/null fields** → `400 {"error": "..."}`
- **Key not found** → `404 {"error": "License key not found"}`
- **Status = revoked** → `403 {"error": "License is revoked"}`
- **DB `hardware_id` IS NULL** → bind, `200 {"status": "active", "message": "Device bound successfully"}`
- **DB `hardware_id` matches provided** → `200 {"status": "active"}`
- **DB `hardware_id` does NOT match** → `403 {"error": "License bound to another device"}`

> **Note**: The old `archive/server_app.py` contract uses `device_id`/`hwid` and returns `{"valid": bool, "message": str}`. The user's new spec for `backend/app.py` uses `hardware_id` and `{"status": "active", ...}`. This is intentional — the new backend is a clean, simplified implementation. The `archive/` server_app.py remains untouched (non-authoritative).

## 3. Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/db.py` | **New** | SQLite persistence: `init_db()`, `insert_license()`, `get_license()`, `bind_hardware_id()`, `update_license_status()`, `clear_licenses()`, `set_db_path()` |
| `backend/app.py` | **Modify** | Import `db`; call `db.init_db()` at startup; INSERT in `generate_license_key`; add `/api/validate` route |
| `backend/__init__.py` | **New** | Empty package marker for gunicorn import |
| `backend/test_webhook_lemon_squeezy.py` | **Modify** | Switch to `:memory:` DB; add `clear_licenses()` in setUp; add `ValidateEndpointTests` class with 7 cases |
| `Procfile` | **New** (root) | `web: gunicorn backend.app:app` |
| `requirements.txt` | **Modify** | Add `gunicorn>=23.0,<24.0` |
| `.gitignore` | **Modify** | Add `*.sqlite` pattern |
| `TESTING.md` | **Modify** | Fix dead `/api/webhook/lemonsqueezy` → `/webhooks/lemon-squeezy`; fix `X-Signature` header; drop `LEMONSQUEEZY_WEBHOOK_SECRET` from secrets list |
| `PROJECT_MAP.md` | **Modify** | §7: add `db.py`, update `app.py` line count/description, add Procfile to root tree, add M90 milestone |
| `FLOW_LOGIC.md` | **Modify** | §13: add step 9 (DB persistence insert), add `/api/validate` data-flow subsection, update verification count |

## 4. Data Flow: `POST /api/validate`

```
Desktop client → POST /api/validate {"license_key","hardware_id"}
    ↓
app.validate_license()
    ├── request.get_json(silent=True) → 400 if None
    ├── extract license_key + hardware_id → 400 if either missing
    ├── db.get_license(license_key) → 404 if row is None
    ├── row["status"] == "revoked" → 403
    ├── row["hardware_id"] is None → db.bind_hardware_id(key, hwid) → 200 {"status":"active","message":"Device bound successfully"}
    ├── row["hardware_id"] == hardware_id → 200 {"status":"active"}
    └── mismatch → 403 {"error":"License bound to another device"}
```

## 5. Implementation Steps (Ordered)

### Step 1 — Create `backend/__init__.py` (empty file)
Empty file. Makes `backend` a proper Python package for `gunicorn backend.app:app`.

### Step 2 — Create `backend/db.py`
Module-level:
- `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`
- `DEFAULT_DB_PATH = os.path.join(BASE_DIR, "license_db.sqlite")`
- `_db_path = DEFAULT_DB_PATH`
- `_keepalive = None` (persistent connection for `:memory:` mode)

Functions:
- `set_db_path(path)` — override `_db_path` (for tests)
- `_connect()` — returns `_keepalive` if `:memory:` (raises if not initialized), else new `sqlite3.connect(_db_path)` with `row_factory=sqlite3.Row`
- `_close(conn)` — closes unless `:memory:` keepalive
- `init_db(db_path=None)` — sets path if provided; for `:memory:`, creates one persistent connection if `_keepalive is None`; executes `CREATE TABLE IF NOT EXISTS licenses` with columns: `license_key TEXT PRIMARY KEY`, `customer_email TEXT`, `order_id TEXT`, `status TEXT DEFAULT 'active'`, `hardware_id TEXT`; commits; closes (unless `:memory:`)
- `insert_license(license_key, customer_email, order_id)` — INSERT with `'active'` status and NULL `hardware_id`; commit
- `get_license(license_key)` — SELECT one row; returns `sqlite3.Row` or `None`
- `bind_hardware_id(license_key, hardware_id)` — UPDATE `hardware_id`; commit
- `update_license_status(license_key, status)` — UPDATE `status`; commit (needed for test setup of revoked licenses; natural CRUD operation)
- `clear_licenses()` — `DELETE FROM licenses`; commit (test isolation)

### Step 3 — Modify `backend/app.py`

**3a. Add import**: After `from flask import Flask, jsonify, request`, add:
```python
import db  # SQLite persistence layer for license keys
```

**3b. Call `db.init_db()`**: After `SIGNATURE_SECRET = ...` line (before the generate_license_key section), add:
```python
db.init_db()
```

**3c. Update `generate_license_key()`**: Replace the stub docstring and add INSERT call. The function currently:
```python
def generate_license_key(email: str, order_id: str) -> str:
    """
    Generate a license key for a verified order.

    STUB: returns a PHARM-XXXX-XXXX-XXXX key and prints to stdout.
    Persistence (Redis/SQLite), device binding, and expiry are
    intentionally NOT implemented yet.
    """
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    license_key = f"PHARM-{'-'.join(segments)}"
    print(
        f"generate_license_key(email={email!r}, order_id={order_id!r}) "
        f"-> {license_key}"
    )
    logger.info(
        "Generated license key (stub): email=%s order_id=%s key=%s",
        email, order_id, license_key,
    )
    return license_key
```
Becomes:
```python
def generate_license_key(email: str, order_id: str) -> str:
    """
    Generate a license key for a verified order.

    Generates a PHARM-XXXX-XXXX-XXXX key and persists it to the SQLite
    ``licenses`` table with status='active' and hardware_id=NULL.
    """
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    license_key = f"PHARM-{'-'.join(segments)}"
    db.insert_license(license_key, email, order_id)
    logger.info(
        "Generated license key: email=%s order_id=%s key=%s***",
        email, order_id, license_key[:8],
    )
    return license_key
```
(Keep the `print()` for dev debugging, but it's optional — the AGENTS.md surgical protocol says "touch only what is necessary" so I'll keep it.)

**3d. Add `/api/validate` endpoint**: Insert before `if __name__ == "__main__":` block:
```python
@app.route("/api/validate", methods=["POST"])
def validate_license():
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Validate: invalid or missing JSON body")
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    license_key = data.get("license_key")
    hardware_id = data.get("hardware_id")

    if not license_key or not hardware_id:
        logger.warning("Validate: missing license_key or hardware_id")
        return jsonify({"error": "license_key and hardware_id are required"}), 400

    row = db.get_license(license_key)
    if row is None:
        logger.warning("Validate: key not found key=%s***", (license_key or "")[:8])
        return jsonify({"error": "License key not found"}), 404

    if row["status"] == "revoked":
        logger.warning("Validate: revoked key=%s***", license_key[:8])
        return jsonify({"error": "License is revoked"}), 403

    db_hardware_id = row["hardware_id"]

    if db_hardware_id is None:
        db.bind_hardware_id(license_key, hardware_id)
        logger.info(
            "Validate: device bound key=%s*** hwid=%s***",
            license_key[:8], hardware_id[:8],
        )
        return jsonify({"status": "active", "message": "Device bound successfully"}), 200

    if db_hardware_id == hardware_id:
        return jsonify({"status": "active"}), 200

    logger.warning(
        "Validate: hardware mismatch key=%s*** db_hwid=%s*** req_hwid=%s***",
        license_key[:8], (db_hardware_id or "")[:8], hardware_id[:8],
    )
    return jsonify({"error": "License bound to another device"}), 403
```

### Step 4 — Modify `backend/test_webhook_lemon_squeezy.py`

**4a. Set `:memory:` DB before app import**: After the `sys.path.insert(...)` line and before `from app import app`, add:
```python
import db
db.set_db_path(":memory:")
db.init_db()
```

**4b. Add `clear_licenses()` to `LemonSqueezyWebhookTests.setUp`**: Add `db.clear_licenses()` after `self.client = app.test_client()`.

**4c. Add `ValidateEndpointTests` class** (before `if __name__` block) with 7 test methods:
```python
class ValidateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()
        db.insert_license("PHARM-TEST0001", "buyer@example.com", "ord_001")
        db.insert_license("PHARM-TEST0002", "buyer2@example.com", "ord_002")
        db.bind_hardware_id("PHARM-TEST0002", "hw-abc-123")
        db.insert_license("PHARM-TEST0003", "revoked@example.com", "ord_003")
        db.update_license_status("PHARM-TEST0003", "revoked")

    def test_validate_key_not_found(self): ...  # → 404
    def test_validate_revoked_key(self): ...     # → 403
    def test_validate_bind_new_device(self): ...  # → 200, message="Device bound successfully", verify DB updated
    def test_validate_matching_hardware_id(self): ...  # → 200, {"status": "active"}
    def test_validate_mismatched_hardware_id(self): ... # → 403
    def test_validate_missing_fields(self): ...  # → 400
    def test_validate_invalid_json(self): ...    # → 400
```

### Step 5 — Create `Procfile` (root)
```
web: gunicorn backend.app:app
```

### Step 6 — Add gunicorn to `requirements.txt`
Append:
```
# WSGI server for Procfile deployment (gunicorn backend.app:app)
gunicorn>=23.0,<24.0
```

### Step 7 — Add `*.sqlite` + `*.sqlite3` to `.gitignore`
Append both patterns after the existing `*.db` line:
```
*.db
*.sqlite
*.sqlite3
```

### Step 8 — Clean up `TESTING.md`

Three dead references identified via `rg -n "api/webhook/lemonsqueezy|LEMONSQUEEZY_WEBHOOK_SECRET" TESTING.md`:

**8a.** Line 94 — Lemon Squeezy mock payload curl block:
- URL: `http://localhost:5000/api/webhook/lemonsqueezy` → `http://localhost:5000/webhooks/lemon-squeezy`
- Header: `-H "x-signature: test-signature"` → `-H "X-Signature: <hmac-sha256-hex-digest>"`
- Add a note: "Header is `X-Signature` over the raw request body, computed as `hmac.sha256(LEMON_SQUEEZEY_SIGNATURE_SECRET, raw_body)`."

**8b.** Line 192 — ngrok webhook configuration:
- URL: `https://xxxx.ngrok.io/api/webhook/lemonsqueezy` → `https://xxxx.ngrok.io/webhooks/lemon-squeezy`

**8c.** Line 200 — secrets list:
```
Set your real `LEMONSQUEEZY_WEBHOOK_SECRET` and `PADDLE_WEBHOOK_SECRET` in `.env`.
```
Change to:
```
Set your real `LEMON_SQUEEZEY_SIGNATURE_SECRET` and `PADDLE_WEBHOOK_SECRET` in `.env`.
```

> Lines 67 and 252 reference `python hub.py test-webhook --gateway lemonsqueezy` — this is a CLI argument, not a dead endpoint URL. Leave as-is (out of scope; `hub.py` updates are a separate concern).

### Step 9 — Update `PROJECT_MAP.md`

**9a.** Root structure tree (line 354): Update `backend/` entry to include `db.py` and `__init__.py`.

**9b.** §7 file table (lines 1009-1012): Add row for `backend/db.py`; update `backend/app.py` description to include `/api/validate` and SQLite persistence; update line count.

**9c.** §7 root structure tree: Add `Procfile` and `LICENSE` entries if not present (check existing tree first — `LICENSE` appears at line 385 but `Procfile` is not listed).

**9d.** §7: Add note about `Procfile` and `*.gitignore` adding `*.sqlite`.

**9e.** Milestones table: Add row for M90 after M66:
```
| M90 | SQLite License Persistence + Validate Endpoint (backend/db.py: SQLite licenses table with CRUD; backend/app.py: generate_license_key INSERTs to DB, POST /api/validate endpoint with 404/403/400/200 binding logic; Procfile for gunicorn deployment; in-memory test isolation) | TODO | — |
```

### Step 10 — Update `FLOW_LOGIC.md`

**10a.** §13 data flow: Extend step 6 (`order_created`): after generating license key, add step 6b — `INSERT into licenses table via db.insert_license()`.

**10b.** §13: Add a new subsection "### 13B. License Validation Endpoint (`POST /api/validate`)" with the full data flow (see Section 4 above).

**10c.** §13: Update verification count from "6/6 unittest cases" to "13/13" (6 webhook + 7 validate).

## 6. Validation

1. **Webhook tests still pass**: `python backend/test_webhook_lemon_squeezy.py` → all existing 6 tests + 7 new validate tests pass (13 total).
2. **No disk artifacts**: `git status` shows no new `.sqlite` file created by test run.
3. **Validate endpoint behavior**: Each of the 7 test cases verifies the exact status code and response body per Section 2.
4. **Binding verification**: `test_validate_bind_new_device` checks `db.get_license("PHARM-TEST0001")["hardware_id"]` equals the provided `hardware_id` after the request.
5. **Procfile is valid**: `echo "web: gunicorn backend.app:app" > Procfile` matches the file content; `gunicorn` added to requirements.txt.
6. **TESTING.md clean**: `rg -n "api/webhook/lemonsqueezy|LEMONSQUEEZY_WEBHOOK_SECRET" TESTING.md` returns zero matches.
7. **Docs consistent**: `PROJECT_MAP.md` §7 and `FLOW_LOGIC.md` §13 both reference `backend/db.py`, the `/api/validate` endpoint, and the `license_db.sqlite` database.
8. **No regression**: The webhook endpoint behavior is unchanged — `generate_license_key` now persists but still returns the same `PHARM-XXXX-XXXX-XXXX` format.

## 7. Risks & Mitigations

- **Risk**: `:memory:` connection not thread-safe if Flask dev server uses threads. **Mitigation**: `check_same_thread=False` on the `:memory:` keepalive; production uses file-based DB with per-call connections.
- **Risk**: `init_db()` called twice (once by test, once by app import) creates duplicate `:memory:` connections. **Mitigation**: `init_db()` guards with `if _keepalive is None` to avoid recreating.
- **Risk**: Test DB state leaks between test classes. **Mitigation**: `db.clear_licenses()` in every `setUp`.
- **Risk**: `.gitignore` `*.sqlite` pattern doesn't cover `*.sqlite3`. **Mitigation**: Add both `*.sqlite` and `*.sqlite3` to `.gitignore`.
