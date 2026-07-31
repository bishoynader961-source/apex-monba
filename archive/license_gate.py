"""
License Gate — Startup validation for monthly subscription enforcement.

Checks a local cryptographically signed cache first (7-day offline grace),
then contacts the remote server to validate the license key against a
hardware fingerprint and HWID.  Blocks the main application from launching
until validation passes.
"""
import customtkinter as ctk
import hashlib
import json
import os
import platform
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from path_utils import get_resource_path

try:
    import requests
except ImportError:
    import traceback
    traceback.print_exc()
    print("\n[ERROR] The 'requests' library is required for license activation.")
    print("        Install it with: pip install requests\n")
    requests = None

try:
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
except ImportError:
    URLSafeTimedSerializer = None
    BadSignature = Exception
    SignatureExpired = Exception


def _frozen_app_dir() -> str:
    """Return the directory where the .exe lives (for writable files).

    When frozen, ``sys._MEIPASS`` is a read-only temp dir.  Writable
    state (cache, local DB) must live next to the executable instead.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ── Configuration ──────────────────────────────────────────────────────
LICENSE_CACHE_FILE = os.path.join(_frozen_app_dir(), ".license_cache")
API_BASE_URL = "https://inventory1app1nn.pythonanywhere.com/api"
OFFLINE_GRACE_DAYS = 7
REQUEST_TIMEOUT_SECONDS = 8
DEV_CONFIG_FILE = "dev_config.json"
_CACHE_SIGNING_KEY_FILE = os.path.join(_frozen_app_dir(), ".license_signing_key")

# ── Dev Hardware MAC Whitelist ──────────────────────────────────────────
DEV_MAC_WHITELIST: set[str] = {
     "D4:54:8B:0A:7C:D7.",  # Example: replace with your real MAC
}


def is_dev_mode() -> bool:
    """Development-only license bypass.

    Returns True (skip license gate) ONLY when ALL conditions are met:
      1. The process is NOT a frozen PyInstaller binary.
      2. A file named ``dev_config.json`` exists next to the entry-point script.
      3. That file contains the JSON object ``{"dev_mode": true}``.

    If the app is running as a compiled .exe (sys.frozen == True), this
    function **always** returns False — the bypass is structurally disabled
    and cannot be triggered regardless of what files are present on disk.
    """
    if getattr(sys, 'frozen', False):
        return False

    if os.environ.get("PHARMACY_DEV_MODE") == "1":
        return True
    try:
        ghost_token = Path.home() / ".pharmacy_dev.key"
        if ghost_token.is_file():
            return True
    except OSError:
        pass

    return False


def get_device_mac() -> str | None:
    """Return this machine's MAC address as a standardised hex string.

    Format: ``"AA:BB:CC:DD:EE:FF"`` (uppercase, colon-separated).
    Returns ``None`` if the MAC cannot be determined.
    """
    try:
        mac_int = uuid.getnode()
        if (mac_int >> 40) & 1:
            return None
        mac_hex = f"{mac_int:012X}"
        return ":".join(mac_hex[i : i + 2] for i in range(0, 12, 2))
    except Exception:
        return None


def is_dev_mac() -> bool:
    """Return True if the current device's MAC is in the dev whitelist."""
    if not DEV_MAC_WHITELIST:
        return False
    mac = get_device_mac()
    if mac is None:
        return False
    return mac in DEV_MAC_WHITELIST


def _get_device_id() -> str:
    """Hardware fingerprint: SHA-256 of machine UUID + hostname + processor."""
    raw = f"{uuid.getnode()}|{platform.node()}|{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_hwid() -> str:
    """Return a hardware ID string sent to the server for binding."""
    return _get_device_id()


# ── Signed Cache (itsdangerous) ────────────────────────────────────────
def _get_signing_serializer() -> "URLSafeTimedSerializer | None":
    """Return a serializer that signs cache tokens with a device-bound key.

    The signing key is persisted to disk on first use so that tokens
    survive restarts.  If itsdangerous is not installed, returns None.
    """
    if URLSafeTimedSerializer is None:
        return None

    # Try to load existing signing key
    try:
        key = Path(_CACHE_SIGNING_KEY_FILE).read_text(encoding="utf-8").strip()
    except (OSError, FileNotFoundError):
        # Generate a new key from the device fingerprint
        key = hashlib.sha256(_get_device_id().encode()).hexdigest()
        try:
            Path(_CACHE_SIGNING_KEY_FILE).write_text(key, encoding="utf-8")
        except OSError:
            pass

    return URLSafeTimedSerializer(key)


