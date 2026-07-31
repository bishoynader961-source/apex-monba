"""
test_ai_pipeline.py — Standalone test for AI invoice parsing pipeline.

Verifies:
  1. Ollama connectivity
  2. AI extraction of pharmaceutical invoice text
  3. Output schema validation (6-key JSON array)
  4. Execution timing

Usage:
    python archive/test_ai_pipeline.py
"""
import sys
import time
import json
import textwrap

sys.path.insert(0, __import__("os").path.dirname(__file__))

from auto_extract import check_ollama_status, extract_sync


# ── Mock Invoice Data ──────────────────────────────────────────────────

MOCK_INVOICE = """\
INVOICE #99824
Supplier: Apex Medical & Dental Wholesalers
Date: 2026-07-31

Items Received:
1. Amoxicillin 500mg Capsules
   Active Ingredient: Amoxicillin Trihydrate
   Dosage: 500 mg
   Qty: 100 boxes
   Batch: AMX-2026-X8
   Expiry: 2028-12-01

2. Lidocaine HCl 2% with Epinephrine 1:100,000
   Active Ingredient: Lidocaine Hydrochloride / Epinephrine
   Dosage: 20 mg/mL
   Qty: 50 cartridge boxes
   Batch: LIDO-88A-2026
   Expiry: 2027-06-15

3. Paracetamol Extra 500/65mg
   Active Ingredient: Paracetamol / Caffeine
   Dosage: 500mg + 65mg
   Qty: 250 packs
   Batch: PCM-40912
   Expiry: 2029-01-30

4. Metformin HCl 850mg Tablets
   Active Ingredient: Metformin Hydrochloride
   Dosage: 850 mg film-coated tablets
   Qty: 200 bottles
   Batch: MET-7712-Q
   Expiry: 2028-03-15
"""

REQUIRED_KEYS = [
    "product_name",
    "active_ingredient",
    "dosage_concentration",
    "quantity_received",
    "batch_number",
    "expiration_date",
]


# ── Validation ─────────────────────────────────────────────────────────

def validate_item(item: dict, index: int) -> list[str]:
    """Validate a single extracted item against the schema."""
    errors = []
    missing = set(REQUIRED_KEYS) - set(item.keys())
    if missing:
        errors.append(f"  Item {index}: missing keys {missing}")

    if not item.get("product_name"):
        errors.append(f"  Item {index}: product_name is null/empty")
    if item.get("quantity_received") is None:
        errors.append(f"  Item {index}: quantity_received is null")
    elif not isinstance(item["quantity_received"], (int, float)):
        errors.append(f"  Item {index}: quantity_received is not numeric ({type(item['quantity_received']).__name__})")

    return errors


def run_test():
    print("=" * 60)
    print("  AI Invoice Pipeline Test")
    print("=" * 60)

    # Step 1: Check Ollama
    print("\n[1] Checking Ollama connectivity...")
    status = check_ollama_status()
    if not status["running"]:
        print(f"  FAIL: Ollama not reachable — {status['error']}")
        print("  Start Ollama and re-run: python archive/test_ai_pipeline.py")
        return False
    print(f"  OK: Ollama running — models: {', '.join(status['models']) or '(none listed)'}")

    # Step 2: Extract
    print("\n[2] Sending mock invoice to AI model...")
    print(f"  Input: {len(MOCK_INVOICE)} chars, 4 pharmaceutical items")
    t0 = time.monotonic()
    try:
        items = extract_sync(MOCK_INVOICE)
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False
    elapsed = time.monotonic() - t0

    # Step 3: Print raw response
    print(f"\n[3] Raw response ({elapsed:.2f}s):")
    print(textwrap.indent(json.dumps(items, indent=2), "  "))

    # Step 3.5: Print parsed objects for debugging
    print(f"\n[3.5] Parsed JSON objects ({len(items)} items):")
    for i, item in enumerate(items, 1):
        print(f"  Item {i}: {json.dumps(item, indent=4)}")

    # Step 4: Validate schema
    print(f"\n[4] Schema validation:")
    print(f"  Items returned: {len(items)}")
    all_errors = []
    for i, item in enumerate(items, 1):
        all_errors.extend(validate_item(item, i))

    if all_errors:
        print("  ERRORS:")
        for e in all_errors:
            print(e)
        return False
    else:
        print("  ALL ITEMS VALID — 6-key schema matches.")

    # Step 5: Summary
    print(f"\n[5] Summary:")
    print(f"  Execution time: {elapsed:.2f}s")
    print(f"  Items extracted: {len(items)}")
    for i, item in enumerate(items, 1):
        name = item.get("product_name", "?")
        qty = item.get("quantity_received", "?")
        batch = item.get("batch_number", "?")
        print(f"    {i}. {name} — qty={qty}, batch={batch}")

    print("\n" + "=" * 60)
    print("  RESULT: PASS" if not all_errors else "  RESULT: FAIL")
    print("=" * 60)
    return not all_errors


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
