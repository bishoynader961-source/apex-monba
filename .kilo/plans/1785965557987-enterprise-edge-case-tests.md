# Implementation Plan — Enterprise Edge Case Tests

> **Status:** Planning — Implementation-Ready
> **Scope:** New test file `archive/test_enterprise_edge_cases.py` only. No source modifications.
> **Current date:** 2026-08-06 (per system clock)
> **Target Python:** 3.12+
> **Plan file:** `.kilo/plans/1785965557987-enterprise-edge-case-tests.md`

---

## 1. Context & Verified Facts

### Files under test (READ-ONLY — no modifications)
| File | Key symbols | Verified behavior |
|---|---|---|
| `archive/bulk_import_staging.py` | `StagingTable`, `import_excel`, `commit_staged_products`, `import_csv` | `import_excel(path, sheet=None)` reads XLSX via `openpyxl` read-only mode. `commit_staged_products` does `import database` lazily inside the function, iterates `table.to_product_dicts()`, calls `database.get_product_by_internal_barcode()` then `add_product()` or `update_product_full()`. Returns `{"added", "updated", "errors"}`. |
| `archive/ndc_dictionary.py` | `_normalize_dea`, `barcode_lookup`, `name_lookup`, `bulk_load_ndc`, `init_ndc_dictionary`, `_get_conn` | `:memory:` → shared in-memory URI `file:ndc_dict?mode=memory&cache=shared`. `bulk_load_ndc` catches all exceptions, rolls back, returns 0. Missing file → returns 0. `_normalize_dea` computes a stripped key but returns `raw.strip().upper()` (original) as default when key not in `_DEA_SCHEDULES`. |
| `archive/database.py` | `add_product(name, price, manufacturer_barcode, internal_unique_barcode, ...)`, `update_product_full(product_id, name, price, ...)`, `get_product_by_internal_barcode` | `get_product_by_internal_barcode` returns a tuple `(id, ...)` or `None`. `add_product` uses kwarg `internal_unique_barcode`; `update_product_full` uses kwarg `internal_barcode`. Both decorated with `@_db_fallback`. |

### Existing test conventions (from `test_phase16.py`)
- `ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))` + `sys.path.insert(0, ARCHIVE_DIR)`
- NDC tests reset module globals (`_initialized`, `_DB_PATH`, `_shared_handle`) in setUp/tearDown
- Temp files via `tempfile.NamedTemporaryFile(suffix=..., delete=False)` + manual `os.unlink` in tearDown
- `unittest.TestCase` with method-level `setUp`/`tearDown`

### Verified runtime behavior (confirmed via shell)
- `openpyxl` 3.1.5 available; `import_excel` creates `StagingTable` with correct rows/columns
- `StagedTable` headers `"Name", "Price", "Manufacturer Barcode", "Internal Unique Barcode", "DEA Schedule"` map correctly via `auto_map_csv_headers()` (Step-1 exact match in rapidfuzz path) → `{"Name": "name", "Price": "price", ...}`
- `to_product_dicts()` converts `price` to `float`
- `_normalize_dea("SCHEDULE II")` → `"SCHEDULE II"` (key "II" not in dict; default = raw uppercased)
- `_normalize_dea("CIIS")` → `"CII"`, `_normalize_dea("cIV")` → `"CIV"`, `_normalize_dea("schedule ii")` → `"SCHEDULE II"`
- `bulk_load_ndc` returns 0 for: missing file, malformed CSV (bad `float()`), empty CSV (headers only)

---

## 2. Verifiable Goals (Success Metrics)

