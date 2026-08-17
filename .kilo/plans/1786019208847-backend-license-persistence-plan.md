# Plan: SQLite License Persistence + Validate Endpoint (Refined)

> **Timestamp:** 2026-08-06 | **Python:** 3.14.3 | **Flask:** 3.1.3 | **gunicorn:** not installed (add to requirements.txt)
> **Status:** `backend/db.py` already exists and is fully implemented — no creation needed. This plan focuses on integration, endpoint delivery, test coverage, deployment config, and doc hygiene.

---

## 1. Goal

Wire the existing `backend/db.py` SQLite layer into `backend/app.py`, replace the `generate_license_key` stdout stub with real persistence, implement `POST /api/validate` per the user spec, create a WSGI `Procfile`, add `gunicorn` to dependencies, gitignore `*.sqlite`, clean dead references in `TESTING.md`, and extend the test suite with isolated in-memory DB coverage for the new endpoint.

---

## 2. Current State Assessment

| File | Status | Notes |
|---|---|---|
| `backend/db.py` | **Exists, complete** | Schema matches spec exactly (5 columns). All CRUD funcs present: `init_db`, `insert_license`, `get_license`, `bind_hardware_id`, `update_license_status`, `clear_licenses`, `set_db_path`. Parameterized queries. `:memory:` keepalive pattern. **No changes needed.** |
| `backend/__init__.py` | **Exists, empty** | Package marker for gunicorn. No changes needed. |
| `backend/app.py` | **Stub, not wired** | `generate_license_key` prints to stdout only; no `db` import; no `init_db` call; no `/api/validate` route. |
| `backend/test_webhook_lemon_squeezy.py` | **No DB isolation** | 6 webhook tests only; no `:memory:` setup; no validate tests. |
| `Procfile` | **Missing** | Needs creation at project root. |
| `requirements.txt` | **Missing gunicorn** | Has `flask>=3.0,<4.0`. Needs `gunicorn`. |
| `.gitignore` | **Missing `*.sqlite`** | Has `*.db` but not `*.sqlite`/`*.sqlite3`. |
| `TESTING.md` | **Dead `/api/webhook/lemonsqueezy` refs** | Lines 94, 192 (endpoint URL); line 200 (`LEMONSQUEEZY_WEBHOOK_SECRET`). |
| `PROJECT_MAP.md` §7 | **Outdated** | `backend/app.py` described as "stub"; no `db.py` listed; no Procfile in root tree; M66 milestone says "stub". |
| `FLOW_LOGIC.md` §13 | **Outdated** | Step 6 says "stub returns PHARM-XXXX-XXXX-XXXX, prints to stdout"; no `/api/validate` flow. |

---

## 3. Design Decisions (Resolved)

### D1. DB init timing in `app.py`
**Decision:** Call `db.init_db()` at module level (after `SIGNATURE_SECRET`).
- **Rationale:** Ensures schema exists under any WSGI server (gunicorn). `CREATE TABLE IF NOT EXISTS` is idempotent. Production uses file-based `license_db.sqlite`; tests override to `:memory:` before importing `app`.
- **Test import ordering:** Test file must call `db.init_db(":memory:")` BEFORE `from app import app` so that `app.py`'s module-level `db.init_db()` reuses the already-configured `:memory:` keepalive instead of creating a file.

### D2. Cross-import style (package vs. top-level)
**Decision:** Use dual-mode import in `app.py`:
```python
try:
    from .db import init_db, insert_license, get_license, bind_hardware_id
except ImportError:
    from db import init_db, insert_license, get_license, bind_hardware_id
```
- **Gunicorn** (`backend.app:app`): `from .db import` resolves within package. ✓
- **Tests** (`from app import app` with `backend/` on path): relative import fails → falls back to `from db import`. ✓
- **Rationale:** No changes to the test file's existing `sys.path` + `from app import app` pattern.

