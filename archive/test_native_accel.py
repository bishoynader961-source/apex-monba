"""
test_native_accel.py — Test suite for native_accel.py hybrid acceleration layer.

Tests:
    1. Fuzzy search (rapidfuzz path + Python fallback path)
    2. Barcode generation (Rust path + Python fallback path)
    3. Header mapping integration with bulk_import_staging
    4. Barcode format consistency between Rust and Python paths
    5. Backend status reporting
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import native_accel
from native_accel import (
    fuzzy_search,
    fuzzy_match_one,
    fuzzy_match_headers,
    generate_batch_barcodes,
    _native_accel_loaded,
    _HAS_RAPIDFUZZ,
    _HAS_RUST_BARCODE,
)


class TestFuzzySearch(unittest.TestCase):
    """Tests for fuzzy_search() with rapidfuzz."""

    def test_exact_match(self):
        results = fuzzy_search("hello", ["hello", "world"], cutoff=50)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0][0], "hello")
        self.assertAlmostEqual(results[0][1], 100.0, places=1)

    def test_typo_tolerant(self):
        choices = ["Amoxicillin 500mg", "Aspirin 81mg", "Lisinopril 10mg"]
        results = fuzzy_search("amoxicilln", choices, cutoff=50)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0][0], "Amoxicillin 500mg")

    def test_case_insensitive(self):
        results = fuzzy_search("AMOX", ["amoxicillin", "aspirin"], cutoff=50)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0][0], "amoxicillin")

    def test_cutoff_filtering(self):
        results = fuzzy_search("xyz", ["hello", "world"], cutoff=90)
        self.assertEqual(len(results), 0)

    def test_limit_respected(self):
        choices = ["match"] * 20
        results = fuzzy_search("match", choices, limit=5, cutoff=50)
        self.assertEqual(len(results), 5)

    def test_empty_query(self):
        self.assertEqual(fuzzy_search("", ["a", "b"]), [])

    def test_empty_choices(self):
        self.assertEqual(fuzzy_search("test", []), [])

    def test_score_range(self):
        results = fuzzy_search("hello", ["hello world"], cutoff=0)
        self.assertTrue(len(results) >= 1)
        score = results[0][1]
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


class TestFuzzySearchFallback(unittest.TestCase):
    """Tests for difflib fallback when rapidfuzz is not available."""

    def test_fallback_fuzzy_search(self):
        with patch.object(native_accel, "_HAS_RAPIDFUZZ", False):
            results = native_accel.fuzzy_search("amoxicilln", ["Amoxicillin 500mg", "Aspirin"], cutoff=50)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0][0], "Amoxicillin 500mg")

    def test_fallback_score_format(self):
        with patch.object(native_accel, "_HAS_RAPIDFUZZ", False):
            results = native_accel.fuzzy_search("hello", ["hello world"], cutoff=0)
        self.assertTrue(len(results) >= 1)
        score = results[0][1]
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


class TestFuzzyMatchOne(unittest.TestCase):

    def test_best_match_found(self):
        result = fuzzy_match_one("amox", ["amoxicillin", "aspirin", "lisinopril"])
        self.assertIsNotNone(result)
        match_str, score, idx = result
        self.assertEqual(match_str, "amoxicillin")
        self.assertEqual(idx, 0)

    def test_no_match(self):
        result = fuzzy_match_one("xyz123", ["amoxicillin", "aspirin"], cutoff=90)
        self.assertIsNone(result)


class TestFuzzyMatchHeaders(unittest.TestCase):

    def _known_fields(self):
        return {
            "name": {"name", "product_name", "drug_name", "product", "item_name"},
            "price": {"price", "unit_price", "cost", "retail_price"},
            "manufacturer_barcode": {"manufacturer_barcode", "mfg_barcode", "upc", "barcode"},
            "internal_unique_barcode": {"internal_unique_barcode", "internal_barcode", "sku", "item_number"},
            "vendor_name": {"vendor_name", "vendor", "supplier"},
            "expiry_date": {"expiry_date", "expiration_date", "exp_date"},
        }

    def test_exact_match_headers(self):
        known = self._known_fields()
        headers = ["Product Name", "Unit Price", "Mfg Barcode", "Internal Barcode", "Expiry Date", "SKU"]
        result = fuzzy_match_headers(headers, known)
        self.assertEqual(result["Product Name"], "name")
        self.assertEqual(result["Unit Price"], "price")
        self.assertEqual(result["Mfg Barcode"], "manufacturer_barcode")
        self.assertEqual(result["Internal Barcode"], "internal_unique_barcode")
        self.assertEqual(result["Expiry Date"], "expiry_date")
        self.assertEqual(result["SKU"], "internal_unique_barcode")

    def test_fuzzy_typo_headers(self):
        known = self._known_fields()
        headers = ["Prod Name", "Cost", "Barcode", "Exp Date", "Vendor"]
        result = fuzzy_match_headers(headers, known)
        self.assertEqual(result["Prod Name"], "name")
        self.assertEqual(result["Cost"], "price")
        self.assertEqual(result["Barcode"], "manufacturer_barcode")
        self.assertEqual(result["Exp Date"], "expiry_date")
        self.assertEqual(result["Vendor"], "vendor_name")

    def test_empty_inputs(self):
        self.assertEqual(fuzzy_match_headers([], self._known_fields()), {})
        self.assertEqual(fuzzy_match_headers(["test"], {}), {})

    def test_unmatched_header_excluded(self):
        known = self._known_fields()
        result = fuzzy_match_headers(["Unmatched Column"], known)
        self.assertNotIn("Unmatched Column", result)


class TestBarcodeGeneration(unittest.TestCase):
    """Tests for generate_batch_barcodes() — covers both Rust and Python paths."""

    def test_batch_format(self):
        barcodes = generate_batch_barcodes("MedSupply", 10)
        self.assertEqual(len(barcodes), 10)
        for bc in barcodes:
            self.assertTrue(bc.startswith("MED-"))
            # Format: PREFIX-XXXXXX where X is hex
            parts = bc.split("-")
            self.assertEqual(len(parts), 2)
            self.assertEqual(len(parts[1]), 6)
            int(parts[1], 16)  # Must be valid hex

    def test_batch_uniqueness(self):
        barcodes = generate_batch_barcodes("MedSupply", 500)
        self.assertEqual(len(barcodes), 500)
        self.assertEqual(len(set(barcodes)), 500)

    def test_zero_count(self):
        self.assertEqual(generate_batch_barcodes("MedSupply", 0), [])

    def test_negative_count(self):
        self.assertEqual(generate_batch_barcodes("MedSupply", -5), [])

    def test_na_vendor_prefix(self):
        barcodes = generate_batch_barcodes("N/A", 5)
        for bc in barcodes:
            self.assertTrue(bc.startswith("PRD-"))

    def test_empty_vendor_prefix(self):
        barcodes = generate_batch_barcodes("", 5)
        for bc in barcodes:
            self.assertTrue(bc.startswith("PRD-"))

    def test_none_like_vendor(self):
        barcodes = generate_batch_barcodes("   ", 5)
        for bc in barcodes:
            self.assertTrue(bc.startswith("PRD-"))

    def test_short_vendor(self):
        barcodes = generate_batch_barcodes("AB", 3)
        for bc in barcodes:
            self.assertTrue(bc.startswith("AB-"))

    def test_long_vendor_truncated(self):
        barcodes = generate_batch_barcodes("VeryLongVendorName", 3)
        for bc in barcodes:
            self.assertTrue(bc.startswith("VER-"))

    def test_consistency_with_barcode_logic(self):
        """Rust and Python paths must produce the same format."""
        from barcode_logic import generate_internal_barcode
        py_bc = generate_internal_barcode("MedSupply")
        # Check format matches
        parts = py_bc.split("-")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "MED")
        self.assertEqual(len(parts[1]), 6)


class TestBarcodeFallback(unittest.TestCase):
    """Test Python fallback when Rust extension is unavailable."""

    def test_fallback_generation(self):
        with patch.object(native_accel, "_HAS_RUST_BARCODE", False):
            with patch.object(native_accel, "_rg", None):
                barcodes = generate_batch_barcodes("MedSupply", 5)
        self.assertEqual(len(barcodes), 5)
        for bc in barcodes:
            self.assertTrue(bc.startswith("MED-"))
        self.assertEqual(len(set(barcodes)), 5)

    def test_fallback_na_vendor(self):
        with patch.object(native_accel, "_HAS_RUST_BARCODE", False):
            with patch.object(native_accel, "_rg", None):
                barcodes = generate_batch_barcodes("N/A", 3)
        for bc in barcodes:
            self.assertTrue(bc.startswith("PRD-"))


class TestStatusBarcode(unittest.TestCase):

    def test_status_dict(self):
        status = _native_accel_loaded()
        self.assertIn("rapidfuzz", status)
        self.assertIn("barcode_gen", status)
        self.assertIn("python_fallback", status)
        self.assertIsInstance(status["rapidfuzz"], bool)
        self.assertIsInstance(status["barcode_gen"], bool)
        self.assertIsInstance(status["python_fallback"], bool)

    def test_status_consistency(self):
        status = _native_accel_loaded()
        self.assertEqual(status["rapidfuzz"], _HAS_RAPIDFUZZ)
        self.assertEqual(status["barcode_gen"], _HAS_RUST_BARCODE)


class TestIntegrationHeaderMapping(unittest.TestCase):
    """Integration test: fuzzy_match_headers used by bulk_import_staging."""

    def test_staging_table_integration(self):
        from bulk_import_staging import StagingTable
        headers = ["Drug Name", "Cost", "Mfg Barcode", "Internal Barcode", "Exp Date", "Vendor"]
        table = StagingTable(columns=headers)
        mapping = table.auto_map_csv_headers()
        self.assertEqual(mapping["Drug Name"], "name")
        self.assertEqual(mapping["Cost"], "price")
        self.assertEqual(mapping["Mfg Barcode"], "manufacturer_barcode")
        self.assertEqual(mapping["Internal Barcode"], "internal_unique_barcode")
        self.assertEqual(mapping["Exp Date"], "expiry_date")
        self.assertEqual(mapping["Vendor"], "vendor_name")


if __name__ == "__main__":
    unittest.main(verbosity=2)
