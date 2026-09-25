"""Offline pharmaceutical invoice data extraction.

Pure-Python regex + heuristic parser. Zero AI, zero internet.
Parses messy supplier invoices into a strict 6-key JSON schema.

Adapted from the legacy app's smart_parser.py for the FastAPI backend.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional


# ── Regex Building Blocks ──────────────────────────────────────────────

_RE_QTY = re.compile(
    r"(?:qty|quantity|received|units?|packs?|boxes?|bottles?|cartons?|tabs?|tablets?|capsules?)"
    r"\s*[:=\-]?\s*(\d{1,6})",
    re.IGNORECASE,
)
_RE_QTY_FALLBACK = re.compile(r"[:\-]\s*(\d{1,6})\b")

_RE_BATCH = re.compile(
    r"(?:batch|lot|b\/n|b\.n\.)"
    r"(?:\s+(?:no|number|#)\.?)?"
    r"\s*[:#\-=]?\s*([A-Za-z0-9][\w\-\.]{2,30})",
    re.IGNORECASE,
)

_RE_EXPIRY = re.compile(
    r"(?:exp(?:iry|iration)?|valid\s*until|use\s*by|shelf\s*life)"
    r"\s*[:=\-]?\s*(\d{1,4}[\-/\.]\d{1,2}[\-/\.]?\d{0,4})",
    re.IGNORECASE,
)

_RE_DOSAGE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)"
    r"(?:\s*[+/]\s*\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))?"
    r"(?:\s*/\s*\d+(?:\.\d+)?\s*(?:ml|mL|g|dose))?"
    r"(?:\s+(?:capsules?|tablets?|syrup|drops?|cream|ointment|gel|injection|solution|suspension|ampoules?|vials?|patches?|inhaler))?)\b",
    re.IGNORECASE,
)
_RE_DOSAGE_SLASH = re.compile(
    r"\b(\d+(?:\.\d+)?/\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))\b",
    re.IGNORECASE,
)
_RE_DOSAGE_FALLBACK = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)\b"
    r"(?:[\s\-]+(?:film[- ]?coated|enteric[- ]?coated|extended[- ]?release|slow[- ]?release)?"
    r"\s*(?:capsules?|tablets?|syrup|drops?|cream|ointment|gel|injection|solution|suspension))?)",
    re.IGNORECASE,
)

_RE_INGREDIENT = re.compile(
    r"(?:active\s*(?:ingredient|substance|pharmaceutical|component)"
    r"|ingredient|generic\s*(?:name|drug)?|INN|API)"
    r"\s*[:=\-]?\s*(.+)",
    re.IGNORECASE,
)

_RE_PRODUCT_LABEL = re.compile(
    r"(?:product\s*(?:name)?|drug\s*(?:name)?|item\s*(?:name|description)?"
    r"|medication|medicine|pharmaceutical|description)\s*[:=\-]?\s*(.+)",
    re.IGNORECASE,
)

_RE_LIST_PREFIX = re.compile(r"^\s*\d{1,3}\s*[\.\)\-]\s*")

_NOISE_PATTERNS = re.compile(
    r"(?:invoice|bill|receipt|packing\s*slip|delivery\s*note|supplier|date|total|"
    r"subtotal|tax|vat|amount|paid|payment|terms|conditions|address|phone|fax|"
    r"email|website|order\s*(?:no|number|#)|po\s*(?:no|number|#)|ref\s*(?:no|#)?)",
    re.IGNORECASE,
)


# ── Normalization Helpers ──────────────────────────────────────────────

def _normalize_date(raw: str) -> str:
    raw = raw.strip().replace(".", "/").replace("-", "/")
    m = re.match(r"(20\d{2})/(\d{1,2})/(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(20\d{2})", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
        if 1 <= d <= 12 and 1 <= mo <= 31:
            return f"{y}-{d:02d}-{mo:02d}"
    m = re.match(r"(\d{1,2})/(20\d{2})", raw)
    if m:
        mo, y = int(m.group(1)), m.group(2)
        if 1 <= mo <= 12:
            last_day = 31 if mo == 12 else (date(int(y), mo + 1, 1).toordinal() - date(int(y), mo, 1).toordinal())
            return f"{y}-{mo:02d}-{last_day:02d}"
    return raw.replace("/", "-")


def _extract_quantity(line: str) -> Optional[int]:
    m = _RE_QTY.search(line)
    if m:
        return int(m.group(1))
    m = _RE_QTY_FALLBACK.search(line)
    if m:
        val = int(m.group(1))
        if val < 100000:
            return val
    return None


def _extract_batch(line: str) -> Optional[str]:
    m = _RE_BATCH.search(line)
    if m:
        return m.group(1).strip().rstrip(".")
    return None


def _extract_expiry(line: str) -> Optional[str]:
    m = _RE_EXPIRY.search(line)
    if m:
        return _normalize_date(m.group(1))
    return None


def _extract_dosage(line: str) -> Optional[str]:
    candidates = []
    for m in _RE_DOSAGE.finditer(line):
        candidates.append(m.group(1).strip())
    for m in _RE_DOSAGE_SLASH.finditer(line):
        candidates.append(m.group(1).strip())
    for m in _RE_DOSAGE_FALLBACK.finditer(line):
        candidates.append(m.group(1).strip())
    if candidates:
        return max(candidates, key=len)
    m = re.search(
        r"(\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU)"
        r"(?:\s*[+/]\s*\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|mcg|µg|%|iu|IU))*)",
        line, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_ingredient(line: str) -> Optional[str]:
    m = _RE_INGREDIENT.search(line)
    if m:
        val = m.group(1).strip().rstrip(".")
        val = re.split(r"\s{2,}|\t", val)[0].strip()
        if len(val) > 3:
            return val
    return None


def _extract_product_name(line: str) -> Optional[str]:
    m = _RE_PRODUCT_LABEL.search(line)
    if m:
        val = m.group(1).strip().rstrip(".")
        val = re.split(r"\s{2,}|\t", val)[0].strip()
        if len(val) > 2:
            return val
    return None


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3:
        return True
    if re.match(r"^[\d\s\.\-\/\:]+$", stripped):
        return True
    if _NOISE_PATTERNS.match(stripped) and len(stripped) < 40:
        return True
    return False


def _clean_product_name(raw: str) -> str:
    raw = _RE_LIST_PREFIX.sub("", raw)
    raw = re.sub(r"\s*[-–—]\s*(?:qty|quantity|batch|lot|exp|price|cost).*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s+\d{1,5}\s*$", "", raw)
    return raw.strip().rstrip(":")


# ── Core Parser ────────────────────────────────────────────────────────

def _parse_block(lines: list[str]) -> Optional[dict]:
    if not lines:
        return None
    full_text = "\n".join(lines)
    first_line = lines[0].strip()

    batch = _extract_batch(full_text)
    expiry = _extract_expiry(full_text)
    dosage = _extract_dosage(full_text)
    ingredient = _extract_ingredient(full_text)
    qty = _extract_quantity(full_text)

    product_name = _extract_product_name(full_text)
    if not product_name:
        candidate = _clean_product_name(first_line)
        if candidate and not _is_noise_line(candidate) and len(candidate) > 2:
            product_name = candidate
    if not product_name and len(lines) > 1:
        candidate = _clean_product_name(lines[1].strip())
        if candidate and not _is_noise_line(candidate) and len(candidate) > 2:
            product_name = candidate

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

    Returns list of dicts, each with: product_name, active_ingredient,
    dosage_concentration, quantity_received, batch_number, expiration_date.
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

        is_new_item = False
        if re.match(r"^\d{1,3}\s*[\.\)\-]\s+\S", stripped):
            is_new_item = True
        elif not line.startswith(" ") and not line.startswith("\t"):
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

    items: list[dict] = []
    for block in blocks:
        block_text = " ".join(block).lower()
        has_field = any(
            kw in block_text
            for kw in ("qty", "quantity", "batch", "lot", "exp", "dosage",
                       "active", "ingredient", "mg", "ml", "tablets", "caps")
        )
        if not has_field and not re.match(r"^\d{1,3}\s*[\.\)\-]", block[0]):
            continue

        parsed = _parse_block(block)
        if parsed:
            key = (parsed["product_name"], parsed["batch_number"])
            if not any((it["product_name"], it["batch_number"]) == key for it in items):
                items.append(parsed)

    return items
