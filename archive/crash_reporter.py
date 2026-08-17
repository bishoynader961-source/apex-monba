"""
crash_reporter.py — Autonomous Crash Reporter for PharmacyPro Desktop App.

Captures unhandled exceptions via sys.excepthook and POSTs a structured
telemetry payload to the Flask server, which auto-creates GitHub Issues
and runs AI analysis.

Usage (in main.py):
    from crash_reporter import install_crash_reporter
    install_crash_reporter()

The reporter is non-blocking: POST failures are silently swallowed so the
app can still exit gracefully.
"""
import hashlib
import json
import logging
import os
import platform
import socket
import sys
import threading
import traceback
import urllib.request
import uuid
from datetime import datetime, timezone

from crypto_utils import encrypt_payload
from async_ui import AsyncUI

_reporter_logger = logging.getLogger("crash_reporter")

# ── Configuration ──────────────────────────────────────────────────────
REPORT_URL = "https://inventory1app1nn.pythonanywhere.com/api/report-error"
APP_VERSION = os.environ.get("PHARMACYPRO_VERSION", "1.0.0")
ANONYMIZE_HWID = True


def _get_anonymized_hwid() -> str:
    """Return a SHA-256 hashed hardware fingerprint (never raw HWID).

    Resolution order (first available wins):
        1. Rust extension ``hw_client`` (added in Phase 6; falls back automatically)
        2. Python subprocess-based WMIC queries
    """
    try:
        import hw_client  # type: ignore[import-not-found]
        if hasattr(hw_client, "get_anonymized_hwid"):
            return hw_client.get_anonymized_hwid()
        raise ImportError("hw_client namespace package without compiled extension")
    except ImportError:
        pass

    raw = ""
    try:
        import subprocess
        # Windows: combine machine UUID + hostname + processor
        result = subprocess.run(
            ["wmic", "csproduct", "get", "uuid"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        machine_uuid = result.stdout.strip().split("\n")[-1].strip()
        hostname = socket.gethostname()
        processor = platform.processor()
        raw = f"{machine_uuid}|{hostname}|{processor}"
    except Exception:
        raw = f"{socket.gethostname()}|{platform.system()}|{platform.machine()}"

    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_os_info() -> dict:
    """Return anonymized OS environment info."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "frozen": getattr(sys, "frozen", False),
    }


def _build_error_payload(
    exc_type: type,
    exc_value: BaseException,
    exc_tb,
    license_key: str = "",
) -> dict:
    """Build the structured JSON payload for the error report."""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    tb_text = "".join(tb_lines)

    # Extract the last frame as the crash location
    crash_frame = ""
    if exc_tb:
        last = exc_tb.tb_next
        while last and last.tb_next:
            last = last.tb_next
        if last:
            f = last.tb_frame
            crash_frame = f"{f.f_code.co_filename}:{f.f_lineno} in {f.f_code.co_name}"

    return {
        "app_version": APP_VERSION,
        "error_type": exc_type.__name__ if exc_type else "Unknown",
        "error_message": str(exc_value)[:500],
        "traceback": tb_text[:4000],
        "crash_frame": crash_frame,
        "hwid_hash": _get_anonymized_hwid(),
        "os": _get_os_info(),
        "license_key": license_key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _encrypt_payload_safe(payload: dict) -> dict:
    """Encrypt a payload dict for secure transport.

    Returns a wrapper dict with ``encrypted_payload`` key on success,
    or the raw payload on encryption failure (graceful degradation).
    """
    try:
        token = encrypt_payload(payload)
        _reporter_logger.debug("Payload encrypted via Fernet (AES-128-CBC + HMAC)")
        return {"encrypted_payload": token}
    except Exception as exc:
        _reporter_logger.warning("Encryption failed, sending raw payload: %s", exc)
        return payload


def _send_report(payload: dict) -> bool:
    """Non-blocking POST of the error payload to the Flask server."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            REPORT_URL,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": f"PharmacyPro/{APP_VERSION}"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except Exception as exc:
        _reporter_logger.debug("Crash report send failed: %s", exc)
        return False


# ── License key resolver (best-effort, no imports to avoid circular) ───
_LICENSE_KEY = ""


def set_license_key(key: str):
    """Called by the license gate after successful activation."""
    global _LICENSE_KEY
    _LICENSE_KEY = key


# ── The custom excepthook ──────────────────────────────────────────────
_original_excepthook = sys.excepthook


def _crash_excepthook(exc_type, exc_value, exc_tb):
    """Global exception hook that sends crash reports."""
    payload = _build_error_payload(exc_type, exc_value, exc_tb, _LICENSE_KEY)
    _reporter_logger.error(
        "Unhandled exception: %s: %s\n%s",
        payload["error_type"],
        payload["error_message"],
        payload["traceback"],
    )

    # Encrypt payload before sending (graceful fallback to raw if encryption fails)
    send_payload = _encrypt_payload_safe(payload)

    # Non-blocking send via shared AsyncUI thread pool
    AsyncUI.get().run(_send_report, args=(send_payload,))

    # Call the original hook so the traceback still prints
    _original_excepthook(exc_type, exc_value, exc_tb)


def install_crash_reporter():
    """Install the global crash reporter hook. Call once at startup."""
    sys.excepthook = _crash_excepthook
    _reporter_logger.info("Crash reporter installed (reports to %s)", REPORT_URL)


# ── Manual report API (for try/except blocks) ─────────────────────────
def report_error(exc_type=None, exc_value=None, exc_tb=None, note=""):
    """Manually report an error (useful inside try/except blocks).

    If no exception info is provided, captures the current exception context.
    """
    if exc_type is None:
        exc_type = sys.exc_info()[0]
        exc_value = sys.exc_info()[1]
        exc_tb = sys.exc_info()[2]

    if exc_type is None:
        return False  # No active exception to report

    payload = _build_error_payload(exc_type, exc_value, exc_tb, _LICENSE_KEY)
    if note:
        payload["note"] = note[:200]

    # Encrypt payload before sending (graceful fallback to raw if encryption fails)
    send_payload = _encrypt_payload_safe(payload)

    # Non-blocking send via shared AsyncUI thread pool
    AsyncUI.get().run(_send_report, args=(send_payload,))
    return True
