# Plan: Lemon Squeezy Webhook Flask App (`backend/app.py`)

## Summary
Create a new, standalone Flask application at `backend/app.py` that receives Lemon Squeezy webhooks, verifies their HMAC-SHA256 signature, and stubs license-key generation for `order_created` events.

## Status
Implementation-ready. Awaiting approval to implement (via `plan_exit` follow-up).

---

## 1. Context & Contradictions Found

The codebase already contains **three** Lemon Squeezy / license webhook implementations. This task adds a **fourth**, independent component. Existing files are **out of scope** and must NOT be modified or deleted (Surgical Protocol — touch only what is necessary).

| File | Framework | Env var | License key flow | Status |
|------|-----------|---------|------------------|--------|
| `api/lemon_webhook.py` | `BaseHTTPRequestHandler` (Vercel) | `LEMON_SQUEEZEY_WEBHOOK_SECRET` | reads `license_key` from payload `custom_data` | untouched |
| `archive/licensing/api/webhook.py` | `BaseHTTPRequestHandler` (Vercel) | `LEMON_SQUEEZEY_WEBHOOK_SECRET` | reads `license_key` from payload `custom_data` | untouched (duplicate) |
| `archive/license_server/api/webhook.py` | Vercel Python serverless | `LEMON_WEBHOOK_SECRET` | generates `PHARM-XXXX-XXXX-XXXX` via `uuid` | untouched |
| `archive/server_app.py` | Flask (PythonAnywhere) | `PADDLE_WEBHOOK_SECRET` (Paddle only) | license CRUD in SQLite + offline token | untouched |
| **`backend/app.py` (THIS TASK)** | **Flask** | **`LEMON_SQUEEZEY_SIGNATURE_SECRET`** | **stubs `generate_license_key(email, order_id)`** | **new** |

### Decision 1 — Env var name
The task explicitly specifies `LEMON_SQUEEZEY_SIGNATURE_SECRET`. None of the existing files use this exact name (they use `LEMON_SQUEEZEY_WEBHOOK_SECRET` or `LEMON_WEBHOOK_SECRET`).
- **Resolved:** use `LEMON_SQUEEZEY_SIGNATURE_SECRET` verbatim, as the user explicitly directed. This is a new component with its own deployment environment.
- **Risk / Recommendation:** before deploying to production, the operator must set `LEMON_SQUEEZEY_SIGNATURE_SECRET` (do **not** assume the value lives under one of the legacy names — that would cause all signature checks to fail with 401). Consider standardizing on a single env-var name across the repo as a follow-up task (out of scope here).

### Decision 2 — License key generation
Task says: stub `generate_license_key(email, order_id)` and print to stdout "for now".
- **Resolved:** implement a stub that returns a realistic `PHARM-XXXX-XXXX-XXXX` key (consistent with `archive/license_server` format) **without persisting it** (Redis/DB writes are explicitly deferred — stub). Print to stdout and log.
- Persistence, device binding, and integration with `license_gate.py` (`/api/validate` consumer) are **out of scope** (stub).

### Decision 3 — Payload field paths
Verified against the existing Lemon Squeezy parsers (`archive/license_server/api/webhook.py` lines 126-132 and `api/lemon_webhook.py` line 62):
- Event name: `payload["meta"]["event_name"]`
- Customer email: `payload["data"]["attributes"]["user_email"]`
- Order ID: `payload["data"]["id"]` (string, e.g. `ord_...`)

### Decision 4 — Dependencies
`requirements.txt` (root) does **not** list Flask. The implementing agent must add `flask>=3.0,<4.0` to the root `requirements.txt` so the env is reproducible. (Flask is already used in `archive/requirements.txt`.) This is a one-line additive change to an existing file.

### Decision 5 — Existing files
`api/lemon_webhook.py`, `archive/licensing/api/webhook.py`, `archive/license_server/api/webhook.py`, `archive/server_app.py`, `license_gate.py` are **not modified**. The new `backend/app.py` is intentionally a separate, minimal, testable module.

---

## 2. Affected Boundaries
- **New file:** `backend/app.py` (creates `backend/` directory — must be created if absent).
- **Modified file:** `requirements.txt` (add `flask>=3.0,<4.0`).
- **No deletions, no renames, no `.env`/asset changes.**

---

## 3. Data Flow

