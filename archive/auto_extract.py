"""
auto_extract.py — AI-Powered Document Data Extraction Scaffold.

Sends raw document text (supplier invoices, delivery notes) to a local
Ollama instance for structured parsing. Returns a list of medication dicts
with name, quantity, price, and barcode fields.

All network I/O runs in a background thread to keep the UI responsive.

Usage:
    from auto_extract import extract_from_text, extract_from_file

    # From raw text
    extract_from_text(invoice_text, on_result=handle_result, on_error=handle_error)

    # From a file path
    extract_from_file("invoice.txt", on_result=handle_result)

Configuration:
    Set OLLAMA_HOST env var or pass `base_url` to override the default
    http://localhost:11434 endpoint.
"""
import json
import os
import re
import threading
from typing import Callable, Optional

import requests


# ── Configuration ──────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
REQUEST_TIMEOUT = 60  # seconds


# ── Prompt Template ────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are a pharmaceutical inventory data extraction engine. Given the raw text
of a supplier invoice, delivery note, or packing slip, extract every medication
line item into a strict JSON array.

OUTPUT FORMAT — return ONLY a JSON array. No markdown fences, no explanation,
no conversational text. Just the raw JSON array.

REQUIRED KEYS (exactly these 6, no more, no less):
  product_name, active_ingredient, dosage_concentration,
  quantity_received, batch_number, expiration_date

EXAMPLE OUTPUT (match this exact compact format — no extra whitespace):
[{"product_name": "Amoxicillin 500mg Capsules", "active_ingredient": "Amoxicillin Trihydrate", "dosage_concentration": "500 mg capsules", "quantity_received": 100, "batch_number": "AMX-2026-X8", "expiration_date": "2028-12-01"}]

RULES:
- product_name: Use the exact product name from the document. If not found, use null.
- active_ingredient: Extract the generic/INN name. If not found, use null.
- dosage_concentration: Include both strength and form (e.g. "250mg tablets", "5ml oral drops"). If not found, use null.
- quantity_received: Integer only (no units). If unit is specified, strip it and return just the number.
- batch_number: The lot/batch number printed on the product or invoice. If not found, use null.
- expiration_date: Always in YYYY-MM-DD format. If only MM/YYYY is given, use the last day of that month. If not found, use null.
- Do NOT include price, barcode, or manufacturer fields — only the 6 keys above.
- Do NOT add markdown fences, code blocks, or any text outside the JSON array.

Document text:
---
{document_text}
---

Return ONLY the JSON array:"""


# ── Public API ─────────────────────────────────────────────────────────

def extract_from_text(
    text: str,
    on_result: Callable[[list[dict]], None],
    on_error: Optional[Callable[[Exception], None]] = None,
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
) -> threading.Thread:
    """Parse invoice text via Ollama in a background thread.

    Args:
        text: Raw document text to extract from.
        on_result: Called with list of dicts on success.
        on_error: Called with the exception on failure.
        base_url: Ollama server URL.
        model: Ollama model name.

    Returns:
        The background Thread (for optional join/daemon control).
    """
    def _worker():
        try:
            items = _call_ollama(text, base_url, model)
            on_result(items)
        except Exception as exc:
            if on_error:
                on_error(exc)

    t = threading.Thread(target=_worker, daemon=True, name="auto-extract")
    t.start()
    return t


def extract_from_file(
    file_path: str,
    on_result: Callable[[list[dict]], None],
    on_error: Optional[Callable[[Exception], None]] = None,
    encoding: str = "utf-8",
    **kwargs,
) -> threading.Thread:
    """Read a text file and extract medication data.

    Args:
        file_path: Path to the invoice/document text file.
        on_result: Called with list of dicts on success.
        on_error: Called with the exception on failure.
        encoding: File encoding (default utf-8).

    Returns:
        The background Thread.
    """
    def _worker():
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                text = f.read()
            items = _call_ollama(
                text,
                kwargs.pop("base_url", DEFAULT_OLLAMA_URL),
                kwargs.pop("model", DEFAULT_MODEL),
            )
            on_result(items)
        except Exception as exc:
            if on_error:
                on_error(exc)

    t = threading.Thread(target=_worker, daemon=True, name="auto-extract-file")
    t.start()
    return t


def extract_sync(text: str, **kwargs) -> list[dict]:
    """Synchronous extraction (blocks). Use only from background threads."""
    return _call_ollama(
        text,
        kwargs.pop("base_url", DEFAULT_OLLAMA_URL),
        kwargs.pop("model", DEFAULT_MODEL),
    )


def check_ollama_status(base_url: str = DEFAULT_OLLAMA_URL) -> dict:
    """Check if Ollama is running and which models are available.

    Returns:
        {"running": bool, "models": list[str], "error": str|None}
    """
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        data = r.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        return {"running": True, "models": models, "error": None}
    except Exception as exc:
        return {"running": False, "models": [], "error": str(exc)}


# ── Internal ───────────────────────────────────────────────────────────

def _clean_json_response(raw_text: str) -> list[dict]:
    """Clean and parse JSON from an LLM response.

    Uses regex to isolate the first JSON array, then parses it.
    Returns a list of dicts, or raises ValueError.
    """
    # Try to find the outermost JSON array in the response
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if match:
        candidate = match.group(0).strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            print(f"[auto_extract] JSON parse failed on candidate: {candidate[:200]!r}", flush=True)
            raise ValueError(f"Failed to parse JSON array: {exc}") from exc

        if isinstance(parsed, list):
            return parsed
        # Shouldn't happen since we matched [...], but guard anyway
        return [parsed] if isinstance(parsed, dict) else []

    # No array found — try parsing the whole response (single object, etc.)
    cleaned = raw_text.strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[auto_extract] JSON parse failed on raw text: {cleaned[:200]!r}", flush=True)
        raise ValueError(f"No valid JSON array found in response ({len(raw_text)} chars)") from exc

    if isinstance(parsed, dict):
        for key in ("items", "data", "results", "medications", "products"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        return [parsed]

    if isinstance(parsed, list):
        return parsed

    raise ValueError(f"Unexpected JSON top-level type: {type(parsed).__name__}")


def _call_ollama(text: str, base_url: str, model: str) -> list[dict]:
    """Send text to Ollama and parse the JSON response."""
    prompt = EXTRACTION_PROMPT.format(document_text=text[:8000])

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
        },
    }

    resp = requests.post(
        f"{base_url}/api/generate",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    response_text = resp.json().get("response", "")
    return _clean_json_response(response_text)
