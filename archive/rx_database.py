"""
rx_database.py — RX Workflow data layer.
Mirrors database.py: thin sqlite3 wrappers with @_db_fallback-style
decorator that tries db.py ORM first, then falls back to raw sqlite3.
"""
import sqlite3
import os
import json
import logging
import functools
from datetime import datetime

try:
    import db as _db
    _HAS_DB = getattr(_db, "HAS_SQLALCHEMY", False)
except ImportError:
    _db = None
    _HAS_DB = False

import rx_db as _rx_db

log = logging.getLogger("rx_database")


def _get_db_path():
    """Resolve the SQLite path (PHARMACY_DB_PATH overrides; relative -> app root).

    Mirrors database.get_db_path: test/CI isolation first, then a CWD-safe
    normalized config path so the live DB is never created relative to CWD.
    """
    env = os.environ.get("PHARMACY_DB_PATH")
    if env:
        return env
    import barcode_logic
    config = barcode_logic.load_config()
    from path_utils import get_resource_path
    p = config.get("db_path", "pharmacy.db")
    return p if os.path.isabs(p) else get_resource_path(p)


def _connect():
    """Create a sqlite3 connection with Row factory and FK enforcement."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _db_fallback(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if _HAS_DB:
            try:
                return getattr(_db, func.__name__)(*args, **kwargs)
            except Exception as e:
                log.debug("db.%s failed, falling back to sqlite3: %s", func.__name__, e)
        return func(*args, **kwargs)
    return wrapper


@_db_fallback
def init_rx_tables():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    # ── Migration: ensure insurance columns exist on patients ─────────
    cursor.execute("PRAGMA table_info(patients)")
    _pat_cols = {row[1] for row in cursor.fetchall()}
    for _col in ("insurance_provider", "policy_number", "group_number"):
        if _col not in _pat_cols:
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {_col} TEXT")
            except sqlite3.OperationalError:
                pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            drug_name TEXT NOT NULL,
            dosage TEXT,
            quantity TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            regional_metadata TEXT DEFAULT '{}',
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            user_pin TEXT DEFAULT '',
            details TEXT DEFAULT '',
            region TEXT DEFAULT 'US',
            category TEXT DEFAULT '',
            subject_type TEXT DEFAULT '',
            subject_id INTEGER,
            rx_id INTEGER,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            gdpr_deleted INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rx_config (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


@_db_fallback
def get_prescription_by_id(rx_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, drug_name, dosage, quantity, status, regional_metadata, created_at, updated_at FROM prescriptions WHERE id = ?",
        (rx_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    metadata = {}
    if row["regional_metadata"]:
        try:
            metadata = json.loads(row["regional_metadata"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}
    return (
        row["id"],
        row["drug_name"],
        row["dosage"],
        row["quantity"],
        row["status"],
        metadata,
        row["created_at"],
        row["updated_at"],
    )


@_db_fallback
def add_prescription(patient_id, drug_name, dosage, quantity, custom_fields=None):
    conn = _connect()
    cursor = conn.cursor()
    metadata = json.dumps(custom_fields) if custom_fields else "{}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """INSERT INTO prescriptions (patient_id, drug_name, dosage, quantity, status, created_at, regional_metadata)
           VALUES (?, ?, ?, ?, 'Pending', ?, ?)""",
        (patient_id, drug_name, dosage, quantity, now, metadata),
    )
    conn.commit()
    rx_id = cursor.lastrowid
    conn.close()
    return rx_id


@_db_fallback
def update_prescription(rx_id, update_fields=None):
    conn = _connect()
    cursor = conn.cursor()
    updates = []
    values = []
    if "drug_name" in update_fields:
        updates.append("drug_name = ?")
        values.append(update_fields["drug_name"])
    if "dosage" in update_fields:
        updates.append("dosage = ?")
        values.append(update_fields["dosage"])
    if "quantity" in update_fields:
        updates.append("quantity = ?")
        values.append(update_fields["quantity"])
    if "status" in update_fields:
        updates.append("status = ?")
        values.append(update_fields["status"])
    if "custom_fields" in update_fields:
        updates.append("regional_metadata = ?")
        values.append(json.dumps(update_fields["custom_fields"]))
    if not updates:
        conn.close()
        return
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(rx_id)
    cursor.execute(
        f"UPDATE prescriptions SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
        values,
    )
    conn.commit()
    conn.close()


@_db_fallback
def get_prescriptions_by_patient(patient_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, patient_id, drug_name, dosage, quantity, status, created_at, updated_at
           FROM prescriptions WHERE patient_id = ? ORDER BY created_at DESC""",
        (patient_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "patient_id": row["patient_id"],
            "drug_name": row["drug_name"],
            "dosage": row["dosage"],
            "quantity": row["quantity"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return result


@_db_fallback
def get_distinct_rx_field_names():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT json_each.key as field_name
        FROM prescriptions, json_each(prescriptions.regional_metadata)
        WHERE prescriptions.regional_metadata != '{}'
        ORDER BY field_name ASC
    """)
    names = [row["field_name"] for row in cursor.fetchall() if row["field_name"]]
    conn.close()
    return names


@_db_fallback
def search_prescriptions(query):
    conn = _connect()
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute(
        """SELECT id, drug_name, dosage, quantity, status, created_at
           FROM prescriptions
           WHERE drug_name LIKE ? OR status LIKE ?
           ORDER BY created_at DESC""",
        (like_query, like_query),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@_db_fallback
def delete_prescription(rx_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM prescriptions WHERE id = ?", (rx_id,))
    conn.commit()
    conn.close()


def _load_prescriptions(self, filter_status=None):
    """Populate the RX workflow treeview/listbox.
    Called back from ui_rx_workflow.on_save after CRUD operations.
    """
    rows = []
    conn = _connect()
    cursor = conn.cursor()
    if filter_status:
        cursor.execute(
            """SELECT id, drug_name, dosage, quantity, status
               FROM prescriptions WHERE status = ? ORDER BY created_at DESC""",
            (filter_status,),
        )
    else:
        cursor.execute(
            """SELECT id, drug_name, dosage, quantity, status
               FROM prescriptions ORDER BY created_at DESC"""
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
