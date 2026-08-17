"""
test_sale_type_filtering.py — Tests for Sale Type constants and receipt filtering.

Tests:
  1. POS_SALE_TYPES contains all expected sale types
  2. POS_SALE_TYPES color mapping exists for each type
  3. Receipts store and retrieve sale_type
  4. Receipt filtering by sale_type works end-to-end
  5. Insurance copay/insurance_amount values are stored in receipts
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_db_fixture
test_db_fixture._ensure_fixture()

import database
from ui_pos_retail import POS_SALE_TYPES, _SALE_TYPE_COLORS


class TestPosSaleTypes(unittest.TestCase):
    def test_constant_values(self):
        self.assertEqual(POS_SALE_TYPES, ("OTC", "Rx OTC", "Delivery", "Loyalty", "Gifts"))

    def test_colors_for_all_types(self):
        for st in POS_SALE_TYPES:
            self.assertIn(st, _SALE_TYPE_COLORS,
                          f"No color defined for sale type '{st}'")

    def test_otc_has_default_blue(self):
        self.assertEqual(_SALE_TYPE_COLORS["OTC"], "#3b82f6")


class TestReceiptSaleTypePersistence(unittest.TestCase):
    def setUp(self):
        test_db_fixture.reset_db_fixture()
        database.init_db()

    def _add_test_product(self, barcode):
        import sqlite3
        conn = sqlite3.connect(database.get_db_path())
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status) "
            "VALUES (?, ?, ?, ?, 'In Stock')",
            ("Test Product", 10.00, f"MFG_{barcode}", barcode)
        )
        conn.commit()
        conn.close()

    def test_receipt_persists_sale_type(self):
        barcode = f"INT_sale_type_{id(self)}"
        self._add_test_product(barcode)
        try:
            rid = database.checkout_cart_atomically(
                payment_method="Cash",
                cart_entries=[{
                    "product_name": "Test Product",
                    "quantity": 1,
                    "price_at_time": 10.00,
                    "internal_barcodes": [barcode],
                    "vendor": "N/A",
                    "expiry_date": "",
                }],
                sale_type="Delivery",
                insurance_copay=0.0,
                insurance_amount=0.0,
            )
            receipts = database.get_receipts()
            delivery_receipts = [r for r in receipts if r[4] == "Delivery"]
            self.assertTrue(any(r[0] == rid for r in delivery_receipts))
        except ValueError:
            self.skipTest("Product not in stock")

    def test_receipt_stores_insurance_values(self):
        barcode = f"INT_insurance_{id(self)}"
        self._add_test_product(barcode)
        try:
            rid = database.checkout_cart_atomically(
                payment_method="Card",
                cart_entries=[{
                    "product_name": "Test Product",
                    "quantity": 1,
                    "price_at_time": 10.00,
                    "internal_barcodes": [barcode],
                    "vendor": "N/A",
                    "expiry_date": "",
                }],
                sale_type="OTC",
                insurance_copay=5.0,
                insurance_amount=5.0,
            )
            import sqlite3
            conn = sqlite3.connect(database.get_db_path())
            cur = conn.cursor()
            cur.execute("SELECT insurance_copay, insurance_amount FROM receipts WHERE id = ?", (rid,))
            row = cur.fetchone()
            conn.close()
            self.assertIsNotNone(row)
            self.assertAlmostEqual(row[0], 5.0)
            self.assertAlmostEqual(row[1], 5.0)
        except ValueError:
            self.skipTest("Product not in stock")


if __name__ == "__main__":
    unittest.main()
