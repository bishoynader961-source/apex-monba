"""
rx_migrations.py — Schema migrations for Rx tables whose DDL lives in the LOCKED rx_db.py.

Since rx_db.py is import-only (cannot be modified), this module provides
additive migrations that are safe to run at application startup. Each migration
checks PRAGMA table_info before ALTER TABLE, making it idempotent and
backward-compatible with existing databases.

Call `run_rx_migrations(db_path)` from main_app.py during initialization.
"""
import os
import sqlite3
import logging

from path_utils import get_resource_path

log = logging.getLogger("rx_migrations")


def _get_default_db_path() -> str:
    try:
        import barcode_logic
        config = barcode_logic.load_config()
        return config.get("db_path", get_resource_path("pharmacy.db"))
    except Exception:
        return get_resource_path("pharmacy.db")


def run_rx_migrations(db_path: str = None) -> list[str]:
    """Run all Rx schema migrations. Returns list of applied migration names.

    Each migration checks for existing columns BEFORE ALTER TABLE,
    so the function is safe to call repeatedly.
    """
    if db_path is None:
        db_path = _get_default_db_path()

    applied = []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # ── Migration: inventory_extended.dea_schedule ────────────────────
        # Adds DEA Schedule (CII, CIII, CIV, CV, OTC) to each Rx inventory item.
        cursor.execute("PRAGMA table_info(inventory_extended)")
        cols = {row[1] for row in cursor.fetchall()}
        if "dea_schedule" not in cols:
            cursor.execute(
                "ALTER TABLE inventory_extended ADD COLUMN dea_schedule TEXT DEFAULT 'CIII'"
            )
            applied.append("inventory_extended.dea_schedule")
            log.info("Migration: added dea_schedule column to inventory_extended")

        # ── Migration: inventory_extended.wholesale_price ─────────────────
        if "wholesale_price" not in cols:
            cursor.execute(
                "ALTER TABLE inventory_extended ADD COLUMN wholesale_price REAL DEFAULT 0.0"
            )
            applied.append("inventory_extended.wholesale_price")
            log.info("Migration: added wholesale_price column to inventory_extended")

        # ── Migration: inventory_extended.reorder_threshold ────────────────
        if "reorder_threshold" not in cols:
            cursor.execute(
                "ALTER TABLE inventory_extended ADD COLUMN reorder_threshold INTEGER DEFAULT 0"
            )
            applied.append("inventory_extended.reorder_threshold")
            log.info("Migration: added reorder_threshold column to inventory_extended")

        conn.commit()
    except sqlite3.Error as e:
        log.error("Rx migration error: %s", e)
        conn.rollback()
    finally:
        conn.close()

    return applied


def get_inventory_extended_schema(db_path: str = None) -> list[str]:
    """Return column names for inventory_extended (used for verification)."""
    if db_path is None:
        db_path = _get_default_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(inventory_extended)")
    cols = [row[1] for row in cursor.fetchall()]
    conn.close()
    return cols


if __name__ == "__main__":
    applied = run_rx_migrations()
    print(f"Applied {len(applied)} migrations: {applied}")