### D3. `/api/validate` contract (authoritative per user spec)
- **Payload:** `{"license_key": "...", "hardware_id": "..."}`
- **Response on bind:** `200 {"status": "active", "message": "Device bound successfully"}`
- **Response on match:** `200 {"status": "active"}`
- **404** if key not found: `{"error": "License key not found"}`
- **403** if revoked: `{"error": "License is revoked"}`
- **403** on hardware mismatch: `{"error": "License bound to another device"}`
- **400** on missing fields or invalid JSON: `{"error": "..."}`
- **Known consideration:** The old `archive/server_app.py` contract used `device_id`/`hwid` and `{"valid": bool}`. The `license_gate.py` desktop client sends `device_id` and checks `valid`. **The new backend follows the user's spec exactly** (`hardware_id`, `status`). `license_gate.py` is out of scope (not modified; its `API_BASE_URL` is still a placeholder). The `archive/` server remains non-authoritative.

### D4. `generate_license_key` persistence
**Decision:** Call `db.insert_license(license_key, email, order_id)` before returning. Keep the existing `print()` for dev debugging (minimal touch). Update the docstring and logger to remove "stub" language and avoid logging the full key.

### D5. Error handling in `/api/validate`
**Decision:** Wrap DB operations in `try/except sqlite3.Error` → return `500 {"error": "Database error"}`. This satisfies "handles database connections/closures gracefully" and "production-ready code quality."

### D6. TESTING.md scope
**Decision:** Fix the two `/api/webhook/lemonsqueezy` endpoint-URL references (lines 94, 192) → `/webhooks/lemon-squeezy`, correct the `X-Signature` header name, and replace `LEMONSQUEEZY_WEBHOOK_SECRET` (line 200) with `LEMON_SQUEEZEY_SIGNATURE_SECRET`. **Line 67 and 252** (`hub.py test-webhook --gateway lemonsqueezy`) are CLI argument references, not endpoint paths — `hub.py` only supports `--gateway paddle`. These are out of strict scope for "remove `/api/webhook/lemonsqueezy` references" but noted as optional cleanup.

### D7. `hub.py test-webhook --gateway lemonsqueezy` (lines 67, 252)
**Decision:** Out of scope. These are CLI invocations of `hub.py`, not endpoint references. The user's task is scoped to `/api/webhook/lemonsqueezy` endpoint references. Leave as-is.

### D8. License key format
**Decision:** Keep existing `PHARM-XXXX-XXXX-XXXX` format (3 segments of 4 hex chars). The user's spec says "PHARM-XXXX key" — the prefix `PHARM-` is preserved. Tests already assert `startswith("PHARM-")`.

---

## 4. Affected Files

| File | Action | Lines (est.) |
|---|---|---|
| `backend/app.py` | Modify | ~180 (was ~122) |
| `backend/test_webhook_lemon_squeezy.py` | Modify | ~200 (was ~108) |
| `Procfile` | New (root) | 1 |
| `requirements.txt` | Modify (append 2 lines) | 14 (was 12) |
| `.gitignore` | Modify (append 2 lines) | 25 (was 23) |
| `TESTING.md` | Modify (3 edits) | unchanged |
| `PROJECT_MAP.md` | Modify (§7 + M66 + M90) | unchanged |
| `FLOW_LOGIC.md` | Modify (§13) | unchanged |

---

## 5. Implementation Steps (Ordered)

### Step 1 — Modify `backend/app.py`

**1a. Add import** (after `from flask import Flask, jsonify, request`):
```python
import sqlite3

try:
    from .db import init_db, insert_license, get_license, bind_hardware_id
except ImportError:
    from db import init_db, insert_license, get_license, bind_hardware_id
```

**1b. Add DB init** (after `SIGNATURE_SECRET = ...` line, before the `# ── License key generation` section):
```python
db.init_db()
```

**1c. Update module docstring** (line 7):
Replace:
```
On ``order_created`` events, stubs license-key generation
(key is printed to stdout; persistence is deferred).
```
With:
```
On ``order_created`` events, generates a PHARM-XXXX-XXXX-XXXX license key
and persists it to the SQLite ``licenses`` table (backend/license_db.sqlite).
The ``POST /api/validate`` endpoint handles desktop client hardware binding.
```

**1d. Refactor `generate_license_key`** (replace the stub function body):
```python
def generate_license_key(email: str, order_id: str) -> str:
    """
    Generate a license key for a verified order.

    Generates a ``PHARM-XXXX-XXXX-XXXX`` key and persists it to the SQLite
    ``licenses`` table with ``status='active'`` and ``hardware_id=NULL``
    (unbound). The key is returned to the caller for inclusion in the
    webhook response. Device binding happens later via ``/api/validate``.
    """
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    license_key = f"PHARM-{'-'.join(segments)}"
    insert_license(license_key, email, order_id)
    logger.info(
        "Generated license key: email=%s order_id=%s key=%s***",
        email, order_id, license_key[:8],
    )
    return license_key
```
Note: The existing `print()` statement is removed — it was debug-only and the logger now handles output. This is a necessary change (the docstring/log previously advertised "stub").

