"""
test_server.py — Comprehensive test suite for server_app.py.

Covers:
  - Health check
  - Paddle webhook (transaction.completed, subscription lifecycle)
  - License creation and DB persistence
  - Email dispatch safety (no crash on missing SMTP)
  - Validate / Activate endpoints
  - Admin endpoints (stats, licenses, reset-hwid)
  - Customer portal endpoints (login, details, reset-hwid)
  - Offline token issuance and verification

Run:  python test_server.py
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

# Ensure archive/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))

# Force test mode and set admin secret before importing server_app
os.environ["WEBHOOK_TEST_MODE"] = "1"
os.environ["SERVER_ADMIN_SECRET"] = "test-admin-secret-12345"
os.environ["SMTP_HOST"] = ""  # Ensure SMTP is skipped
os.environ["CREEM_WEBHOOK_SECRET"] = "test-creem-secret"
os.environ["LEMON_SQUEEZEY_SIGNATURE_SECRET"] = "test-ls-secret"

from server_app import app, _get_db, DATABASE  # noqa: E402


class BaseTestCase(unittest.TestCase):
    """Shared setup: temp DB, Flask test client, seeded license."""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        # Patch DATABASE to use temp file
        import server_app
        self._orig_db = server_app.DATABASE
        server_app.DATABASE = self.tmp_db.name

        self.client = app.test_client()
        self.admin_headers = {"X-Admin-Secret": "test-admin-secret-12345"}

        # Seed a test license directly into the DB
        self._seed_license("PHARM-TEST-0001-AAAA", "alice@example.com")
        self._seed_license("PHARM-TEST-0002-BBBB", "bob@example.com", hwid="hwid-bob-123")

    def tearDown(self):
        import server_app
        server_app.DATABASE = self._orig_db
        try:
            os.unlink(self.tmp_db.name)
        except OSError:
            pass

    def _seed_license(self, key, email, hwid=None, status="active", days=30,
                      subscription_id=None):
        """Insert a license row directly (pushes app context for g access)."""
        with app.app_context():
            db = _get_db()
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=days)
            db.execute(
                "INSERT INTO licenses (license_key, email, status, created_at, expires_at, hwid, subscription_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, email, status, now.isoformat(), expires.isoformat(), hwid,
                 subscription_id),
            )
            db.commit()

    def _create_via_api(self, key="PHARM-API-CREATE-TEST", email="api@test.com"):
        """Create a license via the admin API and return the key."""
        resp = self.client.post(
            "/api/create",
            json={"license_key": key, "email": email, "days": 30},
            headers=self.admin_headers,
        )
        return resp

    def _paddle_headers(self, payload_str: str) -> dict:
        """Generate Paddle-format signature header for a JSON payload."""
        import server_app
        secret = server_app.PADDLE_WEBHOOK_SECRET or "test-secret"
        ts = str(int(time.time()))
        signed = f"{ts}:{payload_str}"
        h1 = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "paddle-signature": f"ts={ts};h1={h1}",
        }


# ══════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════
class TestHealth(BaseTestCase):
    def test_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")


# ══════════════════════════════════════════════════════════════════════
# 2. WEBHOOK — PADDLE (JSON payloads with paddle-signature header)
# ══════════════════════════════════════════════════════════════════════
class TestWebhookPaddle(BaseTestCase):
    def test_paddle_transaction_completed_creates_license(self):
        payload = {
            "event_type": "transaction.completed",
            "data": {
                "id": "txn_test_001",
                "subscription_id": "",
                "custom_data": {"email": "paddle-buyer@test.com"},
                "customer": {"email": "paddle-buyer@test.com"},
                "billing_details": {"email": "paddle-buyer@test.com"},
                "total": {"amount": "5000"},
                "status": "completed",
            },
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("PHARM-", body["license_key"])

        # Verify DB
        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT * FROM licenses WHERE license_key = ?", (body["license_key"],)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "paddle-buyer@test.com")
            self.assertEqual(row["status"], "active")

    def test_paddle_subscription_created_creates_license(self):
        payload = {
            "event_type": "subscription.created",
            "data": {
                "id": "sub_test_001",
                "custom_data": {"email": "sub-created@test.com"},
                "customer": {"email": "sub-created@test.com"},
                "status": "active",
            },
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("PHARM-", body["license_key"])

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT * FROM licenses WHERE license_key = ?", (body["license_key"],)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "sub-created@test.com")
            self.assertEqual(row["subscription_id"], "sub_test_001")

    def test_paddle_subscription_updated_extends_license(self):
        self._seed_license(
            "PHARM-RENEW-0001", "renew@test.com", subscription_id="sub_renew_001",
            days=5,
        )
        payload = {
            "event_type": "subscription.updated",
            "data": {"id": "sub_renew_001", "status": "active"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-RENEW-0001")
        self.assertIn("expires_at", body)

    def test_paddle_subscription_cancelled_revokes(self):
        self._seed_license(
            "PHARM-CANCEL-0001", "cancel@test.com", subscription_id="sub_cancel_001"
        )
        payload = {
            "event_type": "subscription.cancelled",
            "data": {"id": "sub_cancel_001"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "revoked")

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT status FROM licenses WHERE license_key = 'PHARM-CANCEL-0001'"
            ).fetchone()
            self.assertEqual(row["status"], "revoked")

    def test_paddle_subscription_paused_revokes(self):
        self._seed_license(
            "PHARM-PAUSE-0001", "pause@test.com", subscription_id="sub_pause_001"
        )
        payload = {
            "event_type": "subscription.paused",
            "data": {"id": "sub_pause_001"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "revoked")

    def test_paddle_subscription_resumed_reactivates(self):
        self._seed_license(
            "PHARM-RESUME-0001", "resume@test.com", subscription_id="sub_resume_001",
            status="revoked",
        )
        payload = {
            "event_type": "subscription.resumed",
            "data": {"id": "sub_resume_001"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "active")

    def test_paddle_duplicate_subscription_returns_existing(self):
        self._seed_license(
            "PHARM-DUP-SUB-0001", "dup@test.com", subscription_id="sub_dup_001"
        )
        payload = {
            "event_type": "subscription.created",
            "data": {
                "id": "sub_dup_001",
                "custom_data": {"email": "dup@test.com"},
                "customer": {"email": "dup@test.com"},
                "status": "active",
            },
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-DUP-SUB-0001")
        self.assertEqual(body["note"], "already_exists")

    def test_paddle_ignored_event_returns_200(self):
        payload = {"event_type": "transaction.billed", "data": {}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_paddle_missing_signature_returns_400(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/paddle",
                data=json.dumps({"event_type": "transaction.completed"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 400)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_paddle_invalid_signature_returns_403(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/paddle",
                data=json.dumps({"event_type": "transaction.completed"}),
                content_type="application/json",
                headers={"paddle-signature": "ts=12345;h1=invalidhash"},
            )
            self.assertEqual(resp.status_code, 403)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_paddle_no_subscription_id_ignored(self):
        payload = {
            "event_type": "subscription.updated",
            "data": {"id": ""},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "no_subscription_id")

    def test_paddle_unknown_subscription_ignored(self):
        payload = {
            "event_type": "subscription.updated",
            "data": {"id": "sub_unknown_999"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "license_not_found")

    def test_paddle_renewal_extends_from_now_if_expired(self):
        self._seed_license(
            "PHARM-RENEW-PAST-01", "past@test.com", subscription_id="sub_past_001",
            days=-5,
        )
        payload = {
            "event_type": "subscription.updated",
            "data": {"id": "sub_past_001", "status": "active"},
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        headers = self._paddle_headers(payload_str)
        resp = self.client.post(
            "/api/webhook/paddle",
            data=payload_str,
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        new_expiry = datetime.fromisoformat(body["expires_at"])
        self.assertGreater(new_expiry.date(), datetime.now(timezone.utc).date())


# ══════════════════════════════════════════════════════════════════════
# 2B. WEBHOOK — CREEM (base64 HMAC-SHA256 over raw body, creem-signature header)
# ══════════════════════════════════════════════════════════════════════
class TestWebhookCreem(BaseTestCase):
    def _creem_headers(self, raw_body: bytes) -> dict:
        import server_app
        secret = server_app.CREEM_WEBHOOK_SECRET or "test-secret"
        sig = base64.b64encode(
            hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        return {
            "Content-Type": "application/json",
            "creem-signature": sig,
        }

    def test_creem_checkout_completed_creates_license(self):
        payload = {
            "id": "evt_creem_001",
            "eventType": "checkout.completed",
            "object": {
                "id": "chk_creem_001",
                "customer": {"email": "creem-buyer@test.com"},
                "subscription_id": "sub_creem_001",
                "order": {"amount": "50.00"},
            },
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("license_key", body)
        with app.app_context():
            row = _get_db().execute(
                "SELECT * FROM licenses WHERE subscription_id = ?", ("sub_creem_001",)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["email"], "creem-buyer@test.com")
        self.assertEqual(row["status"], "active")

    def test_creem_subscription_paid_extends_license(self):
        self._seed_license(
            "PHARM-CREEM-RENEW-01", "renew@test.com", subscription_id="sub_creem_renew",
            days=5,
        )
        payload = {
            "id": "evt_creem_renew",
            "eventType": "subscription.paid",
            "object": {"id": "sub_creem_renew", "amount": "50.00"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("expires_at", body)

    def test_creem_subscription_canceled_revokes(self):
        self._seed_license(
            "PHARM-CREEM-CANCEL", "cancel@test.com", subscription_id="sub_creem_cancel"
        )
        payload = {
            "id": "evt_creem_cancel",
            "eventType": "subscription.canceled",
            "object": {"id": "sub_creem_cancel"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "revoked")

    def test_creem_subscription_expired_revokes(self):
        self._seed_license(
            "PHARM-CREEM-EXPIRE", "expire@test.com", subscription_id="sub_creem_expire"
        )
        payload = {
            "id": "evt_creem_expire",
            "eventType": "subscription.expired",
            "object": {"id": "sub_creem_expire"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "revoked")

    def test_creem_subscription_paused_revokes(self):
        self._seed_license(
            "PHARM-CREEM-PAUSE", "pause@test.com", subscription_id="sub_creem_pause"
        )
        payload = {
            "id": "evt_creem_pause",
            "eventType": "subscription.paused",
            "object": {"id": "sub_creem_pause"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "revoked")

    def test_creem_subscription_active_reactivates(self):
        self._seed_license(
            "PHARM-CREEM-ACTIVE", "active@test.com", subscription_id="sub_creem_active",
            status="revoked",
        )
        payload = {
            "id": "evt_creem_active",
            "eventType": "subscription.active",
            "object": {"id": "sub_creem_active"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "active")

    def test_creem_subscription_resumed_reactivates(self):
        self._seed_license(
            "PHARM-CREEM-RESUME", "resume@test.com", subscription_id="sub_creem_resume",
            status="revoked",
        )
        payload = {
            "id": "evt_creem_resume",
            "eventType": "subscription.resumed",
            "object": {"id": "sub_creem_resume"},
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "active")

    def test_creem_duplicate_subscription_returns_existing(self):
        self._seed_license(
            "PHARM-CREEM-DUP", "dup@test.com", subscription_id="sub_creem_dup"
        )
        payload = {
            "id": "evt_creem_dup",
            "eventType": "checkout.completed",
            "object": {
                "id": "chk_creem_dup",
                "customer": {"email": "dup2@test.com"},
                "subscription_id": "sub_creem_dup",
                "order": {"amount": "50.00"},
            },
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-CREEM-DUP")
        self.assertEqual(body["note"], "already_exists")

    def test_creem_ignored_event_returns_200(self):
        payload = {"eventType": "checkout.updated", "object": {}}
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/creem",
            data=raw,
            headers=self._creem_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_creem_missing_signature_returns_400(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/creem",
                data=json.dumps({"eventType": "checkout.completed"}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 400)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_creem_invalid_signature_returns_403(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/creem",
                data=json.dumps({"eventType": "checkout.completed"}),
                content_type="application/json",
                headers={"creem-signature": "invalidsignature"},
            )
            self.assertEqual(resp.status_code, 403)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_creem_test_mode_skips_signature(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = True
        try:
            payload = {
                "eventType": "checkout.completed",
                "object": {
                    "customer": {"email": "testmode@test.com"},
                    "subscription_id": "sub_testmode",
                    "order": {"amount": "50.00"},
                },
            }
            raw = json.dumps(payload).encode()
            resp = self.client.post(
                "/api/webhook/creem",
                data=raw,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["status"], "ok")
        finally:
            server_app.WEBHOOK_TEST_MODE = orig


# ══════════════════════════════════════════════════════════════════════
# 2C. WEBHOOK — LEMON SQUEEZY (HMAC-SHA256 hexdigest, X-Signature header)
# ══════════════════════════════════════════════════════════════════════
class TestWebhookLemonSqueezy(BaseTestCase):
    def _ls_headers(self, raw_body: bytes) -> dict:
        import server_app
        secret = server_app.LEMON_WEBHOOK_SECRET or "test-secret"
        sig = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Signature": sig,
        }

    def test_ls_order_created_creates_license(self):
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {
                "id": "ord_ls_001",
                "attributes": {"user_email": "ls-buyer@test.com"},
            },
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/lemon-squeezy",
            data=raw,
            headers=self._ls_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("license_key", body)
        with app.app_context():
            row = _get_db().execute(
                "SELECT * FROM licenses WHERE subscription_id = ?", ("ord_ls_001",)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["email"], "ls-buyer@test.com")
        self.assertEqual(row["status"], "active")

    def test_ls_duplicate_order_returns_existing(self):
        self._seed_license(
            "PHARM-LS-DUP-001", "dup@test.com", subscription_id="ord_ls_dup"
        )
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {
                "id": "ord_ls_dup",
                "attributes": {"user_email": "dup2@test.com"},
            },
        }
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/lemon-squeezy",
            data=raw,
            headers=self._ls_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-LS-DUP-001")
        self.assertEqual(body["note"], "already_exists")

    def test_ls_ignored_event_returns_200(self):
        payload = {"meta": {"event_name": "subscription_created"}, "data": {}}
        raw = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/webhook/lemon-squeezy",
            data=raw,
            headers=self._ls_headers(raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_ls_missing_signature_returns_400(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/lemon-squeezy",
                data=json.dumps({"meta": {"event_name": "order_created"}}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 400)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_ls_invalid_signature_returns_401(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/lemon-squeezy",
                data=json.dumps({"meta": {"event_name": "order_created"}}),
                content_type="application/json",
                headers={"X-Signature": "deadbeef"},
            )
            self.assertEqual(resp.status_code, 401)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    def test_ls_test_mode_skips_signature(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = True
        try:
            payload = {
                "meta": {"event_name": "order_created"},
                "data": {
                    "id": "ord_ls_testmode",
                    "attributes": {"user_email": "ls-testmode@test.com"},
                },
            }
            raw = json.dumps(payload).encode()
            resp = self.client.post(
                "/api/webhook/lemon-squeezy",
                data=raw,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["status"], "ok")
        finally:
            server_app.WEBHOOK_TEST_MODE = orig


# ══════════════════════════════════════════════════════════════════════
# 3. EMAIL DISPATCH SAFETY
# ══════════════════════════════════════════════════════════════════════
class TestEmailSafety(BaseTestCase):
    def test_send_license_email_returns_false_without_smtp(self):
        from server_app import send_license_email
        result = send_license_email("anyone@test.com", "PHARM-FAKE-0000-0000")
        self.assertFalse(result)

    def test_send_license_email_rejects_invalid_email(self):
        from server_app import send_license_email
        result = send_license_email("not-an-email", "PHARM-FAKE-0000-0000")
        self.assertFalse(result)

    def test_send_license_email_rejects_empty_email(self):
        from server_app import send_license_email
        result = send_license_email("", "PHARM-FAKE-0000-0000")
        self.assertFalse(result)


# ══════════════════════════════════════════════════════════════════════
# 4. VALIDATE ENDPOINT
# ══════════════════════════════════════════════════════════════════════
class TestValidate(BaseTestCase):
    def test_validate_valid_key(self):
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST-0001-AAAA", "device_id": "dev-001", "hwid": "hwid-001"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["valid"])
        self.assertIn("offline_token", body)

    def test_validate_missing_fields(self):
        resp = self.client.post("/api/validate", json={})
        self.assertEqual(resp.status_code, 400)

    def test_validate_unknown_key(self):
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-DOES-NOT-EXIST", "device_id": "dev-001"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["valid"])

    def test_validate_hwid_mismatch_rejects(self):
        resp = self.client.post(
            "/api/validate",
            json={
                "license_key": "PHARM-TEST-0002-BBBB",
                "device_id": "dev-bob",
                "hwid": "hwid-different-999",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_validate_expired_key(self):
        self._seed_license("PHARM-EXPIRED-0001", "expired@test.com", days=-1)
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-EXPIRED-0001", "device_id": "dev-001"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["valid"])

    def test_validate_first_activation_binds_device(self):
        self._seed_license("PHARM-FRESH-0001", "fresh@test.com")
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-FRESH-0001", "device_id": "dev-fresh", "hwid": "hwid-fresh"},
        )
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            db = _get_db()
            row = db.execute("SELECT device_id, hwid FROM licenses WHERE license_key='PHARM-FRESH-0001'").fetchone()
            self.assertEqual(row["device_id"], "dev-fresh")
            self.assertEqual(row["hwid"], "hwid-fresh")


# ══════════════════════════════════════════════════════════════════════
# 5. ACTIVATE ENDPOINT
# ══════════════════════════════════════════════════════════════════════
class TestActivate(BaseTestCase):
    def test_activate_fresh_license(self):
        self._seed_license("PHARM-ACTV-0001", "actv@test.com")
        resp = self.client.post(
            "/api/activate",
            json={"license_key": "PHARM-ACTV-0001", "device_id": "dev-actv", "hwid": "hwid-actv"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["activated"])

    def test_activate_device_conflict(self):
        self._seed_license("PHARM-ACTV-0002", "conflict@test.com")
        self.client.post(
            "/api/activate",
            json={"license_key": "PHARM-ACTV-0002", "device_id": "device-a"},
        )
        resp = self.client.post(
            "/api/activate",
            json={"license_key": "PHARM-ACTV-0002", "device_id": "device-b"},
        )
        self.assertEqual(resp.status_code, 409)

    def test_activate_hwid_mismatch(self):
        self._seed_license("PHARM-ACTV-0003", "hwid@test.com", hwid="hwid-original")
        resp = self.client.post(
            "/api/activate",
            json={"license_key": "PHARM-ACTV-0003", "device_id": "dev-new", "hwid": "hwid-different"},
        )
        self.assertEqual(resp.status_code, 403)


# ══════════════════════════════════════════════════════════════════════
# 6. ADMIN — CREATE
# ══════════════════════════════════════════════════════════════════════
class TestAdminCreate(BaseTestCase):
    def test_create_license(self):
        resp = self._create_via_api()
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertEqual(body["status"], "active")
        self.assertIn("PHARM-", body["license_key"])

    def test_create_duplicate_returns_409(self):
        self._create_via_api("PHARM-DUP-00001")
        resp = self._create_via_api("PHARM-DUP-00001")
        self.assertEqual(resp.status_code, 409)

    def test_create_unauthorized(self):
        resp = self.client.post(
            "/api/create",
            json={"license_key": "PHARM-NOPE-0001"},
            headers={"X-Admin-Secret": "wrong-secret"},
        )
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════
# 7. ADMIN — STATS
# ══════════════════════════════════════════════════════════════════════
class TestAdminStats(BaseTestCase):
    def test_stats_returns_counts(self):
        resp = self.client.get("/admin/api/stats", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("total", body)
        self.assertIn("active", body)
        self.assertIn("bound", body)
        self.assertGreaterEqual(body["total"], 2)

    def test_stats_unauthorized(self):
        resp = self.client.get("/admin/api/stats")
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════
# 8. ADMIN — LICENSES LIST
# ══════════════════════════════════════════════════════════════════════
class TestAdminLicenses(BaseTestCase):
    def test_list_licenses(self):
        resp = self.client.get("/admin/api/licenses", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("licenses", body)
        self.assertGreaterEqual(body["total"], 2)

    def test_search_by_email(self):
        resp = self.client.get("/admin/api/licenses?q=alice", headers=self.admin_headers)
        body = resp.get_json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["licenses"][0]["email"], "alice@example.com")

    def test_search_by_key(self):
        resp = self.client.get("/admin/api/licenses?q=0002-BBBB", headers=self.admin_headers)
        body = resp.get_json()
        self.assertEqual(body["total"], 1)

    def test_filter_by_status(self):
        resp = self.client.get("/admin/api/licenses?status=active", headers=self.admin_headers)
        body = resp.get_json()
        for lic in body["licenses"]:
            self.assertEqual(lic["status"], "active")


# ══════════════════════════════════════════════════════════════════════
# 9. ADMIN — HWID RESET
# ══════════════════════════════════════════════════════════════════════
class TestAdminResetHwid(BaseTestCase):
    def test_reset_hwid(self):
        resp = self.client.post(
            "/admin/api/reset-hwid",
            json={"license_key": "PHARM-TEST-0002-BBBB"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 200)
        with app.app_context():
            db = _get_db()
            row = db.execute("SELECT hwid, device_id FROM licenses WHERE license_key='PHARM-TEST-0002-BBBB'").fetchone()
            self.assertIsNone(row["hwid"])
            self.assertIsNone(row["device_id"])

    def test_reset_hwid_unknown_key(self):
        resp = self.client.post(
            "/admin/api/reset-hwid",
            json={"license_key": "PHARM-NOPE-9999"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 404)


# ══════════════════════════════════════════════════════════════════════
# 10. ADMIN — ACTIVITY
# ══════════════════════════════════════════════════════════════════════
class TestAdminActivity(BaseTestCase):
    def test_activity_returns_list(self):
        resp = self.client.get("/admin/api/activity", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("activity", body)
        self.assertGreaterEqual(len(body["activity"]), 2)


# ══════════════════════════════════════════════════════════════════════
# 11. CUSTOMER PORTAL — LOGIN
# ══════════════════════════════════════════════════════════════════════
class TestPortalLogin(BaseTestCase):
    def test_portal_login_success(self):
        resp = self.client.post(
            "/api/portal/login",
            json={"license_key": "PHARM-TEST-0001-AAAA"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("session_token", body)
        self.assertIn("license", body)
        self.assertEqual(body["license"]["email"], "alice@example.com")

    def test_portal_login_unknown_key(self):
        resp = self.client.post(
            "/api/portal/login",
            json={"license_key": "PHARM-DOES-NOT-EXIST"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_portal_login_missing_key(self):
        resp = self.client.post("/api/portal/login", json={})
        self.assertEqual(resp.status_code, 400)


# ══════════════════════════════════════════════════════════════════════
# 12. CUSTOMER PORTAL — DETAILS
# ══════════════════════════════════════════════════════════════════════
class TestPortalDetails(BaseTestCase):
    def _get_token(self):
        resp = self.client.post(
            "/api/portal/login",
            json={"license_key": "PHARM-TEST-0001-AAAA"},
        )
        return resp.get_json()["session_token"]

    def test_portal_details_success(self):
        token = self._get_token()
        resp = self.client.get(
            "/api/portal/details",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["license"]["license_key"], "PHARM-TEST-0001-AAAA")

    def test_portal_details_no_token(self):
        resp = self.client.get("/api/portal/details")
        self.assertEqual(resp.status_code, 401)

    def test_portal_details_bad_token(self):
        resp = self.client.get(
            "/api/portal/details",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════
# 13. CUSTOMER PORTAL — RESET HWID
# ══════════════════════════════════════════════════════════════════════
class TestPortalResetHwid(BaseTestCase):
    def _get_token(self):
        resp = self.client.post(
            "/api/portal/login",
            json={"license_key": "PHARM-TEST-0002-BBBB"},
        )
        return resp.get_json()["session_token"]

    def test_portal_reset_hwid_success(self):
        token = self._get_token()
        resp = self.client.post(
            "/api/portal/reset-hwid",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        with app.app_context():
            db = _get_db()
            row = db.execute("SELECT hwid FROM licenses WHERE license_key='PHARM-TEST-0002-BBBB'").fetchone()
            self.assertIsNone(row["hwid"])

    def test_portal_reset_hwid_cooldown(self):
        token = self._get_token()
        self.client.post(
            "/api/portal/reset-hwid",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = self.client.post(
            "/api/portal/reset-hwid",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 429)


# ══════════════════════════════════════════════════════════════════════
# 14. OFFLINE TOKEN
# ══════════════════════════════════════════════════════════════════════
class TestOfflineToken(BaseTestCase):
    def test_validate_returns_offline_token(self):
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST-0001-AAAA", "device_id": "dev-token", "hwid": "hwid-token"},
        )
        body = resp.get_json()
        self.assertIn("offline_token", body)
        from server_app import verify_offline_token
        payload = verify_offline_token(body["offline_token"])
        self.assertIsNotNone(payload)
        self.assertEqual(payload["license_key"], "PHARM-TEST-0001-AAAA")


# ══════════════════════════════════════════════════════════════════════
# 15. ADMIN — OLD RESET ENDPOINT
# ══════════════════════════════════════════════════════════════════════
class TestAdminResetOld(BaseTestCase):
    def test_old_reset_hwid_endpoint(self):
        resp = self.client.post(
            "/api/reset-hwid",
            json={"license_key": "PHARM-TEST-0002-BBBB"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# 16. VERIFY TOKEN ENDPOINT
# ══════════════════════════════════════════════════════════════════════
class TestVerifyToken(BaseTestCase):
    def test_verify_valid_token(self):
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST-0001-AAAA", "device_id": "dev-vt"},
        )
        token = resp.get_json()["offline_token"]
        resp = self.client.post(
            "/api/verify-token",
            json={"token": token},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["valid"])

    def test_verify_invalid_token(self):
        resp = self.client.post(
            "/api/verify-token",
            json={"token": "garbage-token"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["valid"])


# ══════════════════════════════════════════════════════════════════════
# 17. ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════════
class TestErrorHandlers(BaseTestCase):
    def test_404(self):
        resp = self.client.get("/api/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_405(self):
        resp = self.client.put("/api/health")
        self.assertEqual(resp.status_code, 405)


# ══════════════════════════════════════════════════════════════════════
# 18. HTML PAGES
# ══════════════════════════════════════════════════════════════════════
class TestHtmlPages(BaseTestCase):
    def test_landing_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"PharmacyPro", resp.data)
        self.assertIn(b"$50", resp.data)

    def test_admin_page(self):
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Admin Dashboard", resp.data)

    def test_portal_page(self):
        resp = self.client.get("/portal")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"License Portal", resp.data)


if __name__ == "__main__":
    print("=" * 60)
    print("  PharmacyPro Server — Full Test Suite (Paddle Only)")
    print("=" * 60)
    print()
    unittest.main(verbosity=2)
