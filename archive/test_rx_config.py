"""
test_rx_config.py — Test suite for rx_config.py

Tests:
  1. ConfigManager singleton persistence
  2. Unit conversions (lb/kg, in/cm, mg/g, ml/l)
  3. Fernet credential encryption round-trips
"""
import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from rx_config import (
    ConfigManager,
    convert_unit,
    get_labels,
    get_label,
    encrypt_secret,
    decrypt_secret,
)


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False)
        json.dump({"pharmacy_name": "TestPharma", "region": "US"}, self.tmp)
        self.tmp.close()
        # Reset singleton by re-importing
        import importlib
        import rx_config
        importlib.reload(rx_config)
        self.rx_config = rx_config

    def tearDown(self):
        self.rx_config.ConfigManager.__wrapped__ = None
        if hasattr(self.rx_config, "singleton"):
            pass
        os.unlink(self.tmp.name)

    def test_singleton_returns_same_instance(self):
        cm1 = self.rx_config.ConfigManager()
        cm1.set_path(self.tmp.name)
        cm2 = self.rx_config.ConfigManager()
        cm2.set_path(self.tmp.name)
        self.assertIs(cm1, cm2)

    def test_config_loads_from_file(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        config = cm.load()
        self.assertEqual(config["pharmacy_name"], "TestPharma")
        self.assertEqual(config["region"], "US")

    def test_get_returns_value(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        self.assertEqual(cm.get("pharmacy_name"), "TestPharma")
        self.assertEqual(cm.get("nonexistent", "default"), "default")

    def test_set_writes_to_file(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.set("region", "GB")
        with open(self.tmp.name, "r") as f:
            data = json.load(f)
        self.assertEqual(data["region"], "GB")

    def test_lazy_reload_on_mtime_change(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.load()
        with open(self.tmp.name, "w") as f:
            json.dump({"pharmacy_name": "UpdatedPharma"}, f)
        updated = cm.load()
        self.assertEqual(updated["pharmacy_name"], "UpdatedPharma")

    def test_get_region_default_us(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        self.assertEqual(cm.get_region(), "US")

    def test_set_region_persists(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.set_region("EU")
        with open(self.tmp.name, "r") as f:
            data = json.load(f)
        self.assertEqual(data["region"], "EU")

    def test_set_region_updates_unit_system(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.set_region("EU")
        self.assertEqual(cm.get_unit_system(), "metric")
        cm.set_region("US")
        self.assertEqual(cm.get_unit_system(), "imperial")

    def test_is_hipaa_true_for_us(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        self.assertTrue(cm.is_hipaa())
        self.assertFalse(cm.is_gdpr())

    def test_is_gdpr_true_for_eu(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.set_region("EU")
        self.assertTrue(cm.is_gdpr())
        self.assertFalse(cm.is_hipaa())

    def test_credential_round_trip(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        cm.set_credential("test_api_key", "secret-value-123")
        result = cm.get_credential("test_api_key")
        self.assertEqual(result, "secret-value-123")

    def test_get_credential_returns_empty_for_missing(self):
        cm = self.rx_config.ConfigManager()
        cm.set_path(self.tmp.name)
        self.assertEqual(cm.get_credential("nonexistent_key"), "")


class TestUnitConversions(unittest.TestCase):
    def test_kg_to_lb(self):
        self.assertAlmostEqual(convert_unit(1.0, "kg", "lb"), 2.20462262, places=4)

    def test_lb_to_kg(self):
        self.assertAlmostEqual(convert_unit(2.20462262, "lb", "kg"), 1.0, places=4)

    def test_g_to_mg(self):
        self.assertEqual(convert_unit(5.0, "g", "mg"), 5000.0)

    def test_mg_to_g(self):
        self.assertEqual(convert_unit(5000.0, "mg", "g"), 5.0)

    def test_mg_to_mcg(self):
        self.assertEqual(convert_unit(1.0, "mg", "mcg"), 1000.0)

    def test_mcg_to_mg(self):
        self.assertAlmostEqual(convert_unit(1000.0, "mcg", "mg"), 1.0, places=4)

    def test_ml_to_l(self):
        self.assertEqual(convert_unit(1000.0, "ml", "l"), 1.0)

    def test_l_to_ml(self):
        self.assertEqual(convert_unit(1.0, "l", "ml"), 1000.0)

    def test_same_unit_returns_value(self):
        self.assertEqual(convert_unit(42.0, "kg", "kg"), 42.0)

    def test_unknown_conversion_raises(self):
        with self.assertRaises(ValueError):
            convert_unit(1.0, "xyz", "abc")


class TestRegionalLabels(unittest.TestCase):
    def test_us_labels(self):
        labels = get_labels("US")
        self.assertEqual(labels["drug_name"], "Drug Name")
        self.assertEqual(labels["prescriber"], "Prescriber")

    def test_gb_labels(self):
        labels = get_labels("GB")
        self.assertEqual(labels["drug_name"], "Medicinal Product")

    def test_de_labels(self):
        labels = get_labels("DE")
        self.assertEqual(labels["drug_name"], "Medikament")

    def test_unknown_region_falls_back_to_us(self):
        self.assertEqual(get_label("drug_name", "XX"), "Drug Name")

    def test_get_label_key_missing_returns_key(self):
        self.assertEqual(get_label("unknown_key", "US"), "unknown_key")


class TestCredentialEncryption(unittest.TestCase):
    def test_encrypt_decrypt_round_trip(self):
        plaintext = "sk-1234567890abcdef"
        encrypted = encrypt_secret(plaintext)
        self.assertNotEqual(encrypted, plaintext)
        decrypted = decrypt_secret(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_empty_returns_empty(self):
        self.assertEqual(encrypt_secret(""), "")

    def test_decrypt_empty_returns_empty(self):
        self.assertEqual(decrypt_secret(""), "")

    def test_encrypt_produces_different_ciphertext(self):
        """Same plaintext should produce different ciphertext (due to nonce)."""
        encrypted1 = encrypt_secret("test-secret")
        encrypted2 = encrypt_secret("test-secret")
        self.assertNotEqual(encrypted1, encrypted2)

    def test_decrypt_wrong_token_fails(self):
        """Decrypting an invalid token should fail or return garbage."""
        result = decrypt_secret("invalid-token-data")
        if result == "invalid-token-data":
            self.fail("Decryption of invalid token should not return the input unchanged")
        elif result:
            self.assertNotEqual(result, "invalid-token-data")


if __name__ == "__main__":
    unittest.main()