**1e. Add `/api/validate` endpoint** (insert before the `if __name__ == "__main__":` block):
```python
@app.route("/api/validate", methods=["POST"])
def validate_license():
    """Validate a license key and bind it to a hardware device.

    Expected JSON payload:
        {"license_key": "PHARM-XXXX-XXXX-XXXX", "hardware_id": "<hwid>"}

    Response rules:
        - Missing/invalid JSON or missing required fields → 400
        - Key not found in database → 404
        - Key status is 'revoked' → 403
        - DB hardware_id is NULL (first activation) → 200, binds hardware_id
        - DB hardware_id matches provided → 200 (validation success)
        - DB hardware_id mismatches → 403 (bound to another device)
    """
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Validate: invalid or missing JSON body")
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    license_key = data.get("license_key")
    hardware_id = data.get("hardware_id")

    if not license_key or not hardware_id:
        logger.warning("Validate: missing license_key or hardware_id")
        return jsonify({"error": "license_key and hardware_id are required"}), 400

    try:
        row = get_license(license_key)
    except sqlite3.Error:
        logger.exception("Validate: database error")
        return jsonify({"error": "Database error"}), 500

    if row is None:
        logger.warning("Validate: key not found key=%s***", license_key[:8])
        return jsonify({"error": "License key not found"}), 404

    if row["status"] == "revoked":
        logger.warning("Validate: revoked key=%s***", license_key[:8])
        return jsonify({"error": "License is revoked"}), 403

    db_hardware_id = row["hardware_id"]

    if db_hardware_id is None:
        # First activation — bind the device
        try:
            bind_hardware_id(license_key, hardware_id)
        except sqlite3.Error:
            logger.exception("Validate: database error during bind")
            return jsonify({"error": "Database error"}), 500
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

### Step 2 — Modify `backend/test_webhook_lemon_squeezy.py`

**2a. Add DB setup before app import** (after `sys.path.insert(...)`, before `from app import app`):
```python
import db
db.init_db(":memory:")
```
This sets `_db_path = ":memory:"` and creates the in-memory keepalive connection BEFORE `app.py` is imported. When `app.py` runs its module-level `db.init_db()`, it sees `_db_path == ":memory:"` and reuses the existing keepalive (no file created on disk).

**2b. Update imports** — add `db` to the imports after `from app import app`:
```python
from app import app  # noqa: E402
import db  # noqa: E402
```
Wait — `db` is already imported in step 2a. Keep it. But the existing `from app import app` line has `# noqa: E402`. The `import db` should be before `from app import app`. Restructure:
```python
os.environ.setdefault("LEMON_SQUEEZEY_SIGNATURE_SECRET", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
db.init_db(":memory:")
from app import app  # noqa: E402

SECRET = os.environ["LEMON_SQUEEZEY_SIGNATURE_SECRET"]
```

**2c. Add `clear_licenses()` to `LemonSqueezyWebhookTests.setUp`:**
```python
def setUp(self):
    self.client = app.test_client()
    db.clear_licenses()
```

**2d. Enhance `test_order_created_returns_200`** — add DB persistence assertion:
After the existing `self.assertTrue(body["license_key"].startswith("PHARM-"))` line, add:
```python
row = db.get_license(body["license_key"])
self.assertIsNotNone(row, "License key should be persisted in the database")
```

