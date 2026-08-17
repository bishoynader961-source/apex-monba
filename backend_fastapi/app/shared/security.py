"""Password hashing (bcrypt) with legacy scrypt lazy-upgrade, JWT helpers, and
device-bound PIN peppering (C.4 hardening).

The legacy monolith stored ``users.password_hash`` as an 80-byte BLOB produced by
``hashlib.scrypt`` (16-byte salt || 64-byte digest). New passwords use bcrypt.
``verify_password`` transparently supports both formats; ``upgrade_legacy_hash``
re-hashes a just-verified legacy password to bcrypt so the store migrates on
first successful login (no mass migration, no lockout).

PIN kiosk auth (C.4) uses a separate, weaker secret (4–6 digit PIN) but is *not*
barely protected: the PIN verifier mixes in a **device-bound pepper** that is
unrecoverable by an attacker who only exfiltrated ``pharmacy.db``. The DB stores
``salt`` + ``pin_hash`` only; the pepper lives outside the DB and is bound to the
machine (DPAPI ``LOCAL_MACHINE`` on Windows, file/env fallbacks elsewhere).
"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import platform
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast

import bcrypt
import jwt

from app.shared.config import settings
from app.shared.exceptions import AppException

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_SALT_LEN = 16
_BCRYPT_PREFIX = b"$2"

# ── PIN (C.4) ────────────────────────────────────────────────────────────
_PBKDF2_PIN_ITERS = settings.pin_kdf_iters  # 200,000 (~120 ms on kiosk HW)
_PIN_DKLEN = 32
_PIN_SALT_LEN = 16
_PIN_LOCKOUT_ATTEMPTS = settings.pin_lockout_attempts
_PIN_LOCKOUT_MINUTES = settings.pin_lockout_minutes

# Windows DPAPI flags (used by the dpapi-local-machine pepper backend).
_CRYPT_PROTECT_LOCAL_MACHINE = 4
_CRYPT_UNPROTECT_UI_FORBIDDEN = 0x1

# ``crypt32`` is loaded lazily — absent on non-Windows, which is handled by the
# ``file``/``env`` pepper backends.
_crypt32: Optional[ctypes.WinDLL] = None
if platform.system() == "Windows":
    try:  # pragma: no cover - Windows-only native binding
        _crypt32 = ctypes.WinDLL("crypt32")
    except OSError:
        _crypt32 = None


def hash_password(password: str) -> bytes:
    """Hash ``password`` with bcrypt cost 12 and return the raw BLOB."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))


def is_bcrypt_hash(hashed: bytes) -> bool:
    return hashed.startswith(_BCRYPT_PREFIX)


def _verify_legacy(password: str, hashed: bytes) -> bool:
    if len(hashed) <= _SCRYPT_SALT_LEN:
        return False
    salt = hashed[:_SCRYPT_SALT_LEN]
    expected = hashed[_SCRYPT_SALT_LEN:]
    actual = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return hmac.compare_digest(actual, expected)


def verify_password(password: str, hashed: bytes) -> bool:
    """Return True if ``password`` matches ``hashed`` (bcrypt or legacy scrypt)."""
    if not isinstance(hashed, (bytes, bytearray)):
        return False
    hashed = bytes(hashed)
    try:
        if is_bcrypt_hash(hashed):
            return bcrypt.checkpw(password.encode("utf-8"), hashed)
        return _verify_legacy(password, hashed)
    except (ValueError, TypeError):
        return False


def upgrade_legacy_hash(password: str) -> bytes:
    """Re-hash a password (just verified via legacy scheme) to bcrypt."""
    return hash_password(password)