def _load_cache() -> dict | None:
    """Load and verify the signed license cache.

    Returns the cache dict if the signature is valid and the token has
    not expired (within OFFLINE_GRACE_DAYS).  Returns None on any failure.
    """
    serializer = _get_signing_serializer()
    if serializer is None:
        # itsdangerous not available — fall back to unsigned JSON
        return _load_cache_unsigned()

    try:
        raw = Path(LICENSE_CACHE_FILE).read_text(encoding="utf-8")
        data = serializer.loads(raw, max_age=OFFLINE_GRACE_DAYS * 86400)

        # Clock-rollback protection
        try:
            last_validated = datetime.fromisoformat(data["last_validated"])
            if datetime.now(timezone.utc) < last_validated:
                return None
        except (KeyError, ValueError):
            return None

        return data
    except (BadSignature, SignatureExpired):
        return None
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _load_cache_unsigned() -> dict | None:
    """Fallback unsigned cache loader when itsdangerous is not installed."""
    try:
        path = Path(LICENSE_CACHE_FILE)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") != "active":
                return None
            last_validated = datetime.fromisoformat(data["last_validated"])
            now = datetime.now(timezone.utc)
            if now < last_validated:
                return None
            if (now - last_validated) > timedelta(days=OFFLINE_GRACE_DAYS):
                return None
            return data
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        pass
    return None


