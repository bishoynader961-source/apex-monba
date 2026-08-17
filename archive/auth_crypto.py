"""
auth_crypto.py — Salted scrypt hashing for RBAC secrets.

Used to store user passwords, user PINs, and the Owner override master secret
without ever persisting plaintext. Hashing uses ``hashlib.scrypt`` (memory-hard,
stdlib only — no third-party dependency). Verification is performed in
constant time with ``hmac.compare_digest`` to mitigate timing attacks.

The digest embeds a random 16-byte salt so callers store a single BLOB value:

    layout: <16-byte salt> || <64-byte scrypt digest>
"""
from __future__ import annotations

import hashlib
import hmac
import os

# scrypt cost parameters (NIST-aligned, conservative for a desktop app).
_SCRYPT_N = 2 ** 14  # CPU/memory cost
_SCRYPT_R = 8        # block size
_SCRYPT_P = 1        # parallelism
_SCRYPT_DKLEN = 64   # output length (bytes)
_SALT_LEN = 16       # random per-secret salt length (bytes)


def hash_secret(secret: str) -> bytes:
    """Hash ``secret`` and return ``salt || scrypt_digest`` as bytes.

    The returned value is safe to persist directly (e.g. in a BLOB column).
    """
    if not isinstance(secret, str):
        raise TypeError("secret must be a str")
    salt = os.urandom(_SALT_LEN)
    digest = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return salt + digest


def verify_secret(secret: str, hashed: bytes) -> bool:
    """Constant-time verification of ``secret`` against a ``hash_secret`` value.

    Returns ``False`` for malformed/short inputs rather than raising, so callers
    can treat any failure as an authentication failure.
    """
    if not isinstance(secret, str) or not isinstance(hashed, (bytes, bytearray)):
        return False
    hashed = bytes(hashed)
    if len(hashed) <= _SALT_LEN:
        return False
    salt = hashed[:_SALT_LEN]
    expected = hashed[_SALT_LEN:]
    actual = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return hmac.compare_digest(actual, expected)