**2e. Add `ValidateEndpointTests` class** (before `if __name__ == "__main__":`):
```python
class ValidateEndpointTests(unittest.TestCase):
    """Test suite for POST /api/validate with isolated in-memory database."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()
        # Unregistered / unbound key (active, no hardware_id)
        db.insert_license("PHARM-TEST0001", "buyer@example.com", "ord_001")
        # Bound key (hardware_id already set to a known value)
        db.insert_license("PHARM-TEST0002", "buyer2@example.com", "ord_002")
        db.bind_hardware_id("PHARM-TEST0002", "hw-device-abc")
        # Revoked key
        db.insert_license("PHARM-TEST0003", "revoked@example.com", "ord_003")
        db.update_license_status("PHARM-TEST0003", "revoked")

    def test_validate_key_not_found(self):
        """Non-existent license key → 404."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-NONEXISTENT", "hardware_id": "hw-xyz"},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"], "License key not found")

    def test_validate_revoked_key(self):
        """Revoked license → 403."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0003", "hardware_id": "hw-xyz"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "License is revoked")

    def test_validate_bind_new_device(self):
        """First activation (NULL hardware_id) → 200, binds hardware_id."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0001", "hardware_id": "hw-new-device"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["message"], "Device bound successfully")
        # Verify the DB was actually updated
        row = db.get_license("PHARM-TEST0001")
        self.assertEqual(row["hardware_id"], "hw-new-device")

    def test_validate_matching_hardware_id(self):
        """Matching hardware_id → 200 {"status": "active"}."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0002", "hardware_id": "hw-device-abc"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "active")
        self.assertNotIn("message", body)

    def test_validate_mismatched_hardware_id(self):
        """Bound key with wrong hardware_id → 403."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0002", "hardware_id": "hw-different-device"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "License bound to another device")

    def test_validate_missing_fields(self):
        """Missing hardware_id → 400."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0001"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_validate_invalid_json(self):
        """No JSON body → 400."""
        resp = self.client.post(
            "/api/validate",
            data="",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_validate_webhook_to_valid_flow(self):
        """Integration: create key via webhook → bind via validate → re-validate."""
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {
                "id": "ord_integration",
                "type": "order",
                "attributes": {"user_email": "integration@example.com"},
            },
        }
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=json.dumps(payload, separators=(",", ":")),
            headers=sign(payload),
        )
        self.assertEqual(resp.status_code, 200)
        license_key = resp.get_json()["license_key"]

        # First validation — should bind
        resp = self.client.post(
            "/api/validate",
            json={"license_key": license_key, "hardware_id": "hw-integration-1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["message"], "Device bound successfully")

        # Second validation — should succeed (match)
        resp = self.client.post(
            "/api/validate",
            json={"license_key": license_key, "hardware_id": "hw-integration-1"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "active")
```

### Step 3 — Create `Procfile` (project root)
```
web: gunicorn backend.app:app
```

### Step 4 — Add `gunicorn` to `requirements.txt`
Append after the Flask line:
```
# WSGI server for Procfile deployment (gunicorn backend.app:app)
gunicorn>=23.0,<24.0
```

### Step 5 — Add `*.sqlite` + `*.sqlite3` to `.gitignore`
After the existing `*.db` line (line 7), add:
```
*.sqlite
*.sqlite3
```

### Step 6 — Clean up `TESTING.md` (3 edits)

**6a. Line 94 — Lemon Squeezy mock payload curl block:**
Replace:
```
curl -X POST http://localhost:5000/api/webhook/lemonsqueezy \
  -H "Content-Type: application/json" \
  -H "x-signature: test-signature" \
  -d '{
```
With:
```
curl -X POST http://localhost:5000/webhooks/lemon-squeezy \
  -H "Content-Type: application/json" \
  -H "X-Signature: <hmac-sha256-hex-digest>" \
  -d '{
```
Add a note after the curl block:
> The `X-Signature` header is an HMAC-SHA256 hex digest of the raw request body, computed with `LEMON_SQUEEZEY_SIGNATURE_SECRET`.

**6b. Line 192 — ngrok webhook configuration:**
Replace:
```
  - URL: `https://xxxx.ngrok.io/api/webhook/lemonsqueezy`
```
With:
```
  - URL: `https://xxxx.ngrok.io/webhooks/lemon-squeezy`
