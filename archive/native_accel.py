"""
native_accel.py — Hybrid native acceleration layer for PharmacyPro.

Provides optimized fuzzy string search (via rapidfuzz, C++) and batch
UUID barcode generation (via Rust PyO3 extension), each with a pure-Python
fallback that activates automatically when the native backend is unavailable.

Resolution order (first available wins):
    Fuzzy search:  rapidfuzz (C++) → difflib.SequenceMatcher (stdlib)
    Barcode gen:   barcode_gen (Rust .pyd) → barcode_logic.generate_internal_barcode (Python)

Usage:
    from native_accel import fuzzy_search, generate_batch_barcodes

    # Fuzzy search over patient names
    results = fuzzy_search("john", ["John Smith", "Jane Doe"], limit=10, cutoff=60)

    # Batch barcode generation (1000x faster than Python uuid loop)
    barcodes = generate_batch_barcodes("MedSupply", quantity=500)
"""
from __future__ import annotations

import logging
import uuid
from difflib import SequenceMatcher
from typing import Any

log = logging.getLogger("native_accel")

# ── RapidFuzz Layer ──────────────────────────────────────────────────────────

try:
    from rapidfuzz import process as _rf_process
    from rapidfuzz import fuzz as _rf_fuzz
    from rapidfuzz.utils import default_process as _rf_default_process

    _HAS_RAPIDFUZZ: bool = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    _rf_process = None
    _rf_fuzz = None
    log.info("rapidfuzz not available; fuzzy search will use difflib fallback")

# ── Rust Barcode Layer ───────────────────────────────────────────────────────

try:
    import barcode_gen as _rg  # type: ignore[import-not-found]

    _HAS_RUST_BARCODE: bool = hasattr(_rg, "generate_barcodes")
except ImportError:
    _rg = None
    _HAS_RUST_BARCODE = False
    log.info("barcode_gen .pyd not available; barcode generation will use Python fallback")

# ── Fallback: barcode_logic ──────────────────────────────────────────────────

try:
    import barcode_logic

    _HAS_BARCODE_LOGIC: bool = True
except ImportError:
    barcode_logic = None
    _HAS_BARCODE_LOGIC = False


def _normalize_vendor(vendor_name: str) -> str:
    """Normalize a vendor name to a 3-char uppercase prefix.

    Matches barcode_logic.generate_internal_barcode() format.
    """
    if vendor_name and vendor_name.strip() and vendor_name.strip() != "N/A":
        return vendor_name.strip()[:3].upper()
    return "PRD"


# ═════════════════════════════════════════════════════════════════════════════
#  Public API — Fuzzy Search
# ═════════════════════════════════════════════════════════════════════════════


def fuzzy_search(
    query: str,
    choices: list[str] | tuple[str, ...],
    limit: int = 10,
    cutoff: float = 70.0,
    scorer: str = "wratio",
) -> list[tuple[str, float, int]]:
    """Fuzzy-search *query* against a list of *choices*.

    Returns a list of ``(choice, score, index)`` tuples, sorted by score
    descending.  Scores are 0–100 floats (higher is better).

    Args:
        query:   The search string (typos tolerated).
        choices: List of strings to search within.
        limit:   Maximum number of results.
        cutoff:  Minimum score to include (0–100).
        scorer:  rapidfuzz scorer name — ``"wratio"`` (default),
                 ``"partial"``, ``"token_sort"``, ``"token_set"``,
                 ``"tfidf"`` (if available), ``"ratio"``.

    Returns:
        ``[(choice_str, score, index), ...]`` — sorted by score desc.
        Returns empty list if no matches exceed *cutoff*.
    """
    if not query or not choices:
        return []

    if _HAS_RAPIDFUZZ and _rf_fuzz is not None:
        scorer_map = {
            "wratio": _rf_fuzz.WRatio,
            "partial": _rf_fuzz.partial_ratio,
            "token_sort": _rf_fuzz.token_sort_ratio,
            "token_set": _rf_fuzz.token_set_ratio,
            "ratio": _rf_fuzz.ratio,
        }
        if scorer in ("tfidf",):
            try:
                from rapidfuzz import Tfidf

                tfidf = Tfidf(choices, full_process=True, tokenizer=None)
                results = tfidf.search(query, limit=limit)
                return [
                    (choices[idx], round(score * 100, 2), idx)
                    for (idx, score) in results
                    if score * 100 >= cutoff
                ]
            except Exception:
                pass  # fall through to WRatio
        rf_scorer = scorer_map.get(scorer, _rf_fuzz.WRatio)
        raw = _rf_process.extract(
            query, choices, scorer=rf_scorer, processor=_rf_default_process,
            limit=limit, score_cutoff=cutoff
        )
        return [(match, round(score, 2), index) for (match, score, index) in raw]

    return _fuzzy_search_fallback(query, choices, limit, cutoff)


