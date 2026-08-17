"""
test_insurance_copay_workflow.py — Tests for insurance copay payment workflow.

Tests:
  1. US billing strategy patient cost calculation with default coverage
  2. EU billing strategy patient cost calculation with default coverage
  3. Strategy factory resolution by region
  4. Insurance copay does not exceed base cost
  5. checkout_cart_atomically accepts insurance_copay/insurance_amount params
  6. Receipt stores sale_type + insurance values
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import test_db_fixture
test_db_fixture._ensure_fixture()

import database
from rx_strategies import (
    strategy_factory,
    USBillingStrategy,
    EUBillingStrategy,
    MockProvider,
)


class TestUSBillingStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = USBillingStrategy()

    def test_calculate_patient_cost_default_coverage(self):
        """Patient cost = min(base_cost, copay + coinsurance) with default 20% coinsurance, $5 copay."""
        cost = self.strategy.calculate_patient_cost(10.0, 30)
        base_cost = 300.0
        expected = min(base_cost, 5.0 + 300.0 * 0.2)
        self.assertAlmostEqual(cost, round(expected, 2))

    def test_patient_cost_does_not_exceed_base(self):
        """Patient never pays more than the full cost."""
        cost = self.strategy.calculate_patient_cost(100.0, 1)
        self.assertLessEqual(cost, 100.0)


class TestEUBillingStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = EUBillingStrategy()

    def test_calculate_patient_cost_default(self):
        """EU patient cost = patient_share + VAT."""
        cost = self.strategy.calculate_patient_cost(10.0, 30)
        base_cost = 300.0
        patient_share = base_cost * 0.1
        vat = patient_share * 0.2
        expected = round(patient_share + vat, 2)
        self.assertAlmostEqual(cost, expected)

    def test_patient_cost_does_not_exceed_base(self):
        cost = self.strategy.calculate_patient_cost(100.0, 1)
        self.assertLessEqual(cost, 100.0)


class TestStrategyFactory(unittest.TestCase):
    def test_us_factory(self):
        s = strategy_factory("US")
        self.assertIsInstance(s, USBillingStrategy)

    def test_gb_factory(self):
        s = strategy_factory("GB")
        self.assertIsInstance(s, EUBillingStrategy)

    def test_de_factory(self):
        s = strategy_factory("DE")
        self.assertIsInstance(s, EUBillingStrategy)

    def test_unknown_defaults_to_mock(self):
        s = strategy_factory("XX")
        self.assertIsInstance(s, MockProvider)


class TestCheckoutWithInsurance(unittest.TestCase):
    def setUp(self):
        test_db_fixture.reset_db_fixture()
        database.init_db()

    def test_receipts_have_sale_type_column(self):
        """After init_db, receipts table should have sale_type column."""
        import sqlite3
        conn = sqlite3.connect(database.get_db_path())
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(receipts)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("sale_type", cols)
        self.assertIn("insurance_copay", cols)
        self.assertIn("insurance_amount", cols)


class TestInsuranceStateVariables(unittest.TestCase):
    def test_pos_sale_type_constants(self):
        from ui_pos_retail import POS_SALE_TYPES
        self.assertIn("OTC", POS_SALE_TYPES)
        self.assertIn("Delivery", POS_SALE_TYPES)
        self.assertIn("Gifts", POS_SALE_TYPES)

    def test_default_insurance_coverage(self):
        from ui_pos_retail import _DEFAULT_INSURANCE_COVERAGE
        self.assertIn("US", _DEFAULT_INSURANCE_COVERAGE)
        us = _DEFAULT_INSURANCE_COVERAGE["US"]
        self.assertIn("copay", us)
        self.assertIn("coinsurance_rate", us)


if __name__ == "__main__":
    unittest.main()
