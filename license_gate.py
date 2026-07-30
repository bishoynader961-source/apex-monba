"""
License Gate — Startup validation for monthly subscription enforcement.

Checks a local cache first (24-hour grace period with clock-rollback protection),
then contacts the remote server to validate the license key against a hardware
fingerprint. Blocks the main application from launching until validation passes.
"""
import customtkinter as ctk
import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

# ── Configuration ──────────────────────────────────────────────────────
LICENSE_CACHE_FILE = ".license_cache"
API_BASE_URL = "https://<YOUR_VERCEL_URL>/api"  # Phase 2 will populate this
GRACE_PERIOD_HOURS = 24
REQUEST_TIMEOUT_SECONDS = 8


def _get_device_id() -> str:
    """Hardware fingerprint: SHA-256 of machine UUID + hostname + processor."""
    raw = f"{uuid.getnode()}|{platform.node()}|{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_cache() -> dict | None:
    """Return the cached license dict, or None if absent/corrupt."""
    try:
        path = Path(LICENSE_CACHE_FILE)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_cache(data: dict) -> None:
    """Persist the license cache atomically."""
    path = Path(LICENSE_CACHE_FILE)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _is_cache_valid(cache: dict) -> bool:
    """Offline grace-period check with clock-rollback protection."""
    if cache.get("status") != "active":
        return False
    try:
        last_validated = datetime.fromisoformat(cache["last_validated"])
        now = datetime.now(timezone.utc)
        # Clock-rollback protection: current time must not be older than last check
        if now < last_validated:
            return False
        return (now - last_validated) < timedelta(hours=GRACE_PERIOD_HOURS)
    except (KeyError, ValueError):
        return False


def validate_license(license_key: str, device_id: str) -> tuple[bool, str]:
    """
    Validate a license key against the remote server.

    Returns (is_valid, message).
    Handles network timeouts gracefully by falling back to the local cache.
    """
    # 1. Check local cache first
    cache = _load_cache()
    if cache and cache.get("license_key") == license_key and _is_cache_valid(cache):
        return True, "Validated from local cache (offline mode)"

    # 2. Contact server
    if requests is None:
        return False, "Network library not available — cannot validate online"

    try:
        resp = requests.post(
            f"{API_BASE_URL}/validate",
            json={"license_key": license_key, "device_id": device_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("valid"):
                _save_cache({
                    "license_key": license_key,
                    "status": "active",
                    "device_id": device_id,
                    "last_validated": datetime.now(timezone.utc).isoformat(),
                })
                return True, "License activated successfully"
            else:
                return False, data.get("message", "License is invalid or expired")
        elif resp.status_code == 403:
            return False, "This license is bound to a different device"
        else:
            return False, f"Server error ({resp.status_code})"
    except requests.exceptions.Timeout:
        # Offline fallback: accept cache if fresh
        if cache and cache.get("license_key") == license_key:
            return True, "Offline mode — using cached validation"
        return False, "Could not reach license server — check your internet connection"
    except requests.exceptions.ConnectionError:
        if cache and cache.get("license_key") == license_key:
            return True, "Offline mode — using cached validation"
        return False, "No internet connection — cannot validate license"
    except Exception as exc:
        return False, f"Validation error: {exc}"


def activate_license(license_key: str, device_id: str) -> tuple[bool, str]:
    """
    Activate a license key on this device.

    Returns (success, message). On success the cache is written immediately.
    """
    if requests is None:
        return False, "Network library not available — cannot activate"

    try:
        resp = requests.post(
            f"{API_BASE_URL}/activate",
            json={"license_key": license_key, "device_id": device_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("activated"):
                _save_cache({
                    "license_key": license_key,
                    "status": "active",
                    "device_id": device_id,
                    "last_validated": datetime.now(timezone.utc).isoformat(),
                })
                return True, "License activated successfully"
            else:
                return False, data.get("message", "Activation failed")
        elif resp.status_code == 409:
            return False, "This license is already bound to another device"
        else:
            return False, f"Server error ({resp.status_code})"
    except requests.exceptions.Timeout:
        return False, "Could not reach license server — try again later"
    except requests.exceptions.ConnectionError:
        return False, "No internet connection — cannot activate license"
    except Exception as exc:
        return False, f"Activation error: {exc}"


# ── GUI ────────────────────────────────────────────────────────────────
class LicenseGate(ctk.CTk):
    """
    Blocking startup window that validates the license key before the
    main application is allowed to launch. Sets ``self.is_valid = True``
    on successful validation so the caller can proceed.
    """

    def __init__(self):
        super().__init__()
        self.is_valid = False
        self.device_id = _get_device_id()

        self.title("Pharmacy App — License Activation")
        self.geometry("520x340")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self._try_offline_startup()

    # ── Layout ─────────────────────────────────────────────────────────
    def _build_ui(self):
        # Title
        ctk.CTkLabel(
            self, text="Pharmacy Inventory System",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(30, 5))

        ctk.CTkLabel(
            self, text="Enter your license key to activate",
            font=ctk.CTkFont(size=13),
            text_color="#888",
        ).pack(pady=(0, 20))

        # License key entry
        self.key_entry = ctk.CTkEntry(
            self, width=340, placeholder_text="PHARM-XXXX-XXXX-XXXX",
            font=ctk.CTkFont(size=14),
        )
        self.key_entry.pack(pady=(0, 15))
        self.key_entry.bind("<Return>", lambda e: self._on_activate())

        # Status label
        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
        )
        self.status_label.pack(pady=(0, 15))

        # Activate button
        self.activate_btn = ctk.CTkButton(
            self, text="Activate & Launch", width=220, height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_activate,
        )
        self.activate_btn.pack()

    # ── Offline startup attempt ────────────────────────────────────────
    def _try_offline_startup(self):
        """If a valid cached license exists, skip the gate silently."""
        cache = _load_cache()
        if cache and _is_cache_valid(cache):
            self.is_valid = True
            self.after(200, self.destroy)

    # ── Activate handler ───────────────────────────────────────────────
    def _on_activate(self):
        key = self.key_entry.get().strip()
        if not key:
            self.status_label.configure(
                text="Please enter a license key", text_color="#f87171",
            )
            return

        self.activate_btn.configure(state="disabled", text="Activating...")
        self.status_label.configure(text="Contacting license server...", text_color="#aaa")
        self.update_idletasks()

        # Run activation in a thread to keep UI responsive
        import threading

        def _worker():
            ok, msg = activate_license(key, self.device_id)
            self.after(0, lambda: self._on_result(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_result(self, ok: bool, message: str):
        self.activate_btn.configure(state="normal", text="Activate & Launch")
        if ok:
            self.status_label.configure(text=message, text_color="#4ade80")
            self.is_valid = True
            self.after(600, self.destroy)
        else:
            self.status_label.configure(text=message, text_color="#f87171")

    def _on_close(self):
        self.is_valid = False
        self.destroy()
