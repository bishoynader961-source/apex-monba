"""
smart_parser.py — Offline Pharmaceutical Invoice Data Extraction.

Pure-Python regex + heuristic parser. Zero AI, zero internet.
Parses messy supplier invoices into a strict 6-key JSON schema.

Usage:
    from smart_parser import parse_invoice, parse_invoice_file

    items = parse_invoice(raw_text)
    items = parse_invoice_file("invoice.txt")

Schema per item:
    product_name, active_ingredient, dosage_concentration,
    quantity_received, batch_number, expiration_date
"""
import json
import os
import re
from datetime import date, datetime
from typing import Optional


# ── Regex Building Blocks ──────────────────────────────────────────────

# Quantity: "qty: 100 boxes", "quantity 250", "received: 50 packs", "200 units"
_RE_QTY = re.compile(
    r"(?:qty|quantity|received|units?|packs?|boxes?|bottles?|cartons?|tabs?|tablets?|capsules?)"
    r"\s*[:=\-]?\s*(\d{1,6})",
    re.IGNORECASE,
)
# Fallback: standalone number preceded by a dash or colon on the line
_RE_QTY_FALLBACK = re.compile(r"[:\-]\s*(\d{1,6})\b")

# Batch/Lot: "batch: AMX-2026-X8", "lot #LIDO-88A", "batch no. PCM-40912"
_RE_BATCH = re.compile(
    r"(?:batch|lot|b\/n|b\.n\.)"
    r"(?:\s+(?:no|number|#)\.?)?"
    r"\s*[:#\-=]?\s*([A-Za-z0-9][\w\-\.]{2,30})",
    re.IGNORECASE,
)

# Expiration / Expiry: "exp: 2028-12-01", "expiry 12/2028", "exp. 01/12/2028"
_RE_EXPIRY = re.compile(
    r"(?:exp(?:iry|iration)?|valid\s*until|use\s*by|shelf\s*life)"
    r"\s*[:=\-]?\s*(\d{1,4}[\-/\.]\d{1,2}[\-/\.]?\d{0,4})",
    re.IGNORECASE,
)
# Date-only patterns (no keyword required) as last resort
_RE_DATE_STANDALONE = re.compile(
    r"\b(20\d{2}[\-/\.](?:0?[1-9]|1[0-2])[\-/\.](?:0?[1-9]|[12]\d|3[01]))\b"
)
_RE_DATE_MMYYYY = re.compile(
    r"\b((?:0?[1-9]|1[0-2])[\-/\.](?:20\d{2}))\b"
)

# Dosage/concentration: "500mg capsules", "10mg/ml syrup", "2% ointment", "500mg + 65mg"
_RE_DOSAGE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)"
    r"(?:\s*[+/]\s*\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))?"
    r"(?:\s*/\s*\d+(?:\.\d+)?\s*(?:ml|mL|g|dose))?"
    r"(?:\s+(?:capsules?|tablets?|syrup|drops?|cream|ointment|gel|injection|solution|suspension|ampoules?|vials?|patches?|inhaler))?)\b",
    re.IGNORECASE,
)
# Alternate format: "500/65mg" (slash-separated strengths)
_RE_DOSAGE_SLASH = re.compile(
    r"\b(\d+(?:\.\d+)?/\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))\b",
    re.IGNORECASE,
)
# Broader dosage fallback: "850 mg film-coated tablets"
_RE_DOSAGE_FALLBACK = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)\b"
    r"(?:[\s\-]+(?:film[- ]?coated|enteric[- ]?coated|extended[- ]?release|slow[- ]?release)?"
    r"\s*(?:capsules?|tablets?|syrup|drops?|cream|ointment|gel|injection|solution|suspension))?)",
    re.IGNORECASE,
)

# Active ingredient: "Active Ingredient: Amoxicillin Trihydrate"
_RE_INGREDIENT = re.compile(
    r"(?:active\s*(?:ingredient|substance|pharmaceutical|component)"
    r"|ingredient|generic\s*(?:name|drug)?|INN|API)"
    r"\s*[:=\-]?\s*(.+)",
    re.IGNORECASE,
)

# Product name indicators
_RE_PRODUCT_LABEL = re.compile(
    r"(?:product\s*(?:name)?|drug\s*(?:name)?|item\s*(?:name|description)?"
    r"|medication|medicine|pharmaceutical|description)\s*[:=\-]?\s*(.+)",
    re.IGNORECASE,
)