```
Lemon Squeezy → POST /webhooks/lemon-squeezy
  1. Read raw body: request.get_data()
  2. Read header: request.headers["X-Signature"]
  3. Compute HMAC-SHA256(secret, raw_body) → hexdigest
  4. hmac.compare_digest(expected, header)
     ├─ mismatch / missing header → 401
        ├─ missing/empty body → 400
        ├─ malformed JSON → 400
  5. Parse JSON
  6. meta.event_name == "order_created"?
     ├─ yes → extract email (data.attributes.user_email) + order_id (data.id)
     │        → generate_license_key(email, order_id) → print to stdout → 200
     └─ no  → 200 (acknowledge, prevent LS retries)
```

### Failure modes
- **Empty/missing secret** → 500 (log loudly; misconfiguration, not client error).
- **Missing `X-Signature`** → 401 (cannot verify).
- **Invalid signature** → 401.
- **Empty body** → 400.
- **Malformed JSON** → 400.
- **Missing `data`/`attributes`/`user_email`/`id` in `order_created`** → 400 (log + safe message).
- **Unhandled event type** → 200 (always ACK non-order events so Lemon Squeezy doesn't retry-endlessly).

---

## 4. Success Metrics (Verifiable Goals)
1. `python -c "import app"` runs with no import errors (Flask importable).
2. Flask test client: POST without `X-Signature` → **401**.
3. Flask test client: POST with valid signature + `order_created` payload → **200**, JSON contains `status` and `license_key`; stdout shows `generate_license_key(...)` print.
4. Flask test client: POST with **invalid** signature → **401**.
5. Flask test client: POST with valid signature + malformed JSON → **400**.
6. Flask test client: POST with valid signature + non-`order_created` event → **200** (acknowledged, not processed).

### Verification command (run from `backend/`):
```bash
python -c "import app; app.app.run"  # import smoke test
python -m pytest ../test_webhook_lemon_squeezy.py  # optional, see §6
# OR inline unittest via the test below
```

---

## 5. Implementation Steps

1. Create `backend/` directory (if missing).
2. Create `backend/app.py` with the exact code in §7.
3. Add `flask>=3.0,<4.0` to root `requirements.txt`.
4. (Optional but recommended) Add `backend/test_webhook_lemon_squeezy.py` — a self-contained `unittest` test (Flask `test_client`) covering the 6 success metrics. (Test file is optional per task scope; recommend adding for verification.)

---

## 6. Recommended Test Stub (optional, for verification)

A self-contained `unittest` harness placed at `backend/test_webhook_lemon_squeezy.py`. It sets the env var, imports `app`, and exercises the test client. See the full code block in §8. This mirrors the existing test convention (`test_server.py` uses `unittest` + Flask `test_client`).

---

## 7. Exact Code to Create — `backend/app.py`

```python
"""
backend/app.py — Flask application for receiving and verifying
Lemon Squeezy webhooks.

Verifies the X-Signature header (HMAC-SHA256) on every incoming
POST. On `order_created` events, stubs license-key generation
(key is printed to stdout; persistence is deferred).

Environment:
    LEMON_SQUEEZEY_SIGNATURE_SECRET  — signing secret (REQUIRED)
"""
import hashlib
import hmac
import json
import logging
import os
import uuid

from flask import Flask, jsonify, request

# ── Application setup ─────────────────────────────────────────────────────
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lemon_squeezy_webhook")

SIGNATURE_SECRET = os.environ.get("LEMON_SQUEEZEY_SIGNATURE_SECRET", "")


# ── License key generation (STUB) ─────────────────────────────────────────
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


# ── Webhook endpoint ───────────────────────────────────────────────────────
@app.route("/webhooks/lemon-squeezy", methods=["POST"])
def lemon_squeezy_webhook():
    # 1. Extract signature header
    signature_header = request.headers.get("X-Signature", "")
    if not signature_header:
        logger.warning("Webhook rejected: missing X-Signature header")
        return jsonify({"error": "Missing signature header"}), 401

    # 2. Read raw payload
    raw_payload = request.get_data()
    if not raw_payload:
        logger.warning("Webhook rejected: empty request body")
        return jsonify({"error": "Empty request body"}), 400

    # 3. Compute HMAC-SHA256 and verify
    if not SIGNATURE_SECRET:
        logger.error(
            "LEMON_SQUEEZEY_SIGNATURE_SECRET is not set — webhook "
            "signature verification is disabled"
        )
        return jsonify({"error": "Webhook secret not configured"}), 500

    expected_signature = hmac.new(
        SIGNATURE_SECRET.encode("utf-8"),
        raw_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("Webhook rejected: signature verification failed")
        return jsonify({"error": "Invalid signature"}), 401

    # 4. Parse JSON
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Webhook rejected: payload is not valid JSON")
        return jsonify({"error": "Invalid JSON"}), 400

    # 5. Inspect event name
    event_name = payload.get("meta", {}).get("event_name", "")

    # 6. Handle order_created
    if event_name == "order_created":
        try:
            customer_email = payload["data"]["attributes"]["user_email"]
            order_id = payload["data"]["id"]
        except (KeyError, TypeError) as exc:
            logger.error(
                "Malformed order_created payload — missing field: %s", exc
            )
            return jsonify({"error": "Malformed order_created payload"}), 400

        license_key = generate_license_key(customer_email, order_id)
        logger.info(
            "order_created processed: email=%s order_id=%s license_key=%s",
            customer_email, order_id, license_key,
        )
        return jsonify({"status": "ok", "license_key": license_key}), 200

    # 7. Unhandled event — acknowledge to prevent Lemon Squeezy retries
    logger.info("Ignoring unhandled event: %s", event_name)
    return jsonify({"status": "ignored", "event_name": event_name}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

---

## 8. Full Test Harness — `backend/test_webhook_lemon_squeezy.py` (optional)

```python
"""
Self-contained unit tests for backend/app.py.

Run from the backend/ directory:
    python test_webhook_lemon_squeezy.py
"""
import hashlib
import hmac
import json
import os
import sys
import unittest

os.environ.setdefault("LEMON_SQUEEZEY_SIGNATURE_SECRET", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app  # noqa: E402

SECRET = os.environ["LEMON_SQUEEZEY_SIGNATURE_SECRET"]


def sign(payload: dict) -> dict:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return {"X-Signature": digest, "Content-Type": "application/json"}


class LemonSqueezyWebhookTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _order_created(self, order_id="ord_123", email="buyer@example.com"):
        return {
            "meta": {"event_name": "order_created"},
            "data": {
                "id": order_id,
                "type": "order",
                "attributes": {"user_email": email},
            },
        }

    def test_missing_signature_returns_401(self):
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=json.dumps(self._order_created()),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_invalid_signature_returns_401(self):
        payload = json.dumps(self._order_created(), separators=(",", ":"))
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=payload,
            headers={
                "X-Signature": "deadbeef" * 8,
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(resp.status_code, 401)

    def test_order_created_returns_200(self):
        payload = self._order_created()
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=json.dumps(payload, separators=(",", ":")),
            headers=sign(payload),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["license_key"].startswith("PHARM-"))

    def test_malformed_json_returns_400(self):
        raw = b"{not valid json"
        digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=raw,
            headers={"X-Signature": digest},
        )
        self.assertEqual(resp.status_code, 400)

    def test_unhandled_event_returns_200(self):
        payload = {"meta": {"event_name": "test.event"}, "data": {}}
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=json.dumps(payload, separators=(",", ":")),
            headers=sign(payload),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_missing_email_field_returns_400(self):
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {"id": "ord_456", "type": "order", "attributes": {}},
        }
        resp = self.client.post(
            "/webhooks/lemon-squeezy",
            data=json.dumps(payload, separators=(",", ":")),
            headers=sign(payload),
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

---

## 9. Rollout / Migration Path
- This is a **new, additive** component. No migration needed.
- Deploy target: any WSGI host (gunicorn recommended; already in `archive/requirements.txt`).
- Set `LEMON_SQUEEZEY_SIGNATURE_SECRET` in the deployment environment (see Decision 1 risk).

## 10. Validation Plan
- [ ] `python -m py_compile backend/app.py` — compiles clean.
- [ ] `python test_webhook_lemon_squeezy.py` from `backend/` — 6/6 tests pass.
- [ ] `pip install -r requirements.txt` succeeds with Flask resolved.

## 11. Orphans & Pending (carried to PROJECT_MAP.md)
- Standardize the Lemon Squeezy webhook secret env-var name across `api/lemon_webhook.py`, `archive/licensing/api/webhook.py`, `archive/license_server/api/webhook.py`, and `backend/app.py` (recommend: `LEMON_SQUEEZEY_SIGNATURE_SECRET`). Out of scope for this task.
- Implement real license-key persistence (Redis/SQLite) to back the `generate_license_key` stub. Out of scope.
- Wire `order_created` license creation into `license_gate.py` activation flow (`/api/validate`). Out of scope.