def _fuzzy_search_fallback(
    query: str,
    choices: list[str] | tuple[str, ...],
    limit: int = 10,
    cutoff: float = 70.0,
) -> list[tuple[str, float, int]]:
    """Pure-Python fallback using difflib.SequenceMatcher.

    Uses SequenceMatcher.ratio() which is algorithmically similar to
    rapidfuzz's fuzz.ratio (Levenshtein-based normalized similarity).
    Returns ``(choice, score, index)`` tuples sorted by score desc.
    """
    query_lower = query.lower()
    results: list[tuple[float, str, int]] = []
    for idx, choice in enumerate(choices):
        choice_lower = str(choice).lower()
        ratio = SequenceMatcher(None, query_lower, choice_lower).ratio()
        score = ratio * 100.0
        if score >= cutoff:
            results.append((score, choice, idx))
    results.sort(key=lambda x: x[0], reverse=True)
    return [(choice, round(score, 2), idx) for score, choice, idx in results[:limit]]


def fuzzy_match_one(
    query: str,
    choices: list[str] | tuple[str, ...],
    cutoff: float = 70.0,
    scorer: str = "wratio",
) -> tuple[str, float, int] | None:
    """Find the single best fuzzy match.

    Returns ``(best_match, score, index)`` or ``None`` if no match
    exceeds *cutoff*.
    """
    if not query or not choices:
        return None

    if _HAS_RAPIDFUZZ and _rf_process is not None:
        scorer_map = {
            "wratio": _rf_fuzz.WRatio,
            "partial": _rf_fuzz.partial_ratio,
            "token_sort": _rf_fuzz.token_sort_ratio,
            "token_set": _rf_fuzz.token_set_ratio,
            "ratio": _rf_fuzz.ratio,
        }
        rf_scorer = scorer_map.get(scorer, _rf_fuzz.WRatio)
        try:
            result = _rf_process.extractOne(
                query, choices, scorer=rf_scorer, processor=_rf_default_process,
                score_cutoff=cutoff
            )
            if result is not None:
                match_str, score, index = result
                return (match_str, round(score, 2), index)
        except Exception as exc:
            log.debug("rapidfuzz.extractOne failed, using fallback: %s", exc)

    results = _fuzzy_search_fallback(query, choices, limit=1, cutoff=cutoff)
    if results:
        return results[0]
    return None


def fuzzy_match_headers(
    headers: list[str],
    field_aliases: dict[str, set[str]],
) -> dict[str, str]:
    """Map CSV/Excel column headers to known database fields.

    Args:
        headers: List of raw column header strings from the data file.
        field_aliases: Dict of ``{field_name: {alias1, alias2, ...}}``.

    Returns:
        Dict of ``{header: field_name}`` for matched columns.

    Strategy:
        1. Exact normalized match (lowercase, spaces/hyphens → underscores)
        2. rapidfuzz fuzzy match (token_set_ratio) for remaining headers
        3. Substring match (longest alias first) as final fallback
    """
    if not headers or not field_aliases:
        return {}

    mapping: dict[str, str] = {}

    # --- Step 1: Exact normalized matches (fast O(1) per header) ---
    for header in headers:
        lower = header.strip().lower().replace(" ", "_").replace("-", "_")
        compact = lower.replace("_", "")
        matched = False
        for field in field_aliases:
            if lower == field:
                mapping[header] = field
                matched = True
                break
        if matched:
            continue
        for field, aliases in field_aliases.items():
            for alias in aliases:
                if lower == alias or compact == alias.replace("_", ""):
                    mapping[header] = field
                    matched = True
                    break
            if matched:
                break

    # --- Step 2: rapidfuzz fuzzy match for unmatched headers ---
    unmatched_headers = [h for h in headers if h not in mapping]
    if not unmatched_headers:
        return mapping

    if _HAS_RAPIDFUZZ and _rf_process is not None and _rf_fuzz is not None:
        try:
            all_aliases: list[str] = []
            alias_to_field: dict[str, str] = {}
            for field, aliases in field_aliases.items():
                for alias in aliases:
                    all_aliases.append(alias)
                    alias_to_field[alias] = field

            for header in unmatched_headers:
                best = _rf_process.extractOne(
                    header,
                    all_aliases,
                    scorer=_rf_fuzz.token_set_ratio,
                    processor=_rf_default_process,
                    score_cutoff=65.0,
                )
                if best is not None:
                    match_str, _score, _ = best
                    mapping[header] = alias_to_field[match_str]
        except Exception as exc:
            log.debug("rapidfuzz header matching failed, using fallback: %s", exc)

    # --- Step 3: Substring fallback for still-unmatched headers ---
    still_unmatched = [h for h in unmatched_headers if h not in mapping]
    for header in still_unmatched:
        lower = header.strip().lower().replace(" ", "_").replace("-", "_")
        compact = lower.replace("_", "")
        for field, aliases in field_aliases.items():
            for alias in sorted(aliases, key=len, reverse=True):
                if alias in lower or lower.replace("_", "") in alias.replace("_", ""):
                    mapping[header] = field
                    break
            if header in mapping:
                break

    return mapping


