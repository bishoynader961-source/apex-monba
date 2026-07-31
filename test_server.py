"""
test_server.py — Comprehensive test suite for server_app.py.

Covers:
  - Health check
  - Webhook payload parsing (Paddle + Lemon Squeezy)
  - License creation and DB persistence
  - Email dispatch safety (no crash on missing SMTP)
  - Validate / Activate endpoints
  - Admin endpoints (stats, licenses, reset-hwid)
  - Customer portal endpoints (login, details, reset-hwid)
  - Offline token issuance and verification

Run:  python test_server.py
"""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

# Ensure archive/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))

# Force test mode and set admin secret before importing server_app
os.environ["WEBHOOK_TEST_MODE"] = "1"
os.environ["SERVER_ADMIN_SECRET"] = "test-admin-secret-12345"
os.environ["SMTP_HOST"] = ""  # Ensure SMTP is skipped

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


# ══════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════
class TestHealth(BaseTestCase):
    def test_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")


# ══════════════════════════════════════════════════════════════════════
# 2. WEBHOOK — PADDLE
# ══════════════════════════════════════════════════════════════════════
class TestWebhookPaddle(BaseTestCase):
    def test_paddle_payment_success_creates_license(self):
        payload = {
            "alert_name": "payment_success",
            "alert_status": "active",
            "email": "paddle-buyer@test.com",
            "transaction_id": "txn_test_999",
        }
        resp = self.client.post(
            "/api/webhook/paddle",
            data=urlencode(payload),
            content_type="application/x-www-form-urlencoded",
            headers={"paddle-signature": "test-sig"},
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

    def test_paddle_ignored_event_returns_200(self):
        payload = {"alert_name": "subscription_created", "alert_status": "active"}
        resp = self.client.post(
            "/api/webhook/paddle",
            data=urlencode(payload),
            content_type="application/x-www-form-urlencoded",
            headers={"paddle-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_paddle_missing_signature_returns_400(self):
        """Without test mode, missing signature should return 400."""
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/paddle",
                data=urlencode({"alert_name": "payment_success"}),
                content_type="application/x-www-form-urlencoded",
            )
            self.assertEqual(resp.status_code, 400)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig


# ══════════════════════════════════════════════════════════════════════
# 3. WEBHOOK — LEMON SQUEEZY
# ══════════════════════════════════════════════════════════════════════
class TestWebhookLemonSqueezy(BaseTestCase):
    def test_ls_order_created_creates_license(self):
        payload = {
            "meta": {"event_name": "order_created", "test_mode": True},
            "data": {
                "id": "ord_test_001",
                "type": "orders",
                "attributes": {
                    "status": "paid",
                    "user_email": "ls-buyer@test.com",
                    "user_name": "Test LS Buyer",
                    "total": 4900,
                    "total_formatted": "$49.00",
                    "currency": "USD",
                    "identifier": "TEST-ORDER-001",
                },
            },
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
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
            self.assertEqual(row["email"], "ls-buyer@test.com")

    def test_ls_ignored_event_returns_200(self):
        payload = {
            "meta": {"event_name": "refund_created"},
            "data": {"attributes": {}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")

    def test_ls_missing_signature_returns_400(self):
        import server_app
        orig = server_app.WEBHOOK_TEST_MODE
        server_app.WEBHOOK_TEST_MODE = False
        try:
            resp = self.client.post(
                "/api/webhook/lemonsqueezy",
                data=json.dumps({"meta": {"event_name": "order_created"}, "data": {"attributes": {}}}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 400)
        finally:
            server_app.WEBHOOK_TEST_MODE = orig

    # ── subscription_created tests ────────────────────────────────
    def test_ls_subscription_created_creates_license(self):
        payload = {
            "meta": {"event_name": "subscription_created"},
            "data": {"attributes": {
                "user_email": "sub-created@test.com",
                "subscription_id": 99001,
            }},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        key = body["license_key"]

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT * FROM licenses WHERE license_key = ?", (key,)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "sub-created@test.com")
            self.assertEqual(row["subscription_id"], "99001")
            self.assertEqual(row["status"], "active")

    def test_ls_order_created_stores_subscription_id(self):
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {"attributes": {
                "user_email": "order-sub@test.com",
                "subscription_id": 99002,
            }},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        key = resp.get_json()["license_key"]

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT subscription_id FROM licenses WHERE license_key = ?", (key,)
            ).fetchone()
            self.assertEqual(row["subscription_id"], "99002")

    def test_ls_duplicate_subscription_returns_existing(self):
        self._seed_license(
            "PHARM-DUP-SUB-0001", "dup@test.com", subscription_id="99099"
        )
        payload = {
            "meta": {"event_name": "order_created"},
            "data": {"attributes": {
                "user_email": "dup@test.com",
                "subscription_id": 99099,
            }},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-DUP-SUB-0001")
        self.assertEqual(body["note"], "already_exists")

    # ── subscription_payment_success tests ────────────────────────
    def test_ls_subscription_payment_success_extends(self):
        self._seed_license(
            "PHARM-RENEW-0001", "renew@test.com", subscription_id="99100",
            days=5,
        )

        # Capture original expiry
        with app.app_context():
            db = _get_db()
            orig = db.execute(
                "SELECT expires_at FROM licenses WHERE license_key = 'PHARM-RENEW-0001'"
            ).fetchone()["expires_at"]

        payload = {
            "meta": {"event_name": "subscription_payment_success"},
            "data": {"attributes": {"subscription_id": 99100}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["license_key"], "PHARM-RENEW-0001")
        new_expiry = datetime.fromisoformat(body["expires_at"])

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT expires_at, status FROM licenses WHERE license_key = 'PHARM-RENEW-0001'"
            ).fetchone()
            stored_expiry = datetime.fromisoformat(row["expires_at"])
            self.assertEqual(row["status"], "active")
            # New expiry should be > original
            self.assertGreater(stored_expiry.isoformat(), orig)

    def test_ls_subscription_payment_success_no_subscription_ignored(self):
        payload = {
            "meta": {"event_name": "subscription_payment_success"},
            "data": {"attributes": {"subscription_id": 0}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "no_subscription_id")

    def test_ls_subscription_payment_success_unknown_sub_ignored(self):
        payload = {
            "meta": {"event_name": "subscription_payment_success"},
            "data": {"attributes": {"subscription_id": 99999}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "license_not_found")

    # ── subscription_cancelled tests ──────────────────────────────
    def test_ls_subscription_cancelled_revokes(self):
        self._seed_license(
            "PHARM-CANCEL-0001", "cancel@test.com", subscription_id="99200"
        )
        payload = {
            "meta": {"event_name": "subscription_cancelled"},
            "data": {"attributes": {"subscription_id": 99200}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
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

    def test_ls_subscription_cancelled_unknown_sub_ignored(self):
        payload = {
            "meta": {"event_name": "subscription_cancelled"},
            "data": {"attributes": {"subscription_id": 88888}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "license_not_found")

    # ── subscription_expired tests ────────────────────────────────
    def test_ls_subscription_expired_marks_expired(self):
        self._seed_license(
            "PHARM-EXPIRE-0001", "expire@test.com", subscription_id="99300"
        )
        payload = {
            "meta": {"event_name": "subscription_expired"},
            "data": {"attributes": {"subscription_id": 99300}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "expired")

        with app.app_context():
            db = _get_db()
            row = db.execute(
                "SELECT status FROM licenses WHERE license_key = 'PHARM-EXPIRE-0001'"
            ).fetchone()
            self.assertEqual(row["status"], "expired")

    def test_ls_subscription_expired_unknown_sub_ignored(self):
        payload = {
            "meta": {"event_name": "subscription_expired"},
            "data": {"attributes": {"subscription_id": 77777}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["reason"], "license_not_found")

    # ── subscription_payment_success extends from now when expiry is past ──
    def test_ls_renewal_extends_from_now_if_expired(self):
        self._seed_license(
            "PHARM-RENEW-PAST-01", "past@test.com", subscription_id="99400",
            days=-5,
        )
        payload = {
            "meta": {"event_name": "subscription_payment_success"},
            "data": {"attributes": {"subscription_id": 99400}},
        }
        resp = self.client.post(
            "/api/webhook/lemonsqueezy",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"x-signature": "test-sig"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        new_expiry = datetime.fromisoformat(body["expires_at"])
        # Should extend from now, not from the past expiry — expiry should be ~25-30 days ahead
        self.assertGreater(new_expiry.date(), datetime.now(timezone.utc).date())


# ══════════════════════════════════════════════════════════════════════
# 4. EMAIL DISPATCH SAFETY
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
# 5. VALIDATE ENDPOINT
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
        """License bound to hwid-bob-123, different hwid should fail."""
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
        # Check DB shows binding
        with app.app_context():
            db = _get_db()
            row = db.execute("SELECT device_id, hwid FROM licenses WHERE license_key='PHARM-FRESH-0001'").fetchone()
            self.assertEqual(row["device_id"], "dev-fresh")
            self.assertEqual(row["hwid"], "hwid-fresh")


# ══════════════════════════════════════════════════════════════════════
# 6. ACTIVATE ENDPOINT
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
        """License already bound to device-a, activating device-b should 409."""
        self._seed_license("PHARM-ACTV-0002", "conflict@test.com")
        # Bind first
        self.client.post(
            "/api/activate",
            json={"license_key": "PHARM-ACTV-0002", "device_id": "device-a"},
        )
        # Try second device
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
# 7. ADMIN — CREATE
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
# 8. ADMIN — STATS
# ══════════════════════════════════════════════════════════════════════
class TestAdminStats(BaseTestCase):
    def test_stats_returns_counts(self):
        resp = self.client.get("/admin/api/stats", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("total", body)
        self.assertIn("active", body)
        self.assertIn("bound", body)
        self.assertGreaterEqual(body["total"], 2)  # seeded licenses

    def test_stats_unauthorized(self):
        resp = self.client.get("/admin/api/stats")
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════════════
# 9. ADMIN — LICENSES LIST
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
# 10. ADMIN — HWID RESET
# ══════════════════════════════════════════════════════════════════════
class TestAdminResetHwid(BaseTestCase):
    def test_reset_hwid(self):
        resp = self.client.post(
            "/admin/api/reset-hwid",
            json={"license_key": "PHARM-TEST-0002-BBBB"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 200)
        # Verify cleared
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
# 11. ADMIN — ACTIVITY
# ══════════════════════════════════════════════════════════════════════
class TestAdminActivity(BaseTestCase):
    def test_activity_returns_list(self):
        resp = self.client.get("/admin/api/activity", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("activity", body)
        self.assertGreaterEqual(len(body["activity"]), 2)


# ══════════════════════════════════════════════════════════════════════
# 12. CUSTOMER PORTAL — LOGIN
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
# 13. CUSTOMER PORTAL — DETAILS
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
# 14. CUSTOMER PORTAL — RESET HWID
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
        # Verify cleared
        with app.app_context():
            db = _get_db()
            row = db.execute("SELECT hwid FROM licenses WHERE license_key='PHARM-TEST-0002-BBBB'").fetchone()
            self.assertIsNone(row["hwid"])

    def test_portal_reset_hwid_cooldown(self):
        """Second reset within 30 days should 429."""
        token = self._get_token()
        # First reset
        self.client.post(
            "/api/portal/reset-hwid",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Second reset — should hit cooldown
        resp = self.client.post(
            "/api/portal/reset-hwid",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 429)


# ══════════════════════════════════════════════════════════════════════
# 15. OFFLINE TOKEN
# ══════════════════════════════════════════════════════════════════════
class TestOfflineToken(BaseTestCase):
    def test_validate_returns_offline_token(self):
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST-0001-AAAA", "device_id": "dev-token", "hwid": "hwid-token"},
        )
        body = resp.get_json()
        self.assertIn("offline_token", body)
        # Verify the token
        from server_app import verify_offline_token
        payload = verify_offline_token(body["offline_token"])
        self.assertIsNotNone(payload)
        self.assertEqual(payload["license_key"], "PHARM-TEST-0001-AAAA")


# ══════════════════════════════════════════════════════════════════════
# 16. ADMIN — OLD RESET ENDPOINT
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
# 17. VERIFY TOKEN ENDPOINT
# ══════════════════════════════════════════════════════════════════════
class TestVerifyToken(BaseTestCase):
    def test_verify_valid_token(self):
        # Create a token first
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST-0001-AAAA", "device_id": "dev-vt"},
        )
        token = resp.get_json()["offline_token"]
        # Verify it
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
# 18. ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════════
class TestErrorHandlers(BaseTestCase):
    def test_404(self):
        resp = self.client.get("/api/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_405(self):
        resp = self.client.put("/api/health")
        self.assertEqual(resp.status_code, 405)


# ══════════════════════════════════════════════════════════════════════
# 19. HTML PAGES
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
    print("  PharmacyPro Server — Full Test Suite")
    print("=" * 60)
    print()
    unittest.main(verbosity=2)
