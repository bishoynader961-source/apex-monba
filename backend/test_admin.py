"""
Self-contained unit tests for the Admin CLI (backend/admin.py) and
Admin API endpoint (POST /api/admin/manage in backend/app.py).

Run from the backend/ directory:
    python test_admin.py

Or from the project root:
    python backend/test_admin.py
"""
import os
import sys
import unittest

os.environ.setdefault("ADMIN_SECRET", "test-admin-secret-9999")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
db.init_db(":memory:")
from app import app, ADMIN_SECRET  # noqa: E402
from admin import cli_list, cli_revoke, cli_reset, cli_generate  # noqa: E402

ADMIN_HEADERS = {"X-Admin-Secret": ADMIN_SECRET}


class AdminCLITests(unittest.TestCase):
    """Tests for the importable CLI functions in admin.py."""

    def setUp(self):
        db.clear_licenses()

    def test_cli_list_empty(self):
        """List on empty DB prints 'No licenses found'."""
        output = cli_list()
        self.assertIn("No licenses found", output)

    def test_cli_list_with_licenses(self):
        """List renders an ASCII table containing all license fields."""
        db.insert_license("PHARM-LST0001", "alice@example.com", "ord_001")
        db.insert_license("PHARM-LST0002", "bob@example.com", "ord_002")
        output = cli_list()
        self.assertIn("PHARM-LST0001", output)
        self.assertIn("PHARM-LST0002", output)
        self.assertIn("alice@example.com", output)
        self.assertIn("bob@example.com", output)
        self.assertIn("License Key", output)
        self.assertIn("Customer Email", output)
        self.assertIn("Status", output)
        self.assertIn("Hardware ID", output)
        self.assertIn("Created At", output)

    def test_cli_revoke_success(self):
        """Revoke sets status to 'revoked' in the database."""
        db.insert_license("PHARM-REV0001", "revoke@example.com", "ord_001")
        msg = cli_revoke("PHARM-REV0001")
        self.assertIn("revoked", msg.lower())
        row = db.get_license("PHARM-REV0001")
        self.assertEqual(row["status"], "revoked")

    def test_cli_revoke_already_revoked(self):
        """Revoking an already-revoked key reports already revoked."""
        db.insert_license("PHARM-REV0002", "revoke2@example.com", "ord_002")
        db.update_license_status("PHARM-REV0002", "revoked")
        msg = cli_revoke("PHARM-REV0002")
        self.assertIn("already revoked", msg.lower())

    def test_cli_revoke_not_found(self):
        """Revoke on non-existent key prints not-found message."""
        msg = cli_revoke("PHARM-NONEXISTENT-KEY")
        self.assertIn("not found", msg.lower())

    def test_cli_reset_success(self):
        """Reset clears the hardware_id for a bound license."""
        db.insert_license("PHARM-RST0001", "reset@example.com", "ord_001")
        db.bind_hardware_id("PHARM-RST0001", "hw-device-001")
        msg = cli_reset("PHARM-RST0001")
        self.assertIn("reset", msg.lower())
        row = db.get_license("PHARM-RST0001")
        self.assertIsNone(row["hardware_id"])

    def test_cli_reset_no_binding(self):
        """Reset on an unbound key reports no binding to reset."""
        db.insert_license("PHARM-RST0002", "reset2@example.com", "ord_002")
        msg = cli_reset("PHARM-RST0002")
        self.assertIn("no hardware binding", msg.lower())

    def test_cli_reset_not_found(self):
        """Reset on non-existent key prints not-found message."""
        msg = cli_reset("PHARM-NONEXISTENT-KEY")
        self.assertIn("not found", msg.lower())

    def test_cli_generate_creates_active_key(self):
        """Generate creates a new active license with NULL hardware_id."""
        msg = cli_generate("support@example.com")
        self.assertIn("Generated license key:", msg)
        # Extract the key from the message
        license_key = msg.split(":")[1].strip().split(" for ")[0]
        self.assertTrue(license_key.startswith("PHARM-"))
        row = db.get_license(license_key)
        self.assertIsNotNone(row, "Generated key should exist in the database")
        self.assertEqual(row["customer_email"], "support@example.com")
        self.assertEqual(row["status"], "active")
        self.assertIsNone(row["hardware_id"])

    def test_cli_generate_unique_keys(self):
        """Each generated key is unique."""
        msg1 = cli_generate("user1@example.com")
        key1 = msg1.split(":")[1].strip().split(" for ")[0]
        msg2 = cli_generate("user2@example.com")
        key2 = msg2.split(":")[1].strip().split(" for ")[0]
        self.assertNotEqual(key1, key2)


class AdminAPIAuthTests(unittest.TestCase):
    """Tests for authentication on POST /api/admin/manage."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_unauthorized_missing_header(self):
        """No X-Admin-Secret header → 401."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_unauthorized_wrong_secret(self):
        """Wrong X-Admin-Secret → 401."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers={"X-Admin-Secret": "wrong-secret"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_unauthorized_empty_secret(self):
        """Empty X-Admin-Secret → 401."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers={"X-Admin-Secret": ""},
        )
        self.assertEqual(resp.status_code, 401)