| # | Metric | Verification |
|---|---|---|
| G1 | `import_excel()` loads a temp .xlsx and populates `StagingTable` correctly | `table.row_count == 2`, columns match headers, row values accessible by header name |
| G2 | `commit_staged_products()` calls `database.add_product` with correct parsed data for new products | Mock assertions on `add_product.call_args_list` — `name`, `price` (float), `manufacturer_barcode`, `internal_unique_barcode` |
| G3 | `commit_staged_products()` calls `database.update_product_full` with correct `product_id` for existing products | Mock returns `(42,)` for `get_product_by_internal_barcode`; assert `update_product_full` called with `product_id=42` |
| G4 | `commit_staged_products()` skips rows without `internal_unique_barcode` | `result["errors"] == 1`, `add_product.call_count` reflects only valid rows |
| G5 | `barcode_lookup(nonexistent)` returns `None` | `assertIsNone` for unknown barcode, empty string, and `None` input |
| G6 | `name_lookup("partial")` returns filtered results | Seeded data with "Amoxicillin" → `name_lookup("Amoxicillin")` returns 2 dicts |
| G7 | `_normalize_dea()` handles edge cases per actual code behavior | "SCHEDULE II"→"SCHEDULE II", "CIIS"→"CII", "cIV"→"CIV", "schedule ii"→"SCHEDULE II", etc. |
| G8 | `bulk_load_ndc()` gracefully handles missing file | Returns 0, no exception raised |
| G9 | `bulk_load_ndc()` gracefully handles malformed CSV | Returns 0, no exception raised (catches ValueError from bad `float()`) |
| G10 | All NDC tests use isolated in-memory SQLite | `:memory:` + proper `_shared_handle` teardown in setUp/tearDown |
| G11 | Test suite passes via `python -m pytest` or `python -m unittest` | Exit code 0, all tests green |
| G12 | No regression — existing `test_phase16.py` still passes | Run both test files together |

---

## 3. Step-by-Step Implementation

### Step 3.1 — Create `archive/test_enterprise_edge_cases.py`

Write the complete file below. Key design decisions:

1. **`TestImportExcel`**: Uses `tempfile.NamedTemporaryFile(suffix=".xlsx")` for cleanup. Creates `openpyxl.Workbook()`, appends header + data rows, saves, closes, then calls `import_excel()`.

2. **`TestCommitStagedProducts`**: Patches `database.add_product`, `database.update_product_full`, and `database.get_product_by_internal_barcode` via `unittest.mock.patch`. Helper `_build_staged_table()` sets columns with clear headers, calls `auto_map_csv_headers()`, adds rows. Verifies mock call args using `.kwargs`.

3. **`TestNDCDictionary`**: Uses `:memory:` in-memory SQLite (per constraint). Resets `ndc_dictionary` module globals in setUp/tearDown (close `_shared_handle`, reset `_initialized`/`_DB_PATH`/`_shared_handle`). Helper `_seed_data()` writes a temp CSV for `bulk_load_ndc`.

```python
"""
test_enterprise_edge_cases.py — Edge-case tests for enterprise modules.

Tests:
  - bulk_import_staging: import_excel(), commit_staged_products()
  - ndc_dictionary: barcode_lookup(), name_lookup(), _normalize_dea(), bulk_load_ndc() error handling
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
if ARCHIVE_DIR not in sys.path:
    sys.path.insert(0, ARCHIVE_DIR)


class TestImportExcel(unittest.TestCase):
    """Test import_excel() with a mock .xlsx file created via openpyxl."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        self._tmp.close()

    def tearDown(self):
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_import_excel_populates_staging_table(self):
        """import_excel() loads headers and data rows into a StagingTable."""
        import openpyxl
        from bulk_import_staging import import_excel, StagingTable

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Products"
        headers = [
            "Name", "Price", "Manufacturer Barcode",
            "Internal Unique Barcode", "DEA Schedule",
        ]
        ws.append(headers)
        ws.append(["Aspirin 500mg", 5.99, "012345678901", "MED-A3F9B2", "OTC"])
        ws.append(["Ibuprofen 200mg", 6.50, "012345678902", "MED-C7D2E1", "OTC"])
        wb.save(self._tmp.name)
        wb.close()

        table = import_excel(self._tmp.name)

        self.assertIsInstance(table, StagingTable)
        self.assertEqual(table.row_count, 2)
        self.assertEqual(table.source_name, os.path.basename(self._tmp.name))
        self.assertEqual(len(table.columns), 5)

        rows = table.rows
        self.assertEqual(rows[0]["Name"], "Aspirin 500mg")
        self.assertEqual(rows[0]["Price"], "5.99")
        self.assertEqual(rows[0]["Internal Unique Barcode"], "MED-A3F9B2")
        self.assertEqual(rows[1]["Name"], "Ibuprofen 200mg")
        self.assertEqual(rows[1]["Internal Unique Barcode"], "MED-C7D2E1")

    def test_import_excel_custom_sheet(self):
        """import_excel(sheet='...') loads the correct worksheet."""
        import openpyxl
        from bulk_import_staging import import_excel

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Data"
        ws1.append(["Name", "Price"])
        ws1.append(["Product A", "10.00"])

        ws2 = wb.create_sheet("Other")
        ws2.append(["Name", "Price"])
        ws2.append(["Product B", "20.00"])

        wb.save(self._tmp.name)
        wb.close()

        table = import_excel(self._tmp.name, sheet="Other")
        self.assertEqual(table.row_count, 1)
        self.assertEqual(table.rows[0]["Name"], "Product B")


class TestCommitStagedProducts(unittest.TestCase):
    """Test commit_staged_products() with mocked database functions."""

    def _build_staged_table(self, rows_data):
        """Helper: build a StagingTable with auto-mapped columns from header names."""
        from bulk_import_staging import StagingTable
        t = StagingTable()
        t.set_columns([
            "Name", "Price", "Manufacturer Barcode",
            "Internal Unique Barcode", "DEA Schedule",
        ])
        t.auto_map_csv_headers()
        for row in rows_data:
            t.add_row(row)
        return t

    def test_commit_adds_new_products(self):
        """commit_staged_products() calls add_product with correct parsed data."""
        from bulk_import_staging import commit_staged_products

        table = self._build_staged_table([
            ["Aspirin", "5.99", "012345678901", "INT-001", "OTC"],
            ["Ibuprofen", "6.50", "012345678902", "INT-002", "OTC"],
        ])

        with patch("database.add_product") as mock_add, \
             patch("database.update_product_full") as mock_update, \
             patch("database.get_product_by_internal_barcode", return_value=None):
            result = commit_staged_products(table)

        self.assertEqual(result["added"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(mock_add.call_count, 2)
        self.assertEqual(mock_update.call_count, 0)

        first = mock_add.call_args_list[0].kwargs
        self.assertEqual(first["name"], "Aspirin")
        self.assertIsInstance(first["price"], float)
        self.assertEqual(first["price"], 5.99)
        self.assertEqual(first["manufacturer_barcode"], "012345678901")
        self.assertEqual(first["internal_unique_barcode"], "INT-001")

        second = mock_add.call_args_list[1].kwargs
        self.assertEqual(second["name"], "Ibuprofen")
        self.assertEqual(second["price"], 6.50)
        self.assertEqual(second["internal_unique_barcode"], "INT-002")

    def test_commit_updates_existing_products(self):
        """commit_staged_products() calls update_product_full when product exists."""
        from bulk_import_staging import commit_staged_products

        table = self._build_staged_table([
            ["Aspirin", "5.99", "012345678901", "INT-001", "OTC"],
            ["Ibuprofen", "6.50", "012345678902", "INT-002", "OTC"],
        ])

        with patch("database.add_product") as mock_add, \
             patch("database.update_product_full") as mock_update, \
             patch("database.get_product_by_internal_barcode", return_value=(42,)):
            result = commit_staged_products(table)

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["updated"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(mock_update.call_count, 2)
        self.assertEqual(mock_add.call_count, 0)

        update_call = mock_update.call_args_list[0].kwargs
        self.assertEqual(update_call["product_id"], 42)
        self.assertEqual(update_call["name"], "Aspirin")
        self.assertEqual(update_call["price"], 5.99)
        self.assertEqual(update_call["internal_barcode"], "INT-001")

    def test_commit_skips_missing_internal_barcode(self):
        """Rows without internal_unique_barcode are counted as errors."""
        from bulk_import_staging import commit_staged_products

        table = self._build_staged_table([
            ["", "", "", "", ""],  # empty row — no internal barcode
            ["Aspirin", "5.99", "012345678901", "INT-002", "OTC"],
        ])

        with patch("database.add_product") as mock_add, \
             patch("database.update_product_full") as mock_update, \
             patch("database.get_product_by_internal_barcode", return_value=None):
            result = commit_staged_products(table)

        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(mock_add.call_count, 1)
        self.assertEqual(mock_update.call_count, 0)


class TestNDCDictionary(unittest.TestCase):
    """Test ndc_dictionary.py with an isolated in-memory SQLite database."""

    def setUp(self):
        import ndc_dictionary
        self._ndd = ndc_dictionary
        # Close any lingering shared handle
        if self._ndd._shared_handle:
            try:
                self._ndd._shared_handle.close()
            except Exception:
                pass
        self._ndd._initialized = False
        self._ndd._DB_PATH = ""
        self._ndd._shared_handle = None
        # Initialize fresh in-memory database
        self._ndd.init_ndc_dictionary(":memory:")

    def tearDown(self):
        import ndc_dictionary
        ndd = ndc_dictionary
        if ndd._shared_handle:
            try:
                ndd._shared_handle.close()
            except Exception:
                pass
        ndd._initialized = False
        ndd._DB_PATH = ""
        ndd._shared_handle = None

    def _seed_data(self, rows):
        """Write a temp CSV with the standard NDC header and return its path."""
        header = ("ndc_code,drug_name,strength,manufacturer,dosage_form,"
                  "awp,dea_schedule,manufacturer_barcode,ndc_formatted\n")
        content = header + "".join(
            ",".join(str(v) for v in r) + "\n" for r in rows
        )
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_barcode_lookup_nonexistent(self):
        """barcode_lookup() returns None for unknown barcodes."""
        self.assertIsNone(self._ndd.barcode_lookup("000000000000"))
        self.assertIsNone(self._ndd.barcode_lookup("nonexistent-barcode-12345"))

    def test_barcode_lookup_empty_and_none(self):
        """barcode_lookup() returns None for empty/None input."""
        self.assertIsNone(self._ndd.barcode_lookup(""))
        self.assertIsNone(self._ndd.barcode_lookup(None))

    def test_name_lookup_partial_match(self):
        """name_lookup() returns results for partial string matches."""
        rows = [
            ("11111-001", "Amoxicillin 500mg", "500mg", "PharmaCo", "Capsule", "3.50", "OTC", "111345678901", "11111-001"),
            ("11111-002", "Amoxicillin 250mg", "250mg", "PharmaCo", "Capsule", "2.00", "OTC", "111345678902", "11111-002"),
            ("22222-001", "Lisinopril 10mg", "10mg", "CardioLab", "Tablet", "1.25", "OTC", "222345678901", "22222-001"),
        ]
        csv_path = self._seed_data(rows)
        try:
            self._ndd.bulk_load_ndc(csv_path)
            results = self._ndd.name_lookup("Amoxicillin")
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r["drug_name"].startswith("Amoxicillin") for r in results))
        finally:
            os.unlink(csv_path)

    def test_name_lookup_no_match_returns_empty_list(self):
        """name_lookup() returns empty list when no drugs match."""
        rows = [
            ("11111-001", "Amoxicillin 500mg", "500mg", "PharmaCo", "Capsule", "3.50", "OTC", "111345678901", "11111-001"),
        ]
        csv_path = self._seed_data(rows)
        try:
            self._ndd.bulk_load_ndc(csv_path)
            results = self._ndd.name_lookup("NonexistentDrug")
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)
        finally:
            os.unlink(csv_path)

    def test_normalize_dea(self):
        """_normalize_dea() handles SCHEDULE prefix, CIIS/CIV variants, lowercase, and empty."""
        from ndc_dictionary import _normalize_dea

        # "SCHEDULE II" — key becomes "II" but "II" not in _DEA_SCHEDULES,
        # so default (raw uppercased) is returned.
        self.assertEqual(_normalize_dea("SCHEDULE II"), "SCHEDULE II")
        self.assertEqual(_normalize_dea("SCHEDULE III"), "SCHEDULE III")
        self.assertEqual(_normalize_dea("SCHEDULE IV"), "SCHEDULE IV")

        # CIIS → CII (mapped in _DEA_SCHEDULES)
        self.assertEqual(_normalize_dea("CIIS"), "CII")

        # cIV → CIV (mapped in _DEA_SCHEDULES, case-insensitive via .upper())
        self.assertEqual(_normalize_dea("cIV"), "CIV")

        # Lowercase Roman-style entries
        self.assertEqual(_normalize_dea("cii"), "CII")
        self.assertEqual(_normalize_dea("cIII"), "CIII")

        # Lowercase schedule prefix
        self.assertEqual(_normalize_dea("schedule ii"), "SCHEDULE II")

        # Standard schedules
        self.assertEqual(_normalize_dea("CV"), "CV")
        self.assertEqual(_normalize_dea("cv"), "CV")

        # OTC / na / empty / None
        self.assertEqual(_normalize_dea("na"), "OTC")
        self.assertEqual(_normalize_dea(""), "OTC")
        self.assertEqual(_normalize_dea(None), "OTC")
        self.assertEqual(_normalize_dea("OTC"), "OTC")

    def test_bulk_load_ndc_missing_file(self):
        """bulk_load_ndc() returns 0 and does not raise for a missing file."""
        count = self._ndd.bulk_load_ndc("/nonexistent/path/to/missing.csv")
        self.assertEqual(count, 0)

    def test_bulk_load_ndc_malformed_csv(self):
        """bulk_load_ndc() returns 0 and does not raise for malformed CSV data."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        tmp.write(
            "ndc_code,drug_name,strength,manufacturer,dosage_form,"
            "awp,dea_schedule,manufacturer_barcode,ndc_formatted\n"
        )
        tmp.write("GOODCODE,GoodDrug,10mg,Manufacturer,Tablet,5.00,OTC,BARCODE001,GOODCODE\n")
        tmp.write("BADCODE,BadDrug,10mg,Manufacturer,Tablet,NOT_A_NUMBER,OTC,BARCODE002,BADCODE\n")
        tmp.close()
        try:
            count = self._ndd.bulk_load_ndc(tmp.name)
            self.assertEqual(count, 0)
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
```