```

**6c. Line 200 — secrets list:**
Replace:
```
Set your real `LEMONSQUEEZY_WEBHOOK_SECRET` and `PADDLE_WEBHOOK_SECRET` in `.env`.
```
With:
```
Set your real `LEMON_SQUEEZEY_SIGNATURE_SECRET` and `PADDLE_WEBHOOK_SECRET` in `.env`.
```

**6d. Line 78 — generic template:**
Replace:
```
3. POSTs to `http://localhost:5000/api/webhook/<gateway>`
```
With:
```
3. POSTs to `http://localhost:5000/webhooks/<gateway>`
```

### Step 7 — Update `PROJECT_MAP.md`

**7a. Line 354 — root structure tree:**
Replace:
```
├── backend/                # Flask Lemon Squeezy webhook server (backend/app.py + tests)
```
With:
```
├── backend/                # Flask licensing server (backend/app.py: webhook + validate endpoint; db.py: SQLite persistence)
├── Procfile                # WSGI entry: `web: gunicorn backend.app:app`
```

**7b. Line 433 — M66 milestone row:**
Replace:
```
| M66 | Lemon Squeezy Webhook Flask Backend (`backend/app.py` + `backend/test_webhook_lemon_squeezy.py`) — HMAC-SHA256 signature verification, `order_created` license-key stub | Complete | 2026-08-06 |
```
With:
```
| M66 | Lemon Squeezy Webhook Flask Backend (`backend/app.py` + `backend/test_webhook_lemon_squeezy.py`) — HMAC-SHA256 signature verification, `order_created` generates + persists `PHARM-XXXX-XXXX-XXXX` key to SQLite. | Complete | 2026-08-06 |
| M90 | SQLite License Persistence + Validate Endpoint — `backend/db.py` (SQLite `licenses` table: `init_db`, `insert_license`, `get_license`, `bind_hardware_id`, `update_license_status`, `clear_licenses`), `POST /api/validate` endpoint (404/403/400/200 binding logic), in-memory test isolation, `Procfile` for gunicorn deployment, `gunicorn` in requirements.txt. | Complete | 2026-08-06 |
```

**7c. §7 Licensing Backend (lines 1009-1014) — file table:**
Replace:
```
| `backend/app.py` | Flask app — `POST /webhooks/lemon-squeezy`, HMAC-SHA256 `X-Signature` verification → `order_created` license-key stub | ~120 |
| `backend/test_webhook_lemon_squeezy.py` | 6 unittest cases (Flask test client) covering the 401/400/200 paths | ~160 |

**Test result:** 6/6 pass (`python backend/test_webhook_lemon_squeezy.py`).
```
With:
```
| `backend/app.py` | Flask app — `POST /webhooks/lemon-squeezy` (HMAC-SHA256 + key persistence) + `POST /api/validate` (hardware binding: 404/403/400/200) | ~180 |
| `backend/db.py` | SQLite persistence layer — `licenses` table, `init_db`/`insert_license`/`get_license`/`bind_hardware_id`/`update_license_status`/`clear_licenses` | ~145 |
| `backend/test_webhook_lemon_squeezy.py` | 14 unittest cases (Flask test client) — 6 webhook + 8 validate (success, binding, mismatch, revocation, not-found, missing-fields, invalid-JSON, integration flow) | ~200 |

**Test result:** 14/14 pass (`python backend/test_webhook_lemon_squeezy.py`).
```

**7d. §7 — add deployment subsection** (after the "Removed legacy handlers" section, before "Other licensing components"):
```
### Deployment

A `Procfile` at the project root defines the WSGI entry point:

```
web: gunicorn backend.app:app
```

This bypasses `.vercelignore` (which excludes `*.py`) for standard WSGI hosts
(Heroku/Render/Railway/Fly.io). `gunicorn>=23.0,<24.0` is listed in
`requirements.txt`. Note: the database file `backend/license_db.sqlite` is
runtime-generated; add `*.sqlite` to your deployment `.gitignore` (already
done in this repo). Initialize the schema with `python -c "import backend.db; backend.db.init_db()"` before first boot, or rely on `app.py`'s module-level `init_db()` call.
```

**7e. §7 environment variables table — add note about DB path:**
After the env vars table, add:
```
**Database:** `backend/license_db.sqlite` (SQLite, auto-initialized at import by
`backend/app.py` via `db.init_db()`). Override at test time with
`db.set_db_path(":memory:")`.
```

### Step 8 — Update `FLOW_LOGIC.md` Section 13

**8a. Module docstring line (line 119-121):** Update to reflect M90:
Replace:
```
## 13. Lemon Squeezy Webhook Backend (M66) — SINGLE SOURCE OF TRUTH
```
With:
```
## 13. Lemon Squeezy Webhook Backend (M66/M90) — SINGLE SOURCE OF TRUTH
```

**8b. Update the "order_created" data flow step 6 (line 149):**
Replace:
```
    - `order_created`:
      - Extract `customer_email = payload["data"]["attributes"]["user_email"]`.
      - Extract `order_id = payload["data"]["id"]`.
      - Call `generate_license_key(email, order_id)` → stub returns `PHARM-XXXX-XXXX-XXXX`, prints to stdout.
      - → `200` `{"status": "ok", "license_key": ...}`.
```
With:
```
    - `order_created`:
      - Extract `customer_email = payload["data"]["attributes"]["user_email"]`.
      - Extract `order_id = payload["data"]["id"]`.
      - Call `generate_license_key(email, order_id)` → generates `PHARM-XXXX-XXXX-XXXX`,
        INSERTs into `licenses` table (`backend/db.py`), returns the key.
      - → `200` `{"status": "ok", "license_key": ...}`.
```

**8c. Update security notes (line 154):**
Replace:
```
**Verification:** 6/6 unittest cases pass via Flask `test_client` (missing/invalid signature → 401, empty body → 400, malformed JSON → 400, order_created → 200 + stdout print, unhandled event → 200, missing email → 400).
```
With:
```
**Verification:** 14/14 unittest cases pass via Flask `test_client` (6 webhook
tests + 8 validate tests: key-not-found→404, revoked→403, first-bind→200,
match→200, mismatch→403, missing-fields→400, invalid-JSON→400, webhook→validate
integration flow). In-memory `:memory:` SQLite ensures zero test artifacts.
```

**8d. Add subsection 13B after the data flow (after line 154):**
```markdown
### 13B. License Validation Endpoint — `POST /api/validate` (M90)

**Data flow:**

Desktop client → `POST /api/validate` `{"license_key", "hardware_id"}`

1. Parse JSON body via `request.get_json(silent=True)`.
   - Missing/invalid → `400 {"error": "Invalid or missing JSON body"}`.
2. Extract `license_key` and `hardware_id`.
   - Either missing/empty → `400 {"error": "license_key and hardware_id are required"}`.
3. `db.get_license(license_key)` (parameterized query).
   - Row not found → `404 {"error": "License key not found"}`.
4. Check `row["status"]`.
   - `'revoked'` → `403 {"error": "License is revoked"}`.
5. Read `row["hardware_id"]`:
   - **NULL** (first activation): `db.bind_hardware_id(key, hardware_id)` →
     `200 {"status": "active", "message": "Device bound successfully"}`.
   - **Matches** provided `hardware_id` → `200 {"status": "active"}`.
   - **Does not match** → `403 {"error": "License bound to another device"}`.