class AdminAPIListTests(unittest.TestCase):
    """Tests for the 'list' action on POST /api/admin/manage."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_list_authorized_empty(self):
        """Authorized list on empty DB → 200 with empty licenses array."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["licenses"], [])

    def test_list_authorized_with_licenses(self):
        """Authorized list returns all licenses with full fields."""
        db.insert_license("PHARM-API0001", "list1@example.com", "ord_001")
        db.insert_license("PHARM-API0002", "list2@example.com", "ord_002")
        db.bind_hardware_id("PHARM-API0001", "hw-list-001")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["count"], 2)
        licenses = body["licenses"]
        keys = [lic["license_key"] for lic in licenses]
        self.assertIn("PHARM-API0001", keys)
        self.assertIn("PHARM-API0002", keys)
        for lic in licenses:
            self.assertIn("license_key", lic)
            self.assertIn("customer_email", lic)
            self.assertIn("status", lic)
            self.assertIn("hardware_id", lic)
            self.assertIn("created_at", lic)

    def test_list_does_not_require_license_key(self):
        """The 'list' action works without a license_key field."""
        db.insert_license("PHARM-API0003", "list3@example.com", "ord_003")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)


class AdminAPIRevokeTests(unittest.TestCase):
    """Tests for the 'revoke' action on POST /api/admin/manage."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_revoke_success(self):
        """Authorized revoke → 200, key status set to 'revoked'."""
        db.insert_license("PHARM-REV0001", "revoke@example.com", "ord_001")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "revoke", "license_key": "PHARM-REV0001"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["action"], "revoke")
        self.assertEqual(body["license_key"], "PHARM-REV0001")
        row = db.get_license("PHARM-REV0001")
        self.assertEqual(row["status"], "revoked")

    def test_revoke_not_found(self):
        """Revoke non-existent key → 404."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "revoke", "license_key": "PHARM-NONEXISTENT"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"], "License key not found")

    def test_revoke_missing_license_key(self):
        """Revoke without license_key → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "revoke"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_revoke_unauthorized(self):
        """Revoke without admin secret → 401."""
        db.insert_license("PHARM-REV0002", "revoke2@example.com", "ord_002")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "revoke", "license_key": "PHARM-REV0002"},
            headers={"X-Admin-Secret": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)


class AdminAPIResetTests(unittest.TestCase):
    """Tests for the 'reset' action on POST /api/admin/manage."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_reset_success(self):
        """Authorized reset → 200, hardware_id set to NULL in DB."""
        db.insert_license("PHARM-RST0001", "reset@example.com", "ord_001")
        db.bind_hardware_id("PHARM-RST0001", "hw-device-001")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "reset", "license_key": "PHARM-RST0001"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["action"], "reset")
        row = db.get_license("PHARM-RST0001")
        self.assertIsNone(row["hardware_id"])

    def test_reset_not_found(self):
        """Reset non-existent key → 404."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "reset", "license_key": "PHARM-NONEXISTENT"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 404)

    def test_reset_missing_license_key(self):
        """Reset without license_key → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "reset"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_reset_unauthorized(self):
        """Reset without admin secret → 401."""
        db.insert_license("PHARM-RST0002", "reset2@example.com", "ord_002")
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "reset", "license_key": "PHARM-RST0002"},
            headers={"X-Admin-Secret": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)


class AdminAPIEdgeCaseTests(unittest.TestCase):
    """Edge cases: invalid JSON, missing action, invalid action."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_missing_action(self):
        """No action field → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            json={},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_action(self):
        """Unknown action → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "delete"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_json(self):
        """No JSON body → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            data="not json",
            content_type="application/json",
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_list_invalid_json(self):
        """Invalid JSON with valid secret → 400."""
        resp = self.client.post(
            "/api/admin/manage",
            data="not json",
            content_type="application/json",
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)


class AdminAPIEndToEndTests(unittest.TestCase):
    """End-to-end: generate via API list → revoke → verify → reset."""

    def setUp(self):
        self.client = app.test_client()
        db.clear_licenses()

    def test_full_admin_lifecycle(self):
        """Create → list → revoke → reset → list cycle."""
        # Seed a license
        db.insert_license("PHARM-E2E-0001", "e2e@example.com", "ord_e2e")
        db.bind_hardware_id("PHARM-E2E-0001", "hw-e2e-device")

        # List should show it
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "list"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["count"], 1)
        lic = body["licenses"][0]
        self.assertEqual(lic["license_key"], "PHARM-E2E-0001")
        self.assertEqual(lic["hardware_id"], "hw-e2e-device")
        self.assertEqual(lic["status"], "active")

        # Revoke it
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "revoke", "license_key": "PHARM-E2E-0001"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)

        # Verify status changed
        row = db.get_license("PHARM-E2E-0001")
        self.assertEqual(row["status"], "revoked")

        # Reset hardware binding (should still work on revoked key)
        resp = self.client.post(
            "/api/admin/manage",
            json={"action": "reset", "license_key": "PHARM-E2E-0001"},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        row = db.get_license("PHARM-E2E-0001")
        self.assertIsNone(row["hardware_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