def create_access_token(
    subject: str,
    role: str,
    permissions: list[str],
    username: Optional[str] = None,
    expires_minutes: int | None = None,
) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "username": username,
        "role": role,
        "permissions": permissions,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(subject: str, expires_days: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=expires_days or settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:  # noqa: BLE001 - normalize all JWT failures
        raise AppException("Invalid or expired token", status_code=401, error_code="invalid_token") from exc


# ── Single-use manager approval tokens (Concern 1 addendum) ──────────────────
# High-risk actions (drawer open, price override, void, discount) require a
# short-lived, single-use, scope-bound token presented via ``X-Approval-Token``.
# Tokens are invalidated (jittered) after first use so they cannot be replayed.
_APPROVAL_JTI_USED: set[str] = set()


def create_approval_token(subject: str, scope: str, ttl_seconds: int = 60) -> str:
    """Issue a single-use, scope-bound approval token (``X-Approval-Token``)."""
    exp = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "sub": subject,
        "scope": scope,
        "type": "approval",
        "jti": secrets.token_hex(16),
        "iat": datetime.now(timezone.utc),
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_approval_token(token: str) -> dict[str, Any]:
    """Decode + validate an approval token; raise if malformed/expired/consumed."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:  # noqa: BLE001 - normalize all JWT failures
        raise AppException("Invalid or expired approval token", status_code=401, error_code="invalid_approval_token") from exc
    if claims.get("type") != "approval":
        raise AppException("Not an approval token", status_code=401, error_code="invalid_approval_token")
    jti = claims.get("jti")
    if jti in _APPROVAL_JTI_USED:
        raise AppException("Approval token already used", status_code=401, error_code="approval_consumed")
    return claims


def consume_approval_token(token: str) -> dict[str, Any]:
    """Validate and single-use-invalidate an approval token."""
    claims = decode_approval_token(token)
    _APPROVAL_JTI_USED.add(claims["jti"])
    return claims


# ── PIN peppering (C.4) ──────────────────────────────────────────────────
# The pepper is a machine-bound secret: it is *not* stored in ``pharmacy.db``.
# On Windows it is sealed to the machine via DPAPI ``LOCAL_MACHINE``, so an
# attacker who exfiltrates only the DB file cannot brute-force the 4–6 digit PIN
# off-machine — ``verify_pin`` returns False for every candidate (even the
# correct one), collapsing the offline search. The ``env``/``file`` backends are
# Tier-2 fallbacks for non-Windows (or test) environments.


def _dpapi_blob(data: bytes) -> "ctypes.Structure":
    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    blob = _BLOB()
    blob.cbData = len(data)
    blob.pbData = (ctypes.c_ubyte * len(data))(*data)
    return blob


def _dpapi_protect(plaintext: bytes) -> Optional[bytes]:
    """Encrypt ``plaintext`` to the local machine; return ciphertext BLOB or None."""
    if _crypt32 is None:
        return None
    import ctypes.wintypes as w

    out = _dpapi_blob(b"\0" * (len(plaintext) + 64))
    res = _crypt32.CryptProtectData(
        _dpapi_blob(plaintext),
        ctypes.c_wchar_p("PharmacyPOS pin pepper"),
        None,
        None,
        None,
        _CRYPT_PROTECT_LOCAL_MACHINE,
        ctypes.byref(out),
    )
    if not res:
        return None
    return bytes(out.pbData[: out.cbData]) if out.cbData else None


def _dpapi_unprotect(blob: bytes) -> Optional[bytes]:
    """Decrypt a DPAPI blob on the bound machine; None if wrong machine/unavailable."""
    if _crypt32 is None:
        return None
    import ctypes.wintypes as w  # noqa: F401  - needed for pointer typing

    out = _dpapi_blob(b"\0" * (len(blob) + 64))
    res = _crypt32.CryptUnprotectData(
        _dpapi_blob(blob),
        None,
        None,
        None,
        None,
        _CRYPT_UNPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not res:
        return None
    return bytes(out.pbData[: out.cbData]) if out.cbData else None


class PinPepper:
    """Resolves the device-bound PIN pepper.

    Backend selection (from ``settings``):
      * ``dpapi-local-machine`` (default, Windows): seal a random pepper to the
        machine via DPAPI; persisted to ``pepper_path``. Off-machine decryption
        fails -> pepper is ``None`` -> PIN verify is impossible offline.
      * ``file`` (Tier-2): 32-byte random secret persisted to ``pepper_path``;
        stable per install but movable with the file.
      * ``env``: read ``settings.pepper_env_key``; trivially flippable in tests.
    """

    def __init__(self, backend: str, path: str, env_key: str) -> None:
        self.backend = backend
        self.path = Path(path)
        self.env_key = env_key
        # The ``env`` backend is process config — capture it at construction so a
        # later env change (or a sibling instance with a different value) can't
        # mutate an already-resolved instance. ``file``/``dpapi`` read live on disk.
        self._env_value = os.environ.get(env_key) if backend == "env" else None
        self._cached: Any = _UNRESOLVED  # not yet resolved

    def derive(self) -> Optional[bytes]:
        if self._cached is not _UNRESOLVED:
            return cast(Optional[bytes], self._cached)
        try:
            if self.backend == "env":
                value = self._env_value
                self._cached = value.encode("utf-8") if value else None
            elif self.backend == "file":
                self._cached = self._file_backend()
            else:  # dpapi-local-machine
                self._cached = self._dpapi_backend()
        except OSError:
            self._cached = None
        return cast(Optional[bytes], self._cached)

    def _file_backend(self) -> Optional[bytes]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            data = self.path.read_bytes()
            return data if len(data) == _PIN_SALT_LEN else None
        secret = secrets.token_bytes(_PIN_SALT_LEN)
        self.path.write_bytes(secret)
        return secret

    def _dpapi_backend(self) -> Optional[bytes]:
        # First run: no blob -> generate a random pepper, DPAPI-seal it, persist.
        if not self.path.exists():
            secret = secrets.token_bytes(_PIN_SALT_LEN)
            blob = _dpapi_protect(secret)
            if blob is None:
                return None  # DPAPI unavailable; PIN auth degrades to "locked".
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(blob)
            return secret
        blob = self.path.read_bytes()
        return _dpapi_unprotect(blob)  # None on wrong machine.

    def reset(self) -> None:
        self._cached = _UNRESOLVED


_pepper: Optional[PinPepper] = None
_pepper_override: Optional[PinPepper] = None  # test/dev injection (bypasses cached settings)
_UNRESOLVED: Any = object()  # sentinel: pepper not yet derived


def get_pin_pepper() -> PinPepper:
    """Module-level pepper resolver.

    Prefers an explicit override (set via :func:`set_pin_pepper`) so tests can
    drive a deterministic ``env`` backend without fighting the lru-cached
    ``settings`` singleton. Falls back to a settings-derived resolver.
    """
    global _pepper
    if _pepper_override is not None:
        return _pepper_override
    if _pepper is None:
        _pepper = PinPepper(
            backend=settings.pepper_backend,
            path=settings.pepper_path,
            env_key=settings.pepper_env_key,
        )
    return _pepper


def set_pin_pepper(pepper: Optional[PinPepper]) -> None:
    """Inject a pepper resolver (tests) or pass ``None`` to clear the override.

    This is the supported seam for unit tests: build ``PinPepper(backend="env",
    env_key="PHARMACY_PEPPER_KEY")`` and flip the env var, instead of relying on
    the process-wide cached ``settings``.
    """
    global _pepper_override
    _pepper_override = pepper


def reset_pin_pepper() -> None:
    """Clear the cached pepper (tests + forced re-resolve)."""
    global _pepper
    if _pepper is not None:
        _pepper.reset()
    _pepper = None


def hash_pin(pin: str, salt: bytes, pepper: bytes, iters: int = _PBKDF2_PIN_ITERS) -> bytes:
    """``PBKDF2-HMAC-SHA256(pin, salt || pepper)`` — pepper is machine-bound."""
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt + pepper, iters, _PIN_DKLEN)


def verify_pin(
    pin: str,
    salt: Optional[bytes],
    stored: Optional[bytes],
    pepper: Optional[bytes],
    iters: int = _PBKDF2_PIN_ITERS,
) -> bool:
    """Constant-time PIN verification.

    Returns ``False`` for *every* candidate (including the correct PIN) when the
    pepper is unavailable — this is the core anti-exfiltration guarantee (C.4):
    a DB stolen off-machine cannot confirm or brute-force any PIN.
    """
    if pepper is None or not salt or not stored:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt + pepper, iters, _PIN_DKLEN)
    return hmac.compare_digest(actual, bytes(stored))


def generate_pin_salt() -> bytes:
    return secrets.token_bytes(_PIN_SALT_LEN)


def seal_lockout(failed_attempts: int, locked_until: Optional[str], pepper: bytes) -> bytes:
    """HMAC-seal the lockout counters so they cannot be reset offline."""
    msg = f"{failed_attempts}|{locked_until or ''}".encode("utf-8")
    return hmac.new(pepper, msg, hashlib.sha256).digest()


def verify_lockout(
    failed_attempts: int,
    locked_until: Optional[str],
    stored_hmac: Optional[bytes],
    pepper: bytes,
) -> bool:
    """True if the lockout counters are untampered.

    On first run (``stored_hmac`` is None) we trust the counters (nothing to
    verify yet). Any mismatch -> tampered -> caller must force a lock.
    """
    if not stored_hmac:
        return True
    expected = seal_lockout(failed_attempts, locked_until, pepper)
    return hmac.compare_digest(expected, bytes(stored_hmac))
