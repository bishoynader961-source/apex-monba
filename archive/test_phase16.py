"""
test_phase16.py — Unit tests for Phase 16 Enterprise modules.

Tests:
  - ndc_dictionary: init, lookup, bulk_load, stats
  - quick_sig: save/load/delete/toggle_favorite/get_sig_suggestions (sqlite3 fallback)
  - rx_migrations: run_rx_migrations, get_inventory_extended_schema
  - bulk_import_staging: StagingTable auto-map, import_csv
  - database DEA columns: init_db adds dea_schedule, wholesale_price, reorder_threshold
  - i18n: all new Phase 16 keys present in all 6 locales
"""
import os
import sys

# CRITICAL: route the ORM engine + sqlite3 fallback to a disposable temp DB
# BEFORE any `import database` / `import db` resolves DATABASE_URL at import
# time. This protects the production archive/pharmacy.db.
import test_db_fixture  # noqa: F401  (must precede database/db imports)

import json
import csv
import tempfile
import sqlite3
import unittest

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
if ARCHIVE_DIR not in sys.path:
    sys.path.insert(0, ARCHIVE_DIR)


class BaseTempDBTestCase(unittest.TestCase):
    """Base class that provisions a temp database for each test."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_db_path = None

    def tearDown(self):
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _patch_db_path(self):
        """Patch database.get_db_path to return the temp DB path."""
        import database
        self._orig_db_path = database.get_db_path
        database.get_db_path = lambda: self._tmp.name

    def _unpatch_db_path(self):
        import database
        if self._orig_db_path is not None:
            database.get_db_path = self._orig_db_path


class TestNDCDictionary(unittest.TestCase):
    """Test ndc_dictionary.py: init, lookups, bulk_load."""

    def setUp(self):
        import ndc_dictionary
        self._ndd = ndc_dictionary
        # Use a unique temp file DB to avoid shared in-memory persistence
        self._ndc_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._ndc_tmp.close()
        if self._ndd._shared_handle:
            try:
                self._ndd._shared_handle.close()
            except Exception:
                pass
        self._ndd._initialized = False
        self._ndd._DB_PATH = ""
        self._ndd._shared_handle = None
        self._ndd.init_ndc_dictionary(self._ndc_tmp.name)

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
        try:
            os.unlink(self._ndc_tmp.name)
        except OSError:
            pass

    def test_init_returns_path(self):
        path = self._ndd.init_ndc_dictionary(":memory:")
        self.assertIsNotNone(path)

    def test_empty_lookup_returns_none(self):
        self.assertIsNone(self._ndd.ndc_lookup("99999-9999-99"))
        self.assertIsNone(self._ndd.barcode_lookup("000000000000"))

    def test_bulk_load_and_lookup(self):
        csv_content = (
            "ndc_code,drug_name,strength,manufacturer,dosage_form,awp,dea_schedule,manufacturer_barcode,ndc_formatted\n"
            "52094001,Acetaminophen,500mg,MfgCo,Tablet,3.50,OTC,012345678901,52094-001\n"
            "52094002,Ibuprofen,200mg,MfgCo,Tablet,4.25,OTC,012345678902,52094-002\n"
        )
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        tmp.write(csv_content)
        tmp.close()
        try:
            count = self._ndd.bulk_load_ndc(tmp.name)
            self.assertEqual(count, 2)
            result = self._ndd.ndc_lookup("52094001")
            self.assertIsNotNone(result)
            self.assertEqual(result["drug_name"], "Acetaminophen")
            bar_result = self._ndd.barcode_lookup("012345678901")
            self.assertEqual(bar_result["drug_name"], "Acetaminophen")
        finally:
            os.unlink(tmp.name)

    def test_get_dictionary_stats_empty(self):
        stats = self._ndd.get_dictionary_stats()
        self.assertEqual(stats["total_entries"], 0)

    def test_timed_lookup_empty(self):
        result, elapsed = self._ndd.timed_lookup("99999-9999-99")
        self.assertIsNone(result)
        self.assertGreaterEqual(elapsed, 0.0)

    def test_dea_normalization(self):
        csv_content = "ndc_code,drug_name,strength,manufacturer,dosage_form,awp,dea_schedule,manufacturer_barcode,ndc_formatted\n52094003,Metric,10mg,MfgCo,Tablet,5.00,II,012345678903,52094-003\n"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        tmp.write(csv_content)
        tmp.close()
        try:
            self._ndd.bulk_load_ndc(tmp.name)
            result = self._ndd.ndc_lookup("52094003")
            self.assertEqual(result["dea_schedule"], "II")
        finally:
            os.unlink(tmp.name)

    def test_lookup_by_formatted_ndc(self):
        csv_content = "ndc_code,drug_name,strength,manufacturer,dosage_form,awp,dea_schedule,manufacturer_barcode,ndc_formatted\n52094004,Test,10mg,MfgCo,Tablet,5.00,OTC,012345678904,52094-004\n"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        tmp.write(csv_content)
        tmp.close()
        try:
            self._ndd.bulk_load_ndc(tmp.name)
            result = self._ndd.ndc_lookup("52094-004")
            self.assertIsNotNone(result)
            self.assertEqual(result["drug_name"], "Test")
        finally:
            os.unlink(tmp.name)


class TestQuickSigDB(BaseTempDBTestCase):
    """Test quick_sig.py DB functions using sqlite3 fallback path."""

    def setUp(self):
        super().setUp()
        self._patch_db_path()
        import quick_sig
        self._qs = quick_sig
        self._orig_use_sqla = quick_sig._USE_SQLA
        quick_sig._USE_SQLA = False
        self._orig_qs_db_path = quick_sig.get_db_path
        quick_sig.get_db_path = lambda: self._tmp.name

        # Create tables
        import database
        database.get_db_path = lambda: self._tmp.name
        database.init_db()

    def tearDown(self):
        self._qs._USE_SQLA = self._orig_use_sqla
        self._qs.get_db_path = self._orig_qs_db_path
        self._unpatch_db_path()
        super().tearDown()

    def test_save_and_load_template(self):
        tid = self._qs.save_quick_sig_template(
            name="Test Template", drug_name="Aspirin", dose="500mg",
            route="by mouth", frequency="BID", duration="7 days",
            directions="Take 1 tablet twice daily", is_favorite=1,
        )
        self.assertIsInstance(tid, int)
        templates = self._qs.load_quick_sig_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["name"], "Test Template")
        self.assertEqual(templates[0]["drug_name"], "Aspirin")

    def test_load_favorites_only(self):
        self._qs.save_quick_sig_template(name="Fav", drug_name="A", is_favorite=1)
        self._qs.save_quick_sig_template(name="NonFav", drug_name="B", is_favorite=0)
        favs = self._qs.load_quick_sig_templates(favorites_only=True)
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs[0]["name"], "Fav")

    def test_delete_template(self):
        tid = self._qs.save_quick_sig_template(name="ToDelete")
        self.assertTrue(self._qs.delete_quick_sig_template(tid))
        self.assertEqual(len(self._qs.load_quick_sig_templates()), 0)

    def test_toggle_favorite(self):
        tid = self._qs.save_quick_sig_template(name="ToggleTest", is_favorite=0)
        new_val = self._qs.toggle_favorite(tid)
        self.assertEqual(new_val, 1)
        new_val = self._qs.toggle_favorite(tid)
        self.assertEqual(new_val, 0)

    def test_get_sig_suggestions(self):
        self._qs.save_quick_sig_template(name="Morning Antibiotic", directions="Take 1 tablet by mouth")
        self._qs.save_quick_sig_template(name="Evening Pill", directions="Swallow whole")
        results = self._qs.get_sig_suggestions("morning")
        self.assertEqual(len(results), 1)
        results = self._qs.get_sig_suggestions("evening")
        self.assertEqual(len(results), 1)
        results = self._qs.get_sig_suggestions("xyz_no_match")
        self.assertEqual(len(results), 0)
        results = self._qs.get_sig_suggestions("")
        self.assertEqual(len(results), 0)  # No favorites saved


class TestRxMigrations(BaseTempDBTestCase):
    """Test rx_migrations.py on a temp database with inventory_extended."""

    def setUp(self):
        super().setUp()
        conn = sqlite3.connect(self._tmp.name)
        conn.execute("CREATE TABLE inventory_extended (id INTEGER PRIMARY KEY, ndc_code TEXT, drug_name TEXT)")
        conn.commit()
        conn.close()

    def tearDown(self):
        self._unpatch_db_path()
        super().tearDown()

    def test_adds_all_columns(self):
        from rx_migrations import run_rx_migrations, get_inventory_extended_schema
        applied = run_rx_migrations(self._tmp.name)
        self.assertIn("inventory_extended.dea_schedule", applied)
        self.assertIn("inventory_extended.wholesale_price", applied)
        self.assertIn("inventory_extended.reorder_threshold", applied)
        cols = get_inventory_extended_schema(self._tmp.name)
        self.assertIn("dea_schedule", cols)
        self.assertIn("wholesale_price", cols)
        self.assertIn("reorder_threshold", cols)

    def test_idempotent(self):
        from rx_migrations import run_rx_migrations
        run_rx_migrations(self._tmp.name)
        applied = run_rx_migrations(self._tmp.name)
        self.assertEqual(len(applied), 0)


class TestDatabaseDEAMigration(BaseTempDBTestCase):
    """Test that database.init_db() adds DEA columns to products (sqlite3 fallback)."""

    def setUp(self):
        super().setUp()
        self._patch_db_path()
        import database
        database.get_db_path = lambda: self._tmp.name
        # Force sqlite3 fallback to avoid db.py SQLAlchemy engine
        self._orig_has_db = database._HAS_DB
        database._HAS_DB = False
        # Create products table with base columns only
        conn = sqlite3.connect(self._tmp.name)
        conn.execute("""CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL,
            manufacturer_barcode TEXT, internal_unique_barcode TEXT UNIQUE,
            status TEXT DEFAULT 'In Stock'
        )""")
        conn.execute("CREATE TABLE templates (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
        conn.execute("CREATE TABLE sold_items (id INTEGER PRIMARY KEY, item_name TEXT, price REAL, manufacturer_barcode TEXT, internal_barcode TEXT, timestamp_of_sale TEXT)")
        conn.execute("CREATE TABLE receiving_log (id INTEGER PRIMARY KEY, vendor_name TEXT, product_name TEXT, date_received TEXT, quantity INTEGER, total_cost REAL)")
        conn.execute("CREATE TABLE receipts (id INTEGER PRIMARY KEY, timestamp TEXT, total_amount REAL, payment_method TEXT)")
        conn.execute("CREATE TABLE receipt_items (id INTEGER PRIMARY KEY, receipt_id INTEGER, product_name TEXT, quantity INTEGER, price_at_time REAL, internal_barcode TEXT, vendor TEXT, expiry_date TEXT)")
        conn.execute("CREATE TABLE patients (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE patient_fields (id INTEGER PRIMARY KEY, patient_id INTEGER, field_name TEXT, field_value TEXT)")
        conn.commit()
        conn.close()

    def tearDown(self):
        import database
        database._HAS_DB = self._orig_has_db
        self._unpatch_db_path()
        super().tearDown()

    def test_dea_columns_present_after_init(self):
        import database
        database.init_db()
        conn = sqlite3.connect(self._tmp.name)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
        conn.close()
        self.assertIn("dea_schedule", cols)
        self.assertIn("wholesale_price", cols)
        self.assertIn("reorder_threshold", cols)

    def test_dea_column_defaults(self):
        import database
        database.init_db()
        database.add_product("TestDrug", 10.0, "BC123", "INT001")
        conn = sqlite3.connect(self._tmp.name)
        row = conn.execute(
            "SELECT dea_schedule, wholesale_price, reorder_threshold FROM products WHERE internal_unique_barcode = 'INT001'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "OTC")
        self.assertEqual(row[1], 0.0)
        self.assertEqual(row[2], 0)

    def test_add_product_with_dea_values(self):
        import database
        database.init_db()
        database.add_product("TestDrug2", 15.0, "BC456", "INT002",
                            dea_schedule="CIII", wholesale_price=5.0, reorder_threshold=5)
        conn = sqlite3.connect(self._tmp.name)
        row = conn.execute(
            "SELECT dea_schedule, wholesale_price, reorder_threshold FROM products WHERE internal_unique_barcode = 'INT002'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "CIII")
        self.assertEqual(row[1], 5.0)
        self.assertEqual(row[2], 5)


class TestBulkImportStaging(unittest.TestCase):
    """Test bulk_import_staging.py: StagingTable, auto_map, import_csv."""

    def test_staging_table_basic(self):
        from bulk_import_staging import StagingTable
        t = StagingTable(columns=["name", "price", "dea_schedule"], source_name="test")
        t.add_row(["Aspirin", "5.99", "OTC"])
        t.add_row(["Ibuprofen", "6.50", "OTC"])
        self.assertEqual(t.row_count, 2)
        self.assertEqual(t.columns, ["name", "price", "dea_schedule"])

    def test_auto_map_csv_headers(self):
        from bulk_import_staging import import_csv
        csv_content = "Name,Price,DEASchedule,WholesalePrice,ReorderThreshold,ExpiryDate\nAspirin,5.99,OTC,2.50,10,2027-12-31\n"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        tmp.write(csv_content)
        tmp.close()
        try:
            table = import_csv(tmp.name)
            mapping = table._column_map
            self.assertIn("Name", mapping)
            self.assertEqual(mapping["Name"], "name")
            self.assertIn("Price", mapping)
            self.assertTrue(mapping["DEASchedule"] == "dea_schedule")
            self.assertTrue(mapping["WholesalePrice"] == "wholesale_price")
            self.assertTrue(mapping["ReorderThreshold"] == "reorder_threshold")
            self.assertTrue(mapping["ExpiryDate"] == "expiry_date")
        finally:
            os.unlink(tmp.name)

    def test_to_product_dicts(self):
        from bulk_import_staging import StagingTable
        t = StagingTable()
        t.set_columns(["Name", "Price", "DEASchedule"])
        t.auto_map_csv_headers()
        t.add_row(["Aspirin", "5.99", "OTC"])
        products = t.to_product_dicts()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name"], "Aspirin")
        self.assertEqual(products[0]["price"], 5.99)
        self.assertEqual(products[0]["dea_schedule"], "OTC")

    def test_import_csv_row_count(self):
        from bulk_import_staging import import_csv
        csv_content = "Name,Price,Barcode\nA,1.00,001\nB,2.00,002\nC,3.00,003\n"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
        tmp.write(csv_content)
        tmp.close()
        try:
            table = import_csv(tmp.name)
            self.assertEqual(table.row_count, 3)
        finally:
            os.unlink(tmp.name)


class TestI18nNewKeys(unittest.TestCase):
    """Test that all new Phase 16 i18n keys resolve across all languages."""

    NEW_KEYS = [
        "quick_sig_title", "quick_sig_name", "quick_sig_dose", "quick_sig_route",
        "quick_sig_frequency", "quick_sig_duration", "quick_sig_directions",
        "quick_sig_favorite", "quick_sig_suggestions", "quick_sig_dose_label",
        "quick_sig_route_label", "quick_sig_frequency_label", "quick_sig_duration_label",
        "quick_sig_toggle_favorite", "nav_menu_file", "nav_menu_edit", "nav_menu_view",
        "nav_menu_tools", "nav_menu_help", "status_dashboard_title", "status_dashboard_subtitle",
        "metric_prescriptions_today", "metric_low_stock", "metric_total_patients",
        "metric_total_products", "metric_revenue_today", "task_panel_title",
        "task_new_prescription", "task_process_claim", "task_receive_inventory",
        "task_generate_report", "task_manage_patients", "task_manage_products",
        "task_pos_terminal", "task_quick_sig", "task_audit_log", "task_send_email",
        "pos_retail_title", "pos_retail_fees", "pos_retail_tax_exempt",
        "pos_retail_process_payment", "clinical_workflow_title", "clinical_workflow_subtitle",
        "clinical_wizard_step1", "clinical_wizard_step2", "clinical_wizard_step3",
        "clinical_wizard_step4", "clinical_attachments", "clinical_notes",
        "clinical_allergies", "clinical_interactions", "clinical_documentation",
        "clinical_review_summary", "clinical_submit_prescription",
        "clinical_patient_selection", "clinical_medication_selection",
        "clinical_prescription_details", "bulk_import_title", "bulk_import_subtitle",
        "toolbar_dashboard", "toolbar_inventory", "toolbar_prescriptions",
        "toolbar_patients", "toolbar_reports", "toolbar_clinical",
        "toolbar_quick_sig", "toolbar_settings", "toolbar_bulk_import",
    ]

    def test_keys_resolve_in_all_languages(self):
        LOCALES_DIR = os.path.join(ARCHIVE_DIR, "locales")
        for lang in ["en", "de", "es", "fr", "pt", "ar"]:
            path = os.path.join(LOCALES_DIR, f"{lang}.json")
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in self.NEW_KEYS:
                self.assertIn(key, data, f"Key '{key}' missing from {lang}.json")


class TestMainAppIntegration(unittest.TestCase):
    """Test that main_app._wire_rx_extensions wires all new modules."""

    def test_wire_rx_extensions_references(self):
        """Verify _wire_rx_extensions references all Phase 16 modules."""
        with open(os.path.join(ARCHIVE_DIR, "main_app.py"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("setup_status_dashboard_tab", content)
        self.assertIn("setup_pos_retail_tab", content)
        self.assertIn("setup_clinical_workflow_tab", content)
        self.assertIn("setup_quick_sig_tab", content)
        self.assertIn("setup_enterprise_navigation", content)
        self.assertIn("run_rx_migrations", content)
        self.assertIn("init_ndc_dictionary", content)
        self.assertIn("setup_quick_sig_tab", content)


class TestBackendImmutability(unittest.TestCase):
    """Verify Phase 16 did NOT modify locked backend files."""

    LOCKED_FILES = ["rx_db.py", "rx_config.py", "rx_strategies.py"]

    def test_locked_files_not_modified_to_add_phase16(self):
        for fname in self.LOCKED_FILES:
            path = os.path.join(ARCHIVE_DIR, fname)
            self.assertTrue(os.path.isfile(path), f"Locked file missing: {fname}")

    def test_quick_sig_templates_table_exists_in_database_init(self):
        """Verify quick_sig_templates table is created in database.py init_db."""
        with open(os.path.join(ARCHIVE_DIR, "database.py"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("quick_sig_templates", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