# Numbered list prefix: "1.", "1)", "1 -", etc.
_RE_LIST_PREFIX = re.compile(r"^\s*\d{1,3}\s*[\.\)\-]\s*")

# Noise lines to skip
_NOISE_PATTERNS = re.compile(
    r"(?:invoice|bill|receipt|packing\s*slip|delivery\s*note|supplier|date|total|"
    r"subtotal|tax|vat|amount|paid|payment|terms|conditions|address|phone|fax|"
    r"email|website|order\s*(?:no|number|#)|po\s*(?:no|number|#)|ref\s*(?:no|#)?)",
    re.IGNORECASE,
)


# ── Normalization Helpers ──────────────────────────────────────────────

def _normalize_date(raw: str) -> str:
    """Normalize any date string to YYYY-MM-DD."""
    raw = raw.strip().replace(".", "/").replace("-", "/")
    # YYYY/MM/DD or YYYY-MM-DD or YYYY.MM.DD
    m = re.match(r"(20\d{2})/(\d{1,2})/(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD/MM/YYYY or MM/DD/YYYY — assume DD/MM/YYYY (pharmaceutical standard)
    m = re.match(r"(\d{1,2})/(\d{1,2})/(20\d{2})", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
        # Might be MM/DD/YYYY
        if 1 <= d <= 12 and 1 <= mo <= 31:
            return f"{y}-{d:02d}-{mo:02d}"
    # MM/YYYY
    m = re.match(r"(\d{1,2})/(20\d{2})", raw)
    if m:
        mo, y = int(m.group(1)), m.group(2)
        if 1 <= mo <= 12:
            if mo == 12:
                last_day = 31
            else:
                last_day = (date(int(y), mo + 1, 1).toordinal()
                            - date(int(y), mo, 1).toordinal())
            return f"{y}-{mo:02d}-{last_day:02d}"
    return raw.replace("/", "-")


def _extract_quantity(line: str) -> Optional[int]:
    """Pull a quantity from a line."""
    m = _RE_QTY.search(line)
    if m:
        return int(m.group(1))
    # If the line has a list prefix and a bare number, try it
    m = _RE_QTY_FALLBACK.search(line)
    if m:
        val = int(m.group(1))
        if val < 100000:  # sanity check
            return val
    return None


def _extract_batch(line: str) -> Optional[str]:
    """Pull batch/lot number from a line."""
    m = _RE_BATCH.search(line)
    if m:
        return m.group(1).strip().rstrip(".")
    return None


def _extract_expiry(line: str) -> Optional[str]:
    """Pull expiration date from a line."""
    m = _RE_EXPIRY.search(line)
    if m:
        return _normalize_date(m.group(1))
    return None


def _extract_dosage(line: str) -> Optional[str]:
    """Pull dosage/concentration from a line.

    Prefers the widest match (e.g. "500mg + 65mg" over just "65mg").
    """
    # Collect all dosage-like matches, return the longest
    candidates = []
    for m in _RE_DOSAGE.finditer(line):
        candidates.append(m.group(1).strip())
    for m in _RE_DOSAGE_SLASH.finditer(line):
        candidates.append(m.group(1).strip())
    for m in _RE_DOSAGE_FALLBACK.finditer(line):
        candidates.append(m.group(1).strip())
    if candidates:
        return max(candidates, key=len)
    # Last resort: find any "NNmg" combo
    m = re.search(
        r"(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)"
        r"(?:\s*[+/]\s*\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))*)",
        line, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_ingredient(line: str) -> Optional[str]:
    """Pull active ingredient from a line."""
    m = _RE_INGREDIENT.search(line)
    if m:
        val = m.group(1).strip().rstrip(".")
        # Clean up trailing noise
        val = re.split(r"\s{2,}|\t", val)[0].strip()
        if len(val) > 3:
            return val
    return None


def _extract_product_name(line: str) -> Optional[str]:
    """Pull product name from a line."""
    m = _RE_PRODUCT_LABEL.search(line)
    if m:
        val = m.group(1).strip().rstrip(".")
        val = re.split(r"\s{2,}|\t", val)[0].strip()
        if len(val) > 2:
            return val
    return None


def _is_noise_line(line: str) -> bool:
    """Check if a line is header/footer noise."""
    stripped = line.strip()
    if len(stripped) < 3:
        return True
    # Lines that are purely punctuation or numbers
    if re.match(r"^[\d\s\.\-\/\:]+$", stripped):
        return True
    # Check if it's a known header/footer keyword with nothing else useful
    if _NOISE_PATTERNS.match(stripped) and len(stripped) < 40:
        return True
    return False


def _clean_product_name(raw: str) -> str:
    """Clean up a product name extracted from a line."""
    # Remove list prefix
    raw = _RE_LIST_PREFIX.sub("", raw)
    # Remove common suffixes that aren't part of the name
    raw = re.sub(r"\s*[-–—]\s*(?:qty|quantity|batch|lot|exp|price|cost).*$", "", raw, flags=re.IGNORECASE)
    # Remove trailing numbers that look like quantities
    raw = re.sub(r"\s+\d{1,5}\s*$", "", raw)
    return raw.strip().rstrip(":")


# ── Core Parser ────────────────────────────────────────────────────────

def _parse_block(lines: list[str]) -> Optional[dict]:
    """Parse a single medication block (one item) into the 6-key schema."""
    if not lines:
        return None

    # Flatten for field extraction
    full_text = "\n".join(lines)
    first_line = lines[0].strip()

    # Extract fields (order matters — most specific first)
    batch = _extract_batch(full_text)
    expiry = _extract_expiry(full_text)
    dosage = _extract_dosage(full_text)
    ingredient = _extract_ingredient(full_text)
    qty = _extract_quantity(full_text)

    # Product name: try explicit label first, then first line
    product_name = _extract_product_name(full_text)
    if not product_name:
        # Use first line as product name (common invoice format)
        candidate = _clean_product_name(first_line)
        # Skip if it looks like a header/noise
        if candidate and not _is_noise_line(candidate) and len(candidate) > 2:
            product_name = candidate

    # If we still don't have a product name, try second line
    if not product_name and len(lines) > 1:
        candidate = _clean_product_name(lines[1].strip())
        if candidate and not _is_noise_line(candidate) and len(candidate) > 2:
            product_name = candidate

    # Must have at least a product name or quantity to be valid
    if not product_name and qty is None:
        return None

    return {
        "product_name": product_name or "Unknown Product",
        "active_ingredient": ingredient or "Not specified",
        "dosage_concentration": dosage or "Not specified",
        "quantity_received": qty if qty is not None else 0,
        "batch_number": batch or "N/A",
        "expiration_date": expiry or "N/A",
    }


def parse_invoice(text: str) -> list[dict]:
    """Parse raw invoice text into structured medication data.

    Splits text into item blocks using blank-line separation and
    numbered-list detection, then extracts the 6-key schema from each.

    Returns:
        List of dicts, each with the 6 required keys.
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue

        # Detect start of a new item block:
        # 1. Numbered list prefix (1. 2. 3. etc.)
        # 2. Unindented line that looks like a product name (not a header/noise)
        is_new_item = False

        if re.match(r"^\d{1,3}\s*[\.\)\-]\s+\S", stripped):
            is_new_item = True
        elif not line.startswith(" ") and not line.startswith("\t"):
            # Unindented line — skip known headers/noise and sub-field keywords
            if not re.match(
                r"^(?:active\s*(?:ingredient|substance)|ingredient|generic\s*name|"
                r"dosage|qty|quantity|batch|lot|exp|expiry|expiration|"
                r"price|cost|total|subtotal|tax|vat|amount|product\s*name|"
                r"drug\s*name|item\s*name|description|units?|received|"
                r"invoice|bill|receipt|packing\s*slip|delivery\s*note|"
                r"supplier|date|order|po\s|ref\s|terms|conditions|"
                r"address|phone|fax|email|website|ship(?:ment|ped)|"
                r"from|to|bill\s*to|ship\s*to|payment|items?\s*received)\s*[:=\-]",
                stripped, re.IGNORECASE
            ):
                is_new_item = True

        if is_new_item:
            if current_block:
                blocks.append(current_block)
            current_block = [stripped]
        else:
            current_block.append(stripped)

    if current_block:
        blocks.append(current_block)

    # Parse each block
    items: list[dict] = []
    for block in blocks:
        # Skip blocks that are clearly just headers/noise (no sub-fields)
        block_text = " ".join(block).lower()
        has_field = any(
            kw in block_text
            for kw in ("qty", "quantity", "batch", "lot", "exp", "dosage",
                       "active", "ingredient", "mg", "ml", "tablets", "caps")
        )
        # Must have at least one field indicator or be a numbered list item
        if not has_field and not re.match(r"^\d{1,3}\s*[\.\)\-]", block[0]):
            continue

        parsed = _parse_block(block)
        if parsed:
            # Deduplicate: skip if we already have the same product+batch
            key = (parsed["product_name"], parsed["batch_number"])
            if not any(
                (it["product_name"], it["batch_number"]) == key
                for it in items
            ):
                items.append(parsed)

    return items


def parse_invoice_file(file_path: str, encoding: str = "utf-8") -> list[dict]:
    """Read a text file and parse it."""
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        return parse_invoice(f.read())


# ── Standalone Tests ───────────────────────────────────────────────────

_INVOICE_1 = """\
INVOICE #99824
Supplier: Apex Medical & Dental Wholesalers
Date: 2026-07-31

Items Received:
1. Amoxicillin 500mg Capsules
   Active Ingredient: Amoxicillin Trihydrate
   Dosage: 500 mg capsules
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

_INVOICE_2 = """\
PACKING SLIP - MedSupply Co.
Order #PO-4421

Ibuprofen 400mg Tablets
  active ingredient: Ibuprofen
  qty 120
  batch: IBU-99Z
  exp: 12/2027

Paracetamol 500mg
  ingredient: Acetaminophen
  qty: 300 tabs
  lot: PAC-2025-A1
  expiry: 01/2029
"""

_INVOICE_3 = """\
Delivery Note
============
1) Amoxicillin suspension 250mg/5ml - qty 50, batch AMX-S-44, exp 2028-06-30
2) Cetirizine 10mg tablets - qty 200, lot CTZ-11, expiry 06/2027
3) Omeprazole 20mg capsules - qty 100, batch OME-77-B, exp 2029-12-01
"""

_INVOICE_4 = """\
 supplier: global pharma ltd
 product: azithromycin 500mg tablets
 active ingredient: azithromycin dihydrate
 dosage: 500 mg
 quantity: 80 boxes
 batch no. AZT-2026-33
 expiration date: 15/08/2028

 product: ciprofloxacin 500mg
 generic name: ciprofloxacin HCl
 500mg tablets
 qty 60
 lot #CIP-88
 exp 2027/11/30
"""


def _run_tests():
    """Run inline verification tests."""
    print("=" * 65)
    print("  smart_parser.py — Offline Invoice Extraction Tests")
    print("=" * 65)

    tests = [
        ("Invoice #1 (standard 4-item)", _INVOICE_1, 4),
        ("Invoice #2 (minimal 2-item)", _INVOICE_2, 2),
        ("Invoice #3 (compact list)", _INVOICE_3, 3),
        ("Invoice #4 (mixed formats)", _INVOICE_4, 2),
    ]

    required_keys = [
        "product_name", "active_ingredient", "dosage_concentration",
        "quantity_received", "batch_number", "expiration_date",
    ]

    all_pass = True

    for name, raw, expected_count in tests:
        print(f"\n--- {name} ---")
        items = parse_invoice(raw)
        print(f"  Expected {expected_count} items, got {len(items)}")

        if len(items) != expected_count:
            print(f"  FAIL: count mismatch")
            all_pass = False
            continue

        for i, item in enumerate(items, 1):
            # Verify schema
            missing = [k for k in required_keys if k not in item]
            if missing:
                print(f"  FAIL: item {i} missing keys {missing}")
                all_pass = False
                continue

            name_str = item["product_name"][:35]
            ing = item["active_ingredient"][:20]
            dos = item["dosage_concentration"][:20]
            qty = item["quantity_received"]
            bat = item["batch_number"]
            exp = item["expiration_date"]
            print(f"  {i}. {name_str:<36} | {ing:<21} | {dos:<21} | qty={qty:<5} | {bat:<16} | {exp}")

        print(f"  PASS")

    print("\n" + "=" * 65)
    if all_pass:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
    print("=" * 65)
    return all_pass


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_tests() else 1)
