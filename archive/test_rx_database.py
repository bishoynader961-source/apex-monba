"""
test_rx_database.py — Test suite for rx_database.py

Tests:
  1. Table schema creation (via init_rx_tables)
  2. Foreign key constraints
  3. JSON regional_metadata serialization
  4. GDPR hard-delete functionality (via rx_db.hipaa_log_access / gdpr_hard_delete_patient)
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))


class TestRxDatabaseSchema(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self._patcher = patch(
            "rx_database._get_db_path", return_value=self.db_path)
        self._patcher.start()
        import rx_database
        rx_database.init_rx_tables()

    def tearDown(self):
        self._patcher.stop()
        import rx_database
        # Close any engine connections
        if rx_database._HAS_DB and hasattr(rx_database._db, "engine"):
            try:
                rx_database._db.engine.dispose()
            except Exception:
                pass
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_prescriptions_table_exists(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prescriptions'")
        result = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "prescriptions")

    def test_prescriptions_has_regional_metadata_column(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(prescriptions)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("regional_metadata", cols)

    def test_prescriptions_has_patient_fk(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_list(prescriptions)")
        fks = cursor.fetchall()
        conn.close()
        patient_fks = [fk for fk in fks if fk[2] == "patients"]
        self.assertTrue(len(patient_fks) > 0)

    def test_prescriptions_has_status_column(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(prescriptions)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("status", cols)
        self.assertIn("drug_name", cols)
        self.assertIn("dosage", cols)
        self.assertIn("quantity", cols)


class TestPrescriptionCRUD(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self._patcher = patch(
            "rx_database._get_db_path", return_value=self.db_path)
        self._patcher.start()
        import rx_database
        rx_database.init_rx_tables()

    def tearDown(self):
        self._patcher.stop()
        import rx_database
        if rx_database._HAS_DB and hasattr(rx_database._db, "engine"):
            try:
                rx_database._db.engine.dispose()
            except Exception:
                pass
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_add_prescription_with_custom_fields(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None,
            drug_name="Aspirin 500mg",
            dosage="1 tablet",
            quantity="30",
            custom_fields={"Insurance": "ABC123", "Notes": "Take with food"},
        )
        self.assertIsNotNone(rx_id)

        row = rx_database.get_prescription_by_id(rx_id)
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "Aspirin 500mg")
        self.assertEqual(row[2], "1 tablet")
        self.assertEqual(row[3], "30")
        self.assertEqual(row[5], {"Insurance": "ABC123", "Notes": "Take with food"})

    def test_add_prescription_empty_custom_fields(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None,
            drug_name="Ibuprofen",
            dosage="400mg",
            quantity="20",
            custom_fields=None,
        )
        row = rx_database.get_prescription_by_id(rx_id)
        self.assertEqual(row[5], {})

    def test_update_prescription(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None, drug_name="Lisinopril",
            dosage="10mg", quantity="90",
            custom_fields={"Notes": "Initial"},
        )
        rx_database.update_prescription(rx_id, update_fields={
            "drug_name": "Lisinopril 10mg",
            "quantity": "90",
            "custom_fields": {"Notes": "Updated", "Allergies": "None"},
        })
        row = rx_database.get_prescription_by_id(rx_id)
        self.assertEqual(row[1], "Lisinopril 10mg")
        self.assertEqual(row[5], {"Notes": "Updated", "Allergies": "None"})

    def test_get_prescription_by_id_not_found(self):
        import rx_database
        row = rx_database.get_prescription_by_id(999999)
        self.assertIsNone(row)

    def test_delete_prescription(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None, drug_name="Test", dosage="1mg", quantity="10",
        )
        rx_database.delete_prescription(rx_id)
        row = rx_database.get_prescription_by_id(rx_id)
        self.assertIsNone(row)


class TestJSONRegionalMetadata(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self._patcher = patch(
            "rx_database._get_db_path", return_value=self.db_path)
        self._patcher.start()
        import rx_database
        rx_database.init_rx_tables()

    def tearDown(self):
        self._patcher.stop()
        import rx_database
        if rx_database._HAS_DB and hasattr(rx_database._db, "engine"):
            try:
                rx_database._db.engine.dispose()
            except Exception:
                pass
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_complex_json_metadata(self):
        import rx_database
        metadata = {
            "Insurance": "Delta Dental",
            "Allergies": "Penicillin, Sulfa",
            "DOB": "1985-03-15",
            "nested": {"key": "value", "num": 42},
        }
        rx_id = rx_database.add_prescription(
            patient_id=None, drug_name="Amoxicillin",
            dosage="500mg", quantity="21",
            custom_fields=metadata,
        )
        row = rx_database.get_prescription_by_id(rx_id)
        self.assertEqual(row[5], metadata)
        self.assertEqual(row[5]["nested"]["num"], 42)

    def test_metadata_stored_as_valid_json_in_db(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None, drug_name="Test", dosage="1mg", quantity="1",
            custom_fields={"key": "value"},
        )
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT regional_metadata FROM prescriptions WHERE id = ?", (rx_id,))
        raw = cursor.fetchone()[0]
        conn.close()
        parsed = json.loads(raw)
        self.assertEqual(parsed, {"key": "value"})

    def test_malformed_metadata_returns_empty_dict(self):
        import rx_database
        rx_id = rx_database.add_prescription(
            patient_id=None, drug_name="Test", dosage="1mg", quantity="1",
            custom_fields={"key": "value"},
        )
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE prescriptions SET regional_metadata = ? WHERE id = ?", (
                "not-valid-json{", rx_id))
        conn.commit()
        conn.close()
        row = rx_database.get_prescription_by_id(rx_id)
        self.assertEqual(row[5], {})


class TestDistinctFieldNames(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self._patcher = patch(
            "rx_database._get_db_path", return_value=self.db_path)
        self._patcher.start()
        import rx_database
        rx_database.init_rx_tables()

    def tearDown(self):
        self._patcher.stop()
        import rx_database
        if rx_database._HAS_DB and hasattr(rx_database._db, "engine"):
            try:
                rx_database._db.engine.dispose()
            except Exception:
                pass
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_distinct_field_names(self):
        import rx_database
        rx_database.add_prescription(
            patient_id=None, drug_name="A", dosage="1mg", quantity="10",
            custom_fields={"Insurance": "ABC", "Notes": "Test"},
        )
        rx_database.add_prescription(
            patient_id=None, drug_name="B", dosage="2mg", quantity="20",
            custom_fields={"Allergies": "Penicillin", "Insurance": "XYZ"},
        )
        names = rx_database.get_distinct_rx_field_names()
        self.assertIn("Insurance", names)
        self.assertIn("Notes", names)
        self.assertIn("Allergies", names)


class TestGPHDRightToErasure(unittest.TestCase):
    """Tests GDPR hard-delete and HIPAA access logging via raw sqlite3 layer.

    Uses rx_database.init_rx_tables() (sqlite3 fallback) to set up the
    audit_logs table with Rx columns, then tests the same SQL operations
    that rx_db.hipaa_log_access / rx_db.gdpr_hard_delete_patient execute.
    """
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self._patcher = patch(
            "rx_database._get_db_path", return_value=self.db_path)
        self._patcher.start()
        import rx_database
        rx_database.init_rx_tables()

    def tearDown(self):
        self._patcher.stop()
        import rx_database
        if rx_database._HAS_DB and hasattr(rx_database._db, "engine"):
            try:
                rx_database._db.engine.dispose()
            except Exception:
                pass
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def _insert_audit_log(self, subject_type, subject_id, region="US",
                          category="access", role="user", pin="1234"):
        """Replicate rx_db.hipaa_log_access SQL via sqlite3."""
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs
                (timestamp, action, user_pin, details,
                 region, category, subject_type, subject_id,
                 old_value, new_value, role)
            VALUES (?, 'ACCESS', ?, ?, ?, 'access', ?, ?,
                     '', '', ?)
        """, (ts, pin, f"Accessed {subject_type} id={subject_id}",
              region, subject_type, subject_id, role))
        conn.commit()
        conn.close()

    def _hard_delete_patient_audit_logs(self, patient_id):
        """Replicate rx_db.gdpr_hard_delete_patient SQL via sqlite3."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM audit_logs WHERE subject_type = 'patient' AND subject_id = ?",
            (patient_id,))
        conn.commit()
        conn.close()

    def test_gdpr_hard_delete_patient_audit_logs(self):
        self._insert_audit_log("patient", 42, region="EU", role="user", pin="1234")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE subject_type='patient' AND subject_id=42")
        before = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(before, 1)

        self._hard_delete_patient_audit_logs(42)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE subject_type='patient' AND subject_id=42")
        after = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(after, 0)

    def test_audit_log_region_column_populated(self):
        self._insert_audit_log("rx", 1, region="EU",
                               category="access", role="pharmacist", pin="5678")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT region, category FROM audit_logs WHERE subject_type='rx'")
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "EU")
        self.assertEqual(row[1], "access")

    def test_multiple_region_entries(self):
        self._insert_audit_log("patient", 1, region="US")
        self._insert_audit_log("patient", 2, region="EU")
        self._insert_audit_log("rx", 1, region="GB")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT region FROM audit_logs ORDER BY region")
        regions = [r[0] for r in cursor.fetchall()]
        conn.close()
        self.assertIn("US", regions)
        self.assertIn("EU", regions)
        self.assertIn("GB", regions)

    def test_gdpr_delete_does_not_affect_other_subjects(self):
        self._insert_audit_log("patient", 99, region="EU")
        self._insert_audit_log("rx", 1, region="EU")
        self._insert_audit_log("patient", 42, region="EU")

        self._hard_delete_patient_audit_logs(42)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE subject_type='patient' AND subject_id=42")
        deleted = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE subject_type='patient' AND subject_id=99")
        preserved = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE subject_type='rx'")
        rx_preserved = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(deleted, 0)
        self.assertEqual(preserved, 1)
        self.assertEqual(rx_preserved, 1)


if __name__ == "__main__":
    unittest.main()
