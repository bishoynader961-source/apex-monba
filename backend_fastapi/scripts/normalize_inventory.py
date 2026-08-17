"""One-shot inventory normalizer (R2 data-integrity pass).

Canonicalizes ``inventory_extended.drug_name`` to match a resolvable
``products.name`` exactly, so lot-to-product linking is deterministic.

Usage:
    python -m scripts.normalize_inventory --db pharmacy.db           # dry-run (default)
    python -m scripts.normalize_inventory --db pharmacy.db --apply   # commit changes
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Iterable


def fetch_products(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT id, name FROM products").fetchall()
    return {name: pid for pid, name in rows}


def fetch_lots(conn: sqlite3.Connection) -> list[dict[str, object]]:
    cols = "id, drug_name, ndc_code, lot_number, on_hand"
    rows = conn.execute(
        "SELECT id, drug_name, ndc_code, lot_number, on_hand FROM inventory_extended"
    ).fetchall()
    keys = ["id", "drug_name", "ndc_code", "lot_number", "on_hand"]
    return [dict(zip(keys, r)) for r in rows]


def normalize(conn: sqlite3.Connection, apply: bool) -> int:
    products = fetch_products(conn)
    lots = fetch_lots(conn)

    changes = 0
    for lot in lots:
        name = lot["drug_name"]
        if name in products:
            continue
        # Try exact case-insensitive match against known product names.
        match = next((pn for pn in products if pn.lower() == str(name).lower()), None)
        if match is None:
            print(
                f"[ORPHAN] lot_id={lot['id']} lot={lot['lot_number']} "
                f"drug_name='{name}' ndc='{lot['ndc_code']}' on_hand={lot['on_hand']} "
                "-> no resolvable product (review required)",
                file=sys.stderr,
            )
            continue
        print(f"[FIX]  lot_id={lot['id']} '{name}' -> '{match}'")
        if apply:
            conn.execute(
                "UPDATE inventory_extended SET drug_name = ? WHERE id = ?",
                (match, lot["id"]),
            )
        changes += 1

    if apply and changes:
        conn.commit()
        print(f"[COMMITTED] {changes} lot name(s) normalized.")
    elif changes:
        print(f"[DRY-RUN] {changes} lot name(s) would be normalized. Re-run with --apply to commit.")
    else:
        print("[OK] no normalization required.")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="pharmacy.db", help="Path to pharmacy SQLite DB (default: pharmacy.db)")
    ap.add_argument("--apply", action="store_true", help="Commit changes instead of dry-run")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        normalize(conn, apply=args.apply)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
