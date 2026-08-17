"""
test_rx_strategies.py — Test suite for rx_strategies.py

Tests:
  1. Strategy factory resolution
  2. US strategy behavior (patient cost, claim, validation, auth)
  3. EU strategy behavior (patient cost, claim, validation, auth)
  4. Mock provider behavior
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from rx_strategies import (
    strategy_factory,
    PharmacyIntegrationStrategy,
    USBillingStrategy,
    EUBillingStrategy,
    MockProvider,
)


class TestStrategyFactory(unittest.TestCase):
    def test_factory_us(self):
        s = strategy_factory("US")
        self.assertIsInstance(s, USBillingStrategy)
        self.assertEqual(s.region, "US")

    def test_factory_gb(self):
        s = strategy_factory("GB")
        self.assertIsInstance(s, EUBillingStrategy)
        self.assertEqual(s.region, "GB")

    def test_factory_de(self):
        s = strategy_factory("DE")
        self.assertIsInstance(s, EUBillingStrategy)

    def test_factory_unknown_defaults_to_mock(self):
        s = strategy_factory("XX")
        self.assertIsInstance(s, MockProvider)
        self.assertEqual(s.region, "MOCK")

    def test_factory_default_is_us(self):
        s = strategy_factory()
        self.assertIsInstance(s, USBillingStrategy)


class TestUSBillingStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = USBillingStrategy()

    def test_calculate_patient_cost_default_coverage(self):
        cost = self.strategy.calculate_patient_cost(10.0, 30)
        self.assertGreater(cost, 0)

    def test_calculate_patient_cost_custom_coverage(self):
        coverage = {"coinsurance_rate": 0.1, "copay": 2.0}
        cost = self.strategy.calculate_patient_cost(10.0, 30, insurance_coverage=coverage)
        expected = min(300.0, 2.0 + 300.0 * 0.1)
        self.assertAlmostEqual(cost, round(expected, 2))

    def test_generate_claim(self):
        claim_data = {
            "prescriber_npi": "1234567890",
            "ndc": "00012345678",
            "quantity": 30,
            "days_supply": 30,
            "insurance_id": "INS123",
            "pharmacy_npi": "9876543210",
        }
        result = self.strategy.generate_claim(claim_data)
        self.assertEqual(result["region"], "US")
        self.assertEqual(result["npi"], "1234567890")
        self.assertEqual(result["ndc"], "00012345678")
        self.assertEqual(result["quantity"], 30)
        self.assertEqual(result["days_supply"], 30)

    def test_validate_prescription_valid(self):
        data = {"drug_name": "Aspirin", "dosage": "500mg", "quantity": 30, "prescriber_npi": "123"}
        self.assertTrue(self.strategy.validate_prescription(data))

    def test_validate_prescription_missing_fields(self):
        data = {"drug_name": "Aspirin"}
        with self.assertRaises(ValueError):
            self.strategy.validate_prescription(data)

    def test_authenticate_success(self):
        success, msg = self.strategy.authenticate({
            "api_key": "sk-test-123",
            "switch_id": "SWITCH456",
        })
        self.assertTrue(success)
        self.assertIn("passed", msg)

    def test_authenticate_missing_api_key(self):
        success, msg = self.strategy.authenticate({"switch_id": "SWITCH456"})
        self.assertFalse(success)
        self.assertIn("API Key", msg)

    def test_authenticate_missing_switch_id(self):
        success, msg = self.strategy.authenticate({"api_key": "sk-test-123"})
        self.assertFalse(success)
        self.assertIn("Switch ID", msg)


class TestEUBillingStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = EUBillingStrategy()

    def test_calculate_patient_cost_default(self):
        cost = self.strategy.calculate_patient_cost(10.0, 30)
        self.assertGreater(cost, 0)

    def test_generate_claim(self):
        claim_data = {
            "amts_code": "AMTS001",
            "bnf_code": "BNF123",
            "quantity": 30,
            "days_supply": 30,
            "nhs_number": "9876543210",
            "prescriber_ods": "ODS123",
        }
        result = self.strategy.generate_claim(claim_data)
        self.assertEqual(result["region"], "EU")
        self.assertEqual(result["amts_code"], "AMTS001")
        self.assertEqual(result[" NHS_number"], "9876543210")

    def test_validate_prescription_valid(self):
        data = {"drug_name": "Paracetamol", "dosage": "500mg", "quantity": 30, "prescriber_ods": "ODS123"}
        self.assertTrue(self.strategy.validate_prescription(data))

    def test_validate_prescription_missing_fields(self):
        data = {"drug_name": "Paracetamol"}
        with self.assertRaises(ValueError):
            self.strategy.validate_prescription(data)

    def test_authenticate_success(self):
        tmp_cert = os.path.join(os.path.dirname(__file__), "test_cert.pem")
        with open(tmp_cert, "w") as f:
            f.write("test-cert-content")
        try:
            success, msg = self.strategy.authenticate({
                "fmd_api_key": "key-123",
                "cert_path": tmp_cert,
            })
            self.assertTrue(success)
        finally:
            if os.path.exists(tmp_cert):
                os.unlink(tmp_cert)

    def test_authenticate_missing_api_key(self):
        success, msg = self.strategy.authenticate({"cert_path": "/nonexistent"})
        self.assertFalse(success)
        self.assertIn("API Key", msg)

    def test_authenticate_nonexistent_cert(self):
        success, msg = self.strategy.authenticate({
            "fmd_api_key": "key-123",
            "cert_path": "/nonexistent/cert.pem",
        })
        self.assertFalse(success)
        self.assertIn("Certificate", msg)


class TestMockProvider(unittest.TestCase):
    def setUp(self):
        self.strategy = MockProvider()

    def test_calculate_patient_cost(self):
        cost = self.strategy.calculate_patient_cost(5.5, 20)
        self.assertEqual(cost, 110.0)

    def test_generate_claim(self):
        result = self.strategy.generate_claim({"drug_name": "Test", "quantity": 10})
        self.assertEqual(result["region"], "MOCK")
        self.assertEqual(result["drug_name"], "Test")

    def test_validate_prescription_always_passes(self):
        self.assertTrue(self.strategy.validate_prescription({}))
        self.assertTrue(self.strategy.validate_prescription({"anything": "go"}))

    def test_authenticate_always_passes(self):
        success, msg = self.strategy.authenticate({})
        self.assertTrue(success)
        self.assertIn("accepted", msg)


class TestAbstractBase(unittest.TestCase):
    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            PharmacyIntegrationStrategy()


if __name__ == "__main__":
    unittest.main()
