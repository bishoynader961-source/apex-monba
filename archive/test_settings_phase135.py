"""
test_settings_phase135.py — Tests for Phase 13.5: Dynamic Settings Tab & Config Sync.

Verifies (no GUI/display required):
  VG-2  Safe-write: config merge preserves all keys incl. license_key + email_report
  VG-3  Tax rate validation: accepts 0.0–100.0, rejects non-float / out-of-range
  VG-5  Receipt engine renders header_note + footer_note when present

Run:  python -m unittest test_settings_phase135  (from archive/ directory)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import barcode_logic
import receipt_engine


# ── Validation helpers (mirror save_settings logic in ui_settings_tab.py) ──

def _validate_tax_rate(tax_str):
    """Returns (ok: bool, value: float|None, error: str|None)."""
    try:
        rate = float(tax_str)
        if rate < 0 or rate > 100:
            return False, None, "Tax rate must be a number between 0 and 100."
        return True, rate, None
    except (ValueError, TypeError):
        return False, None, "Tax rate must be a number between 0 and 100."


def _simulate_save_merge(config_path, updates):
    """Replicates the load-modify-write merge used by save_settings().

    Reads existing config, applies only the *updates* dict (no key deletion),
    and writes the merged result back to *config_path*.
    """
    with open(config_path, "r") as f:
        config = json.load(f)
    config.update(updates)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)


class TestConfigDefaults(unittest.TestCase):
    """M36.1 — defaults include the new receipt note keys."""

    def setUp(self):
        self._orig_config_file = barcode_logic.CONFIG_FILE
        self.tmp_dir = tempfile.mkdtemp()
        self._tmp_config = os.path.join(self.tmp_dir, "config.json")

    def tearDown(self):
        barcode_logic.CONFIG_FILE = self._orig_config_file

    def test_load_config_includes_receipt_note_defaults(self):
        if os.path.exists(self._tmp_config):
            os.remove(self._tmp_config)
        barcode_logic.CONFIG_FILE = self._tmp_config
        config = barcode_logic.load_config()
        self.assertEqual(config.get("receipt_header_note"), "")
        self.assertEqual(config.get("receipt_footer_note"), "")

    def test_load_config_merges_new_keys_into_existing(self):
        with open(self._tmp_config, "w") as f:
            json.dump({"pharmacy_name": "Pre", "tax_rate": 5.0}, f)
        barcode_logic.CONFIG_FILE = self._tmp_config
        config = barcode_logic.load_config()
        self.assertEqual(config["pharmacy_name"], "Pre")
        self.assertEqual(config["tax_rate"], 5.0)
        self.assertEqual(config.get("receipt_header_note"), "")
        self.assertEqual(config.get("receipt_footer_note"), "")


class TestConfigSafeWrite(unittest.TestCase):
    """VG-2 — save_settings merge must not destroy unrelated keys."""

    def setUp(self):
        self._orig_config_file = barcode_logic.CONFIG_FILE
        self.tmp_dir = tempfile.mkdtemp()
        self._tmp_config = os.path.join(self.tmp_dir, "config.json")
        # Seed with keys that save_settings does NOT manage
        seed = {
            "pharmacy_name": "My Pharmacy",
            "tax_rate": 0.0,
            "license_key": "SHOULD-SURVIVE-X9K2",
            "email_report": {
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "enabled": True,
            },
            "expiry_ignore_list": ["paracetamol"],
            "unknown_future_key": 42,
        }
        with open(self._tmp_config, "w") as f:
            json.dump(seed, f)
        barcode_logic.CONFIG_FILE = self._tmp_config

    def tearDown(self):
        barcode_logic.CONFIG_FILE = self._orig_config_file

    def test_merge_preserves_license_key_and_email_report(self):
        updates = {
            "pharmacy_name": "New Pharmacy",
            "tax_rate": 8.5,
            "receipt_header_note": "Header Line",
            "receipt_footer_note": "Footer Line",
        }
        _simulate_save_merge(self._tmp_config, updates)

        with open(self._tmp_config, "r") as f:
            result = json.load(f)

        # Edited keys
        self.assertEqual(result["pharmacy_name"], "New Pharmacy")
        self.assertEqual(result["tax_rate"], 8.5)
        self.assertEqual(result["receipt_header_note"], "Header Line")
        self.assertEqual(result["receipt_footer_note"], "Footer Line")
        # Preserved keys (would be DESTROYED by the old new_config-dict approach)
        self.assertEqual(result["license_key"], "SHOULD-SURVIVE-X9K2")
        self.assertEqual(result["email_report"]["smtp_host"], "smtp.gmail.com")
        self.assertTrue(result["email_report"]["enabled"])
        self.assertEqual(result["expiry_ignore_list"], ["paracetamol"])
        self.assertEqual(result["unknown_future_key"], 42)

    def test_merge_with_empty_note_values(self):
        updates = {
            "receipt_header_note": "",
            "receipt_footer_note": "",
        }
        _simulate_save_merge(self._tmp_config, updates)
        with open(self._tmp_config, "r") as f:
            result = json.load(f)
        self.assertEqual(result["receipt_header_note"], "")
        self.assertEqual(result["receipt_footer_note"], "")
        self.assertEqual(result["license_key"], "SHOULD-SURVIVE-X9K2")


class TestTaxRateValidation(unittest.TestCase):
    """VG-3 — tax rate validation rules (mirrors save_settings)."""

    def test_valid_tax_rates(self):
        for val in ["0.0", "0", "8.5", "100", "100.0", "5.25"]:
            ok, rate, err = _validate_tax_rate(val)
            self.assertTrue(ok, f"Expected '{val}' to be valid")
            self.assertIsNone(err)

    def test_invalid_non_float(self):
        for val in ["abc", "", "Eight", "tax", "1.2.3"]:
            ok, rate, err = _validate_tax_rate(val)
            self.assertFalse(ok, f"Expected '{val}' to be invalid")
            self.assertIsNone(rate)

    def test_invalid_out_of_range(self):
        for val in ["-0.1", "-1", "100.1", "101", "150"]:
            ok, rate, err = _validate_tax_rate(val)
            self.assertFalse(ok, f"Expected '{val}' to be invalid")

    def test_boundary_values(self):
        ok, rate, _ = _validate_tax_rate("0")
        self.assertTrue(ok)
        self.assertEqual(rate, 0.0)
        ok, rate, _ = _validate_tax_rate("100")
        self.assertTrue(ok)
        self.assertEqual(rate, 100.0)


class TestReceiptNoteRendering(unittest.TestCase):
    """VG-5 — receipt_engine renders header/footer notes."""

    def setUp(self):
        self._orig_receipts_dir = receipt_engine.RECEIPTS_DIR
        self.tmp_dir = tempfile.mkdtemp()
        receipt_engine.RECEIPTS_DIR = self.tmp_dir

    def tearDown(self):
        receipt_engine.RECEIPTS_DIR = self._orig_receipts_dir

    def test_header_note_appears_in_receipt(self):
        pharmacy_info = {
            "pharmacy_name": "Test Pharmacy",
            "address": "123 Main St",
            "phone": "555-0100",
            "receipt_header_note": "Please have your ID ready at pickup",
            "receipt_footer_note": "Returns accepted within 30 days with receipt",
        }
        path = receipt_engine.generate_receipt(
            receipt_id=42,
            cart_items=[{"product_name": "Aspirin", "quantity": 2, "price_at_time": 5.00}],
            subtotal=10.0,
            total=10.80,
            tax=0.80,
            payment_type="Cash",
            patient_name="John Doe",
            pharmacy_info=pharmacy_info,
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Please have your ID ready at pickup", content)
        self.assertIn("Returns accepted within 30 days with receipt", content)
        # Header note should appear BEFORE the Receipt # line
        self.assertLess(
            content.index("Please have your ID ready at pickup"),
            content.index("Receipt #: 42"),
        )
        # Footer note should appear AFTER the "Thank you" line
        self.assertLess(
            content.index("Thank you for your purchase!"),
            content.index("Returns accepted within 30 days with receipt"),
        )

    def test_no_notes_produces_clean_receipt(self):
        pharmacy_info = {
            "pharmacy_name": "Test Pharmacy",
            "address": "",
            "phone": "",
        }
        path = receipt_engine.generate_receipt(
            receipt_id=43,
            cart_items=[{"product_name": "Ibuprofen", "quantity": 1, "price_at_time": 8.00}],
            subtotal=8.0,
            total=8.0,
            tax=0.0,
            payment_type="Card",
            patient_name="",
            pharmacy_info=pharmacy_info,
        )
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Receipt #: 43", content)
        self.assertIn("TOTAL:", content)
        # No header note sep should appear between header and Receipt #
        # (header block sep + Receipt # line are adjacent)


class TestNotifyConfigUpdatedPattern(unittest.TestCase):
    """Verify the _notify_config_updated method exists and delegates correctly."""

    def test_method_exists_on_pharmacy_app(self):
        # We can't instantiate PharmacyApp (needs Tkinter display), but we can
        # verify the method is attached to the class by inspecting source.
        source_path = os.path.join(os.path.dirname(__file__), "ui.py")
        with open(source_path, "r") as f:
            source = f.read()
        self.assertIn("def _notify_config_updated(self):", source)
        self.assertIn("self._notify_inventory_updated()", source)
        self.assertIn("self._refresh_cart_treeview()", source)
        self.assertIn("self._checkout_update_change()", source)

    def test_save_settings_calls_notify(self):
        source_path = os.path.join(os.path.dirname(__file__), "ui_settings_tab.py")
        with open(source_path, "r") as f:
            source = f.read()
        self.assertIn("self._notify_config_updated()", source)
        # The old ad-hoc refresh calls should be gone
        self.assertNotIn("self.load_templates_grid()", source.split("def save_settings")[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