**Security:** all `db.py` operations use `?` parameterized queries; `sqlite3.Error`
is caught and returns `500` (no traceback leakage to client).
```

---

## 6. Test Cases (Exact)

| # | Test Method | Setup | Request | Expected |
|---|---|---|---|---|
| T1 | `test_validate_key_not_found` | clear DB | `{"license_key":"PHARM-NONEXISTENT","hardware_id":"hw-x"}` | 404 `{"error":"License key not found"}` |
| T2 | `test_validate_revoked_key` | insert `PHARM-TEST0003`, status='revoked' | `{"license_key":"PHARM-TEST0003","hardware_id":"hw-x"}` | 403 `{"error":"License is revoked"}` |
| T3 | `test_validate_bind_new_device` | insert `PHARM-TEST0001` (NULL hwid) | `{"license_key":"PHARM-TEST0001","hardware_id":"hw-new"}` | 200 `{"status":"active","message":"Device bound successfully"}` + verify DB `hardware_id == "hw-new"` |
| T4 | `test_validate_matching_hardware_id` | insert `PHARM-TEST0002`, bind `hw-device-abc` | `{"license_key":"PHARM-TEST0002","hardware_id":"hw-device-abc"}` | 200 `{"status":"active"}` (no `message` key) |
| T5 | `test_validate_mismatched_hardware_id` | insert `PHARM-TEST0002`, bind `hw-device-abc` | `{"license_key":"PHARM-TEST0002","hardware_id":"hw-different"}` | 403 `{"error":"License bound to another device"}` |
| T6 | `test_validate_missing_fields` | clear DB | `{"license_key":"PHARM-TEST0001"}` (no hardware_id) | 400 |
| T7 | `test_validate_invalid_json` | clear DB | empty body, content_type=json | 400 |
| T8 | `test_validate_webhook_to_valid_flow` | clear DB | 1. POST webhook → get key. 2. validate with hwid → 200 bind. 3. validate same hwid → 200 match | 200, 200 |

**Webhooks test enhancement:** `test_order_created_returns_200` adds assertion `db.get_license(body["license_key"]) is not None`.

**Total: 14 tests** (6 original webhook + 8 new validate).

---

## 7. Validation Checklist

1. **Run tests:** `python backend/test_webhook_lemon_squeezy.py` → 14/14 pass (6 webhook + 8 validate).
2. **No disk artifacts:** `git status --porcelain` after test run shows no new `.sqlite` file (in-memory DB used).
3. **Validate response bodies:** Each of T1–T7 verifies exact status code AND response body keys/messages.
4. **Binding verification:** T3 asserts `db.get_license("PHARM-TEST0001")["hardware_id"] == "hw-new"` after the request.
5. **Procfile:** File contains exactly `web: gunicorn backend.app:app`.
6. **requirements.txt:** Contains `gunicorn>=23.0,<24.0`.
7. **TESTING.md clean:** `rg -n "api/webhook/lemonsqueezy|LEMONSQUEEZY_WEBHOOK_SECRET" TESTING.md` returns **zero** matches.
8. **Docs consistent:** `PROJECT_MAP.md` §7 names `backend/db.py`, `/api/validate`, Procfile, and M90 milestone. `FLOW_LOGIC.md` §13 reflects persistence + validate flow.
9. **No regression:** All 6 original webhook tests pass unchanged (only `test_order_created_returns_200` gets one new assertion).
10. **Security:** `rg -n "f-string.*WHERE|f\".*\+.*\"|format.*WHERE" backend/db.py` — zero string-concatenated SQL (all parameterized).
11. **Git status:** `git status --porcelain` shows new/modified files only (no accidental deletions).

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Import path conflict** — `from .db` works under gunicorn but not in tests (and vice versa). | Dual-mode `try/except ImportError` import pattern (D2). Tested by running the test suite. |
| **`:memory:` connection shared across test classes** — state leaks. | `db.clear_licenses()` in every `setUp` (both `LemonSqueezyWebhookTests` and `ValidateEndpointTests`). |
| **`app.py` module-level `init_db()` creates `license_db.sqlite` during test import.** | Test calls `db.init_db(":memory:")` BEFORE `from app import app` (step 2b). `app.py`'s `init_db()` sees `_db_path == ":memory:"` and reuses the keepalive — no file is created. Verified by validation check #2. |
| **gunicorn not installable on Windows dev machine.** | Procfile is for Linux WSGI hosts (Heroku/Render/Railway). Local dev uses `python backend/app.py` (Flask dev server). `gunicorn` in requirements.txt is a deployment dependency, not a dev requirement. |
| **Contract mismatch with `license_gate.py`** (expects `device_id` + `valid`; new endpoint uses `hardware_id` + `status`). | Intentional per user spec. `license_gate.py` is out of scope (not modified). The desktop client's `API_BASE_URL` is still a placeholder. This endpoint serves as the new clean contract for a future client update. |
| **`hub.py` references `--gateway lemonsqueezy` (lines 67, 252) but only supports `--gateway paddle`.** | Documented as out of scope (D7). These are CLI references, not `/api/webhook/lemonsqueezy` endpoint references. |
| **SQLite table lacks `expires_at` / `created_at` columns** (archived `server_app.py` had these). | Intentional — the user's schema spec defines only 5 columns. Expiry/created_at are future enhancements, not in scope. |

---

## 9. Rollout / Execution Order

```
Step 1: backend/app.py  →  Step 2: tests  →  Step 3: Procfile
  ↓                                ↓
Step 4: requirements.txt          Step 5: .gitignore
  ↓                               ↓
Step 6: TESTING.md cleanup
  ↓
Step 7: PROJECT_MAP.md
  ↓
Step 8: FLOW_LOGIC.md
  ↓
VALIDATION: python backend/test_webhook_lemon_squeezy.py → 14/14
```

All steps are independent at the file level. Steps 1–2 must be done together (app + tests are coupled via the DB import pattern). Steps 3–8 are documentation/config.
