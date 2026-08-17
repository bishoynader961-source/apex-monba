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
import db  # noqa: E402
db.init_db(":memory:")
from app import app  # noqa: E402

SECRET = os.environ["LEMON_SQUEEZEY_SIGNATURE_SECRET"]


def sign(payload: dict) -> dict:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return {"X-Signature": digest, "Content-Type": "application/json"}


class LemonSqueezyWebhookTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

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
        row = db.get_license(body["license_key"])
        self.assertIsNotNone(row, "License key should be persisted in the database")

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


class ValidateEndpointTests(unittest.TestCase):
    """Test suite for POST /api/validate with isolated in-memory database."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()
        # Unregistered / unbound key (active, hardware_id = NULL)
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
            json={"license_key": "PHARM-NONEXISTENT", "hardware_id": "hw-x"},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"], "License key not found")

    def test_validate_revoked_key(self):
        """Revoked license → 403."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0003", "hardware_id": "hw-x"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "License is revoked")

    def test_validate_bind_new_device(self):
        """First activation (NULL hardware_id) → 200, binds hardware_id."""
        resp = self.client.post(
            "/api/validate",
            json={"license_key": "PHARM-TEST0001", "hardware_id": "hw-new"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["message"], "Device bound successfully")
        # Verify the DB was actually updated
        row = db.get_license("PHARM-TEST0001")
        self.assertEqual(row["hardware_id"], "hw-new")

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
            json={"license_key": "PHARM-TEST0002", "hardware_id": "hw-different"},
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
        """Invalid JSON body → 400."""
        resp = self.client.post(
            "/api/validate",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_validate_webhook_to_validate_flow(self):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