### Step 3.2 — Run verification

```bash
cd /d "E:\my progam pharmacy\archive"
python -m pytest test_enterprise_edge_cases.py -v            # or: python -m unittest test_enterprise_edge_cases -v
python -m pytest test_phase16.py -v                         # no regression
```

---

## 4. Failure Modes & Edge Cases Handled

| Scenario | Assertion |
|---|---|
| `import_excel` with empty cells | `str(v) if v is not None else ""` — empty cells become `""` strings |
| `commit_staged_products` with all-empty row | Row skipped, `errors += 1`, `add_product` not called for that row |
| `commit_staged_products` with existing product | `update_product_full` called with `product_id=existing[0]` (tuple index) |
| `barcode_lookup(None)` | `if not barcode: return None` — returns None without DB query |
| `name_lookup("")` | `if not drug_name: return []` — returns empty list without DB query |
| `bulk_load_ndc` with bad `float("awp")` | `ValueError` caught by outer `except`, `conn.rollback()`, `return 0` |
| NDC shared in-memory DB leakage | `_shared_handle` closed in tearDown + globals reset in both setUp/tearDown |
| `native_accel` rapidfuzz header matching | Headers match exactly at Step-1, so rapidfuzz and fallback produce identical mapping |

---

## 5. Non-Goals / Scope Guardrails

- No source files modified (`bulk_import_staging.py`, `ndc_dictionary.py`, `database.py` are read-only)
- No new dependencies (openpyxl, sqlite3, unittest, unittest.mock all already in repo)
- No speculative tests beyond the required edge cases (no performance benchmarks, no integration with real database)
- NDC tests use `:memory:` (not temp files) per the constraint

---

## 6. Verification Checklist

```bash
cd /d "E:\my progam pharmacy\archive"
python -m pytest test_enterprise_edge_cases.py -v          # all 8 tests pass
python -m pytest test_phase16.py -v                         # no regression (>=74 existing tests pass)
python -m pytest test_enterprise_edge_cases.py test_phase16.py -v   # both together pass
```