def _fuzzy_match_headers_fallback(
    headers: list[str],
    field_aliases: dict[str, set[str]],
) -> dict[str, str]:
    """Pure-Python fallback for header matching.

    Preserves the existing 8-pass algorithm:
    1. Exact field name match
    2. Exact alias match (normalized)
    3. Substring match (longest alias first)
    """
    column_map: dict[str, str] = {}
    for col in headers:
        lower = col.strip().lower().replace(" ", "_").replace("-", "_")
        compact = lower.replace("_", "")
        matched = False
        for field in field_aliases:
            if lower == field:
                column_map[col] = field
                matched = True
                break
        if matched:
            continue
        for field, aliases in field_aliases.items():
            for alias in aliases:
                if lower == alias or compact == alias.replace("_", ""):
                    column_map[col] = field
                    matched = True
                    break
            if matched:
                break
        if matched:
            continue
        for field, aliases in field_aliases.items():
            for alias in sorted(aliases, key=len, reverse=True):
                if alias in lower or lower.replace("_", "") in alias.replace("_", ""):
                    column_map[col] = field
                    matched = True
                    break
            if matched:
                break
    return column_map


# ═════════════════════════════════════════════════════════════════════════════
#  Public API — Batch Barcode Generation
# ═════════════════════════════════════════════════════════════════════════════


def generate_batch_barcodes(vendor_name: str, count: int) -> list[str]:
    """Generate *count* unique internal barcodes for a vendor.

    Format: ``{VENDOR[:3]}-{uuid6}`` (e.g. ``MED-A3F9B2``).
    Falls back to ``PRD-`` prefix for empty or ``N/A`` vendors.

    Uses the Rust extension (batch UUID4 with single getrandom call) when
    available.  Falls back to ``barcode_logic.generate_internal_barcode()``
    per-call when the extension is absent.

    Time complexity: O(n) where n = count.  Rust path is ~3-5x faster
    due to elimination of per-iteration Python overhead and syscall
    batching.
    """
    if count <= 0:
        return []

    if _HAS_RUST_BARCODE and _rg is not None:
        try:
            return _rg.generate_barcodes(vendor_name, count)
        except Exception as exc:
            log.warning("Rust barcode generation failed, using fallback: %s", exc)

    return _generate_batch_barcodes_fallback(vendor_name, count)


def _generate_batch_barcodes_fallback(vendor_name: str, count: int) -> list[str]:
    """Pure-Python fallback — delegates to barcode_logic.generate_internal_barcode()."""
    if _HAS_BARCODE_LOGIC and barcode_logic is not None:
        return [barcode_logic.generate_internal_barcode(vendor_name) for _ in range(count)]

    # Last-resort fallback if barcode_logic is also unavailable
    prefix = _normalize_vendor(vendor_name)
    return [f"{prefix}-{uuid.uuid4().hex[:6].upper()}" for _ in range(count)]


# ═════════════════════════════════════════════════════════════════════════════
#  Status & Diagnostics
# ═════════════════════════════════════════════════════════════════════════════


def _native_accel_loaded() -> dict[str, bool]:
    """Return a status dict indicating which native backends are active.

    Useful for logging at application startup and for diagnostics.
    """
    return {
        "rapidfuzz": _HAS_RAPIDFUZZ,
        "barcode_gen": _HAS_RUST_BARCODE,
        "python_fallback": not _HAS_RAPIDFUZZ or not _HAS_RUST_BARCODE,
    }


# Log status at import time
_status = _native_accel_loaded()
log.info(
    "native_accel loaded: rapidfuzz=%s, barcode_gen=%s, python_fallback=%s",
    _status["rapidfuzz"],
    _status["barcode_gen"],
    _status["python_fallback"],
)


__all__ = [
    "fuzzy_search",
    "fuzzy_match_one",
    "fuzzy_match_headers",
    "generate_batch_barcodes",
    "_native_accel_loaded",
    "_HAS_RAPIDFUZZ",
    "_HAS_RUST_BARCODE",
]
