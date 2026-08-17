"""
ndc_dictionary.py — High-speed local SQLite dictionary for NDC and barcode-based drug autofill.

Provides an in-memory SQLite database optimized for instant O(1) lookups by NDC code
or manufacturer barcode, instantly populating drug name, strength, and manufacturer.

Usage:
    from ndc_dictionary import init_ndc_dictionary, ndc_lookup, barcode_lookup, bulk_load_ndc

    init_ndc_dictionary(db_path="ndc_dictionary.db")
    result = ndc_lookup("00006-0100-10")  # → {ndc_code, drug_name, strength, ...}
    result = barcode_lookup("02556000102")  # → same dict, searched by manufacturer_barcode
"""
import os
import csv
import sqlite3
import logging
import time
import threading

from path_utils import get_resource_path

log = logging.getLogger("ndc_dictionary")

_DB_PATH: str = ""
_initialized = False
_shared_handle: sqlite3.Connection | None = None
_engine_lock = threading.Lock()


def _resolve_db_path(db_path: str) -> str:
    """Resolve db_path, converting ':memory:' to a shared in-memory URI."""
    if db_path == ":memory:":
        return "file:ndc_dict?mode=memory&cache=shared"
    return db_path


def _get_default_db_path() -> str:
    config_path = get_resource_path("config.json")
    try:
        import json
        if os.path.isfile(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            ndc_path = config.get("ndc_dictionary_path", "")
            if ndc_path:
                return ndc_path
    except Exception:
        pass
    return os.path.join(get_resource_path("."), "ndc_dictionary.db")


_DEA_SCHEDULES = {
    "CII": "CII", "CIIS": "CII",
    "CIII": "CIII", "CIIIS": "CIII",
    "CIV": "CIV", "a": "CIII", "b": "CIII",
    "CV": "CV", "c": "CV",
    "na": "OTC", "": "OTC",
}


def _normalize_dea(raw: str) -> str:
    if not raw:
        return "OTC"
    key = raw.strip().upper().replace("SCHEDULE ", "").replace("SCHED", "").strip()
    return _DEA_SCHEDULES.get(key, raw.strip().upper() or "OTC")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ndc_dictionary (
    ndc_code        TEXT PRIMARY KEY,
    drug_name       TEXT NOT NULL,
    strength        TEXT NOT NULL,
    manufacturer    TEXT NOT NULL,
    dosage_form     TEXT,
    awp             REAL,
    dea_schedule    TEXT DEFAULT 'OTC',
    manufacturer_barcode TEXT,
    ndc_formatted   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ndc_code ON ndc_dictionary(ndc_code);
CREATE INDEX IF NOT EXISTS idx_ndc_mfg_barcode ON ndc_dictionary(manufacturer_barcode);
CREATE INDEX IF NOT EXISTS idx_ndc_name ON ndc_dictionary(drug_name);
"""


def init_ndc_dictionary(db_path: str = None) -> str:
    """Initialize the NDC dictionary SQLite database (in-memory or file-backed).

    If db_path is ':memory:', uses a shared in-memory database.
    If db_path is None, reads ndc_dictionary_path from config.json (falls back to ./ndc_dictionary.db).
    Creates tables and indexes. Returns the resolved db_path.
    """
    global _DB_PATH, _initialized, _shared_handle
    with _engine_lock:
        if db_path is None:
            db_path = _get_default_db_path()
        resolved = _resolve_db_path(db_path)
        _DB_PATH = resolved
        _initialized = True
        if resolved == "file:ndc_dict?mode=memory&cache=shared":
            _shared_handle = sqlite3.connect(resolved, uri=True, check_same_thread=False)
            _shared_handle.executescript(_SCHEMA)
            _shared_handle.commit()
        else:
            conn = sqlite3.connect(resolved, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
            conn.close()
        log.debug("NDC dictionary initialized at: %s", db_path)
        return db_path


def _get_conn() -> sqlite3.Connection:
    if not _initialized:
        init_ndc_dictionary()
    if _DB_PATH == "file:ndc_dict?mode=memory&cache=shared":
        conn = sqlite3.connect(_DB_PATH, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ndc_lookup(ndc_code: str) -> dict | None:
    """Look up a drug by its 11-digit NDC code. Returns None if not found.

    Typical result keys: ndc_code, drug_name, strength, manufacturer,
    dosage_form, awp, dea_schedule, manufacturer_barcode, ndc_formatted
    """
    if not ndc_code:
        return None
    code = ndc_code.strip()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "SELECT * FROM ndc_dictionary WHERE ndc_code = ? OR ndc_formatted = ? OR ndc_code = ?",
            (code, code, code.replace("-", "")),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception as e:
        log.error("ndc_lookup failed for '%s': %s", code, e)
        return None
    finally:
        conn.close()


def barcode_lookup(barcode: str) -> dict | None:
    """Look up a drug by its manufacturer barcode (GTIN/UPC). Returns None if not found."""
    if not barcode:
        return None
    code = barcode.strip()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "SELECT * FROM ndc_dictionary WHERE manufacturer_barcode = ? OR ndc_code = ?",
            (code, code),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception as e:
        log.error("barcode_lookup failed for '%s': %s", code, e)
        return None
    finally:
        conn.close()


def name_lookup(drug_name: str) -> list[dict]:
    """Look up drugs by name (fuzzy/substring match). Returns list of dicts."""
    if not drug_name:
        return []
    like = f"%{drug_name.strip()}%"
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "SELECT * FROM ndc_dictionary WHERE drug_name LIKE ? OR ndc_code LIKE ?",
            (like, like),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("name_lookup failed for '%s': %s", drug_name, e)
        return []
    finally:
        conn.close()


def bulk_load_ndc(source: str) -> int:
    """Bulk-load NDC data from a CSV file.

    Expected CSV headers: ndc_code, drug_name, strength, manufacturer,
    dosage_form, awp, dea_schedule, manufacturer_barcode, ndc_formatted

    Returns the number of rows inserted.
    """
    if not os.path.isfile(source):
        log.warning("NDC bulk load: source file not found: %s", source)
        return 0

    conn = _get_conn()
    count = 0
    try:
        with open(source, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                rows.append((
                    row.get("ndc_code", "").strip(),
                    row.get("drug_name", "").strip(),
                    row.get("strength", "").strip(),
                    row.get("manufacturer", "").strip(),
                    row.get("dosage_form", "").strip() or None,
                    float(row["awp"]) if row.get("awp") else None,
                    _normalize_dea(row.get("dea_schedule", "OTC")),
                    row.get("manufacturer_barcode", "").strip() or None,
                    row.get("ndc_formatted", row.get("ndc_code", "")).strip(),
                ))
            count = conn.executemany(
                "INSERT OR REPLACE INTO ndc_dictionary "
                "(ndc_code, drug_name, strength, manufacturer, dosage_form, awp, "
                " dea_schedule, manufacturer_barcode, ndc_formatted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            ).rowcount
        conn.commit()
        log.info("NDC bulk load: %d rows loaded from %s", count, source)
        return count
    except Exception as e:
        log.error("NDC bulk load failed: %s", e)
        conn.rollback()
        return 0
    finally:
        conn.close()


def get_dictionary_stats() -> dict:
    """Return statistics about the NDC dictionary."""
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM ndc_dictionary").fetchone()[0]
        schedules = {}
        for row in conn.execute(
            "SELECT dea_schedule, COUNT(*) FROM ndc_dictionary GROUP BY dea_schedule"
        ):
            schedules[row[0]] = row[1]
        return {"total_entries": total, "by_dea_schedule": schedules, "db_path": _DB_PATH}
    except Exception:
        return {"total_entries": 0, "by_dea_schedule": {}, "db_path": _DB_PATH}
    finally:
        conn.close()


def timed_lookup(ndc_code: str) -> tuple[dict | None, float]:
    """Look up an NDC code and measure elapsed time in milliseconds."""
    start = time.perf_counter()
    result = ndc_lookup(ndc_code)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms
