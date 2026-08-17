"""
crypto_utils.py — Fernet encryption wrapper for PharmacyPro crash telemetry.

Provides payload-level encryption using Fernet (AES-128-CBC + HMAC-SHA256)
for crash report payloads sent from the desktop app to the license server.

Resolution order (first available wins):
    1. Rust extension ``rust_crypto`` (added in Phase 6; falls back automatically)
    2. ``cryptography`` library (``cryptography.fernet.Fernet``)
    3. Pure-Python Fernet via ``pycryptodome`` (``Crypto`` package)

Key derivation: PBKDF2-HMAC-SHA256 from a shared app secret + static salt,
producing a base64url-encoded 32-byte Fernet key.  Both client and server
derive the *same* key from the same secret + salt.

PyInstaller notes:
    - The ``cryptography`` wheel bundles its own OpenSSL; no extra hiddenimports
      are required beyond ``cryptography``.
    - When using the pycryptodome fallback, add ``Crypto`` to hiddenimports.

Usage:
    from crypto_utils import encrypt_payload, decrypt_payload

    token = encrypt_payload({"error_type": "ValueError", ...})
    data  = decrypt_payload(token)   # -> dict
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
import time
from typing import Any

__all__ = ["encrypt_payload", "decrypt_payload", "get_fernet_key"]

log = logging.getLogger("crypto_utils")

# ── Configuration ─────────────────────────────────────────────────────────

# Shared secret — both desktop client and Flask server must agree.
# In production this is overridden via the PHARMACYPRO_APP_SECRET env var.
APP_SECRET = os.environ.get(
    "PHARMACYPRO_APP_SECRET",
    "pharmacypro-enterprise-crash-key-v1",
)

# Static salt for key derivation (does not need to be secret, but must be stable
# across client and server for key agreement).
_APP_SALT = b"pharmacypro_crash_encryption_v1"

# PBKDF2 iterations (NIST SP 800-132 recommends ≥ 600 000 for SHA-256 as of 2023).
_PBKDF2_ITERATIONS = 480_000


# ── Key derivation ────────────────────────────────────────────────────────

def get_fernet_key() -> bytes:
    """Derive a Fernet key from the app secret via PBKDF2-HMAC-SHA256.

    Returns the key as base64url-encoded bytes (as expected by Fernet).
    """
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        APP_SECRET.encode("utf-8"),
        _APP_SALT,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(dk)


# ── Backend resolution ───────────────────────────────────────────────────

# Flag indicating which backend is active.
_BACKEND: str = "none"


class _FernetBackend:
    """Abstract interface implemented by each encryption backend."""

    def encrypt(self, data: bytes, key: bytes) -> str:
        raise NotImplementedError

    def decrypt(self, token: str, key: bytes) -> bytes:
        raise NotImplementedError


class _CryptographyBackend(_FernetBackend):
    """Primary backend — uses the ``cryptography`` library."""

    def __init__(self) -> None:
        from cryptography.fernet import Fernet
        self._Fernet = Fernet

    def encrypt(self, data: bytes, key: bytes) -> str:
        return self._Fernet(key).encrypt(data).decode("ascii")

    def decrypt(self, token: str, key: bytes) -> bytes:
        return self._Fernet(key).decrypt(token.encode("ascii"))


class _PyCryptodomeBackend(_FernetBackend):
    """Fallback backend — pure-Python Fernet using pycryptodome for AES/HMAC."""

    def __init__(self) -> None:
        from Crypto.Cipher import AES
        from Crypto.Hash import HMAC, SHA256
        from Crypto.Util.Padding import pad, unpad
        self._AES = AES
        self._HMAC = HMAC
        self._SHA256 = SHA256
        self._pad = pad
        self._unpad = unpad

    def encrypt(self, data: bytes, key: bytes) -> str:
        # Fernet key is 32 bytes base64url-encoded; decode to raw 32 bytes.
        raw_key = base64.urlsafe_b64decode(key)
        signing_key = raw_key[:16]
        encryption_key = raw_key[16:]

        # Generate a random 16-byte IV.
        iv = os.urandom(16)

        # Encrypt with AES-128-CBC + PKCS7 padding.
        cipher = self._AES.new(encryption_key, self._AES.MODE_CBC, iv)
        padded = self._pad(data, self._AES.block_size)
        ciphertext = cipher.encrypt(padded)

        # Build the token content: version(1) || timestamp(8) || IV(16) || ciphertext.
        timestamp = int(time.time()).to_bytes(8, "big")
        content = b"\x80" + timestamp + iv + ciphertext

        # HMAC-SHA256 over the content.
        h = self._HMAC.new(signing_key, digestmod=self._SHA256)
        h.update(content)
        mac = h.digest()

        token_bytes = content + mac
        return base64.urlsafe_b64encode(token_bytes).decode("ascii")

    def decrypt(self, token: str, key: bytes) -> bytes:
        raw_key = base64.urlsafe_b64decode(key)
        signing_key = raw_key[:16]
        encryption_key = raw_key[16:]

        token_bytes = base64.urlsafe_b64decode(token.encode("ascii"))
        if len(token_bytes) < 57:  # 1 + 8 + 16 + 32 (min 0 ciphertext)
            raise ValueError("Invalid token: too short")

        version = token_bytes[0]
        if version != 0x80:
            raise ValueError(f"Invalid token: version {version} != 0x80")

        timestamp = token_bytes[1:9]
        iv = token_bytes[9:25]
        mac = token_bytes[-32:]
        ciphertext = token_bytes[25:-32]

        # Verify HMAC (constant-time).
        h = self._HMAC.new(signing_key, digestmod=self._SHA256)
        h.update(b"\x80" + timestamp + iv + ciphertext)
        expected_mac = h.digest()
        if not _hmac.compare_digest(mac, expected_mac):
            raise ValueError("Invalid token: HMAC verification failed")

        # Decrypt.
        cipher = self._AES.new(encryption_key, self._AES.MODE_CBC, iv)
        padded = cipher.decrypt(ciphertext)
        data = self._unpad(padded, self._AES.block_size)
        return data


def _resolve_backend() -> _FernetBackend:
    """Pick the best available backend at import time."""
    # 1. Try Rust extension (Phase 6).
    try:
        import rust_crypto  # type: ignore[import-not-found]
        if not hasattr(rust_crypto, "encrypt_py"):
            raise ImportError("rust_crypto module missing PyO3 bindings")
        log.debug("Using rust_crypto backend")
        return _RustBackend(rust_crypto)
    except ImportError:
        pass

    # 2. Try cryptography library.
    try:
        import cryptography  # noqa: F401
        log.debug("Using cryptography backend")
        return _CryptographyBackend()
    except ImportError:
        pass

    # 3. Try pycryptodome fallback.
    try:
        import Crypto  # noqa: F401
        log.debug("Using pycryptodome fallback backend")
        return _PyCryptodomeBackend()
    except ImportError:
        pass

    raise ImportError(
        "No encryption backend available. Install one of: "
        "cryptography>=42.0, pycryptodome, or rust_crypto (.pyd)"
    )


class _RustBackend(_FernetBackend):
    """Backend that delegates to the Phase-6 Rust extension."""

    def __init__(self, module) -> None:
        self._mod = module

    def encrypt(self, data: bytes, key: bytes) -> str:
        data_str = data.decode("utf-8") if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        key_str = key.decode("ascii") if isinstance(key, bytes) else key
        return self._mod.encrypt_py(data_str, key_str)

    def decrypt(self, token: str, key: bytes) -> bytes:
        key_str = key.decode("ascii") if isinstance(key, bytes) else key
        result = self._mod.decrypt_py(token, key_str)
        return result.encode("utf-8") if isinstance(result, str) else result


# Resolve once at import.
try:
    _backend = _resolve_backend()
    _BACKEND = type(_backend).__name__.lstrip('_').replace("Backend", "").lower()
except ImportError as exc:
    _backend = None
    _BACKEND = "none"
    log.warning("crypto_utils: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────

def encrypt_payload(payload: dict | str | bytes) -> str:
    """Encrypt a payload dict (or string/bytes) and return a Fernet token string.

    Args:
        payload: A dict, string, or raw bytes to encrypt.

    Returns:
        A Fernet token string (base64url-encoded).
    """
    if _backend is None:
        raise ImportError("No encryption backend available")

    if isinstance(payload, dict):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
    else:
        raise TypeError(f"Unsupported payload type: {type(payload).__name__}")

    key = get_fernet_key()
    token = _backend.encrypt(raw, key)
    log.debug("Payload encrypted via %s backend (%d bytes -> token)", _BACKEND, len(raw))
    return token


def decrypt_payload(token: str) -> dict | str | bytes:
    """Decrypt a Fernet token and return the original payload.

    If the payload was a JSON dict, it is returned as a dict.
    Otherwise returns the decoded string or raw bytes.

    Args:
        token: A Fernet token string.

    Returns:
        The decrypted payload (dict, str, or bytes).

    Raises:
        ValueError: If the token is invalid or tampered with.
        ImportError: If no encryption backend is available.
    """
    if _backend is None:
        raise ImportError("No encryption backend available")

    key = get_fernet_key()
    raw = _backend.decrypt(token, key)

    # Try to parse as JSON dict first; fall back to string/bytes.
    try:
        text = raw.decode("utf-8")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
    except (UnicodeDecodeError, ValueError):
        return raw
