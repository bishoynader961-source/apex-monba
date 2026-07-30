"""
Migration M33: Legacy Barcode Normalization

WARNING: Do NOT run this if physical labels with old barcodes have already been
applied to inventory boxes. The old barcode on the sticker will no longer match
the new barcode in the database.

Run: python migrate_data.py
"""

import re
import sqlite3
import sys
import barcode_logic
import database

VALID_BARCODE_PATTERN = re.compile(r"^[A-Z]{3}-[A-Z0-9]{6}$")


def main():
    print("=" * 60)
    print("  M33: Legacy Barcode Normalization")
    print("=" * 60)
    print()

    db_path = database.get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, internal_unique_barcode, vendor_name FROM products WHERE status = 'In Stock'")
    all_rows = cursor.fetchall()

    malformed = [r for r in all_rows if not VALID_BARCODE_PATTERN.match(r[2])]

    if not malformed:
        print("No malformed barcodes found. All barcodes match the new format.")
        conn.close()
        return

    print(f"Found {len(malformed)} malformed barcodes out of {len(all_rows)} total products.")
    print()

    old_barcode_map = {}  # old_barcode -> new_barcode

    try:
        cursor.execute("BEGIN TRANSACTION")

        for row_id, name, old_barcode, vendor_name in malformed:
            new_barcode = barcode_logic.generate_internal_barcode(vendor_name)
            cursor.execute(
                "UPDATE products SET internal_unique_barcode = ? WHERE id = ?",
                (new_barcode, row_id),
            )
            old_barcode_map[old_barcode] = new_barcode
            print(f"  [OK] id={row_id:3d}  {name:25s}  {old_barcode:35s} -> {new_barcode}")

        updated_receiving = 0
        if old_barcode_map:
            placeholders = ",".join("?" for _ in old_barcode_map)
            cursor.execute(
                f"SELECT id, barcode FROM receiving_log WHERE barcode IN ({placeholders})",
                list(old_barcode_map.keys()),
            )
            receiving_rows = cursor.fetchall()
            for recv_id, old_bc in receiving_rows:
                new_bc = old_barcode_map.get(old_bc)
                if new_bc:
                    cursor.execute(
                        "UPDATE receiving_log SET barcode = ? WHERE id = ?",
                        (new_bc, recv_id),
                    )
                    updated_receiving += 1

        conn.commit()
        print()
        print(f"Committed: {len(malformed)} products updated, {updated_receiving} receiving_log entries synced.")
        print("Migration M33 complete.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Transaction rolled back.\n{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