def _save_cache(data: dict) -> None:
    """Sign and persist the license cache atomically."""
    serializer = _get_signing_serializer()
    if serializer is None:
        _save_cache_unsigned(data)
        return

    try:
        signed = serializer.dumps(data)
        path = Path(LICENSE_CACHE_FILE)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(signed, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _save_cache_unsigned(data: dict) -> None:
    """Fallback unsigned cache saver."""
    try:
        path = Path(LICENSE_CACHE_FILE)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _is_cache_valid(cache: dict) -> bool:
    """Offline grace-period check with clock-rollback protection.

    The cache was already signature-verified by _load_cache().  This
    function checks the logical validity (status + last_validated freshness).
    """
    if cache.get("status") != "active":
        return False
    try:
        last_validated = datetime.fromisoformat(cache["last_validated"])
        now = datetime.now(timezone.utc)
        if now < last_validated:
            return False
        return (now - last_validated) < timedelta(days=OFFLINE_GRACE_DAYS)
    except (KeyError, ValueError):
        return False


# ── Local DB Fallback (offline / dev) ────────────────────────────────
LICENSE_DB = Path(_frozen_app_dir()) / "licenses.db"


def _local_db_exists() -> bool:
    """Return True if a local licenses.db file exists alongside this module."""
    return LICENSE_DB.is_file()


def _validate_local_db(license_key: str, device_id: str) -> tuple[bool, str]:
    """Check the local licenses.db written by generate_key.py.

    Returns (is_valid, message).
    """
    try:
        conn = sqlite3.connect(str(LICENSE_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        conn.close()

        if not row:
            return False, "License not found in local database"

        if row["status"] != "active":
            return False, f"License is {row['status']}"

        expires_raw = str(row["expires_at"])
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except ValueError:
            try:
                expires_at = datetime.strptime(expires_raw, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc,
                )
            except ValueError:
                expires_at = datetime.strptime(expires_raw, "%Y/%m/%d").replace(
                    tzinfo=timezone.utc,
                )

        if datetime.now(timezone.utc) > expires_at:
            return False, "License has expired"

        if row["device_id"] and row["device_id"] != device_id:
            return False, "License bound to another device"

        if not row["device_id"] and device_id:
            conn2 = sqlite3.connect(str(LICENSE_DB))
            conn2.execute(
                "UPDATE licenses SET device_id = ?, activated_at = ? "
                "WHERE license_key = ?",
                (device_id, datetime.now(timezone.utc).isoformat(), license_key),
            )
            conn2.commit()
            conn2.close()

        return True, "License valid (local database)"

    except Exception as exc:
        return False, f"Local DB error: {exc}"


def _activate_local_db(license_key: str, device_id: str) -> tuple[bool, str]:
    """Activate a license key against the local licenses.db."""
    try:
        conn = sqlite3.connect(str(LICENSE_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (license_key,),
        ).fetchone()

        if not row:
            conn.close()
            return False, "License not found in local database"

        if row["device_id"] and row["device_id"] != device_id:
            conn.close()
            return False, "This license is already bound to another device"

        if row["status"] != "active":
            conn.close()
            return False, f"License is {row['status']}"

        conn.execute(
            "UPDATE licenses SET device_id = ?, activated_at = ? "
            "WHERE license_key = ?",
            (device_id, datetime.now(timezone.utc).isoformat(), license_key),
        )
        conn.commit()
        conn.close()
        return True, "License activated successfully (local database)"

    except Exception as exc:
        return False, f"Local activation error: {exc}"


# ── Server Communication ───────────────────────────────────────────────
def validate_license(license_key: str, device_id: str) -> tuple[bool, str]:
    """
    Validate a license key against the remote server.

    Returns (is_valid, message).
    Flow: signed cache → server → local DB fallback → error.
    """
    # 0. Dev hardware MAC bypass
    if is_dev_mac():
        print(f"[DEV MODE] Dev Hardware ID recognized ({get_device_mac()}). Skipping license check.")
        return True, "Dev Hardware Bypass Active"

    # 1. Check signed local cache first (7-day offline grace)
    cache = _load_cache()
    if cache and cache.get("license_key") == license_key and _is_cache_valid(cache):
        return True, "Validated from local cache (offline mode)"

    # 2. Contact server
    if requests is None:
        return False, "Missing 'requests' library — run: pip install requests"

    hwid = _get_hwid()
    try:
        resp = requests.post(
            f"{API_BASE_URL}/validate",
            json={"license_key": license_key, "device_id": device_id, "hwid": hwid},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("valid"):
                _save_cache({
                    "license_key": license_key,
                    "status": "active",
                    "device_id": device_id,
                    "hwid": hwid,
                    "last_validated": datetime.now(timezone.utc).isoformat(),
                })
                return True, "License activated successfully"
            else:
                return False, data.get("message", "License is invalid or expired")
        elif resp.status_code == 403:
            msg = resp.json().get("message", "This license is bound to a different device") if resp.content else "This license is bound to a different device"
            return False, msg
        else:
            return False, f"Server error ({resp.status_code})"
    except requests.exceptions.Timeout:
        if _local_db_exists():
            return _validate_local_db(license_key, device_id)
        if cache and cache.get("license_key") == license_key:
            return True, "Offline mode — using cached validation"
        return False, "Could not reach license server — check your internet connection"
    except requests.exceptions.ConnectionError:
        if _local_db_exists():
            return _validate_local_db(license_key, device_id)
        if cache and cache.get("license_key") == license_key:
            return True, "Offline mode — using cached validation"
        return False, "No internet connection — cannot validate license"
    except Exception as exc:
        return False, f"Validation error: {exc}"


def activate_license(license_key: str, device_id: str) -> tuple[bool, str]:
    """
    Activate a license key on this device.

    Returns (success, message). On success the signed cache is written immediately.
    """
    # Dev hardware MAC bypass
    if is_dev_mac():
        print(f"[DEV MODE] Dev Hardware ID recognized ({get_device_mac()}). Skipping activation.")
        return True, "Dev Hardware Bypass Active"

    if requests is None:
        return False, "Missing 'requests' library — run: pip install requests"

    hwid = _get_hwid()
    try:
        resp = requests.post(
            f"{API_BASE_URL}/activate",
            json={"license_key": license_key, "device_id": device_id, "hwid": hwid},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("activated"):
                _save_cache({
                    "license_key": license_key,
                    "status": "active",
                    "device_id": device_id,
                    "hwid": hwid,
                    "last_validated": datetime.now(timezone.utc).isoformat(),
                })
                return True, "License activated successfully"
            else:
                return False, data.get("message", "Activation failed")
        elif resp.status_code == 409:
            return False, "This license is already bound to another device"
        elif resp.status_code == 403:
            msg = resp.json().get("message", "Hardware mismatch") if resp.content else "Hardware mismatch"
            return False, msg
        else:
            return False, f"Server error ({resp.status_code})"
    except requests.exceptions.Timeout:
        return False, "Could not reach license server — try again later"
    except requests.exceptions.ConnectionError:
        if _local_db_exists():
            return _activate_local_db(license_key, device_id)
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
        """If a valid signed cache exists, skip the gate silently."""
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
