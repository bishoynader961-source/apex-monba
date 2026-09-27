"""AES-256-GCM authenticated encryption for encrypted backups (Sprint 2A).

The audit critical-High: ``backup.py`` produced plain-gzip snapshots — a stolen
``pharmacy.db.gz`` is the entire patient database. This module provides
portable, key-held-by-the-admin encryption:

  * Fresh random 256-bit key at backup time (``secrets.token_bytes``), never
    persisted to disk or database — the admin sees it ONCE in the UI and must
    save it ("you cannot recover your backup without it").
  * AES-256-GCM authenticated encryption via ``cryptography.hazmat``: the
    header byte ``0x01`` is AAD-bound, so a truncated/re-tagged file fails
    authentication on restore.
  * File format: ``[header 0x01][12-byte nonce][ciphertext+16-byte GCM tag]``,
    written as ``.backup.enc``.

Restores flow through ``decrypt_file`` → gzip decompress → the existing
``.db`` restore path, so tampered or wrong-key files fail closed.
"""
from __future__ import annotations

import gzip
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.shared.logging_config import get_logger

logger = get_logger("backup_crypto")

_HEADER = b"\x01"
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256


def generate_key() -> bytes:
    """Fresh random AES-256 key (admin-held; never stored)."""
    return secrets.token_bytes(_KEY_LEN)


def encode_key(key: bytes) -> str:
    """Hex-encode a key for single-display to the admin."""
    return key.hex()


def decode_key(key_hex: str) -> bytes:
    """Parse the hex key an admin pasted back; raises on malformed input."""
    raw = key_hex.strip().lower().replace(" ", "")
    if len(raw) != _KEY_LEN * 2:
        raise ValueError("Backup key must be 64 hex characters")
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError("Backup key must be 64 hex characters") from exc


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """AES-256-GCM encrypt with a fresh nonce; header is AAD-bound."""
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, data, _HEADER)
    return _HEADER + nonce + ct


class DecryptError(Exception):
    """Wrong key, corrupted file, or tampered ciphertext."""


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Authenticate + decrypt a ``.backup.enc`` payload. Raises DecryptError."""
    if len(blob) < 1 + _NONCE_LEN + 16 or blob[:1] != _HEADER:
        raise DecryptError("Not an encrypted backup file")
    nonce = blob[1 : 1 + _NONCE_LEN]
    ct = blob[1 + _NONCE_LEN :]
    try:
        return AESGCM(key).decrypt(nonce, ct, _HEADER)
    except InvalidTag as exc:
        raise DecryptError("Wrong key or corrupted backup") from exc


def encrypt_gzip_bytes(gz_data: bytes, key: bytes) -> bytes:
    """Encrypt an already-gzipped payload (the vacuum_backup output)."""
    return encrypt_bytes(gz_data, key)


def decrypt_to_gzip_bytes(blob: bytes, key: bytes) -> bytes:
    """Decrypt a ``.backup.enc`` payload back to its gzip form."""
    return decrypt_bytes(blob, key)


def gunzip_to_db_bytes(gz_data: bytes) -> bytes:
    return gzip.decompress(gz_data)


async def write_encrypted_backup(
    dest_dir: str, gz_source: Path, key: bytes
) -> Path:
    """Encrypt ``gz_source`` (a .db.gz snapshot) to ``<dest_dir>/<name>.backup.enc``.

    Deletes the intermediate plaintext .gz so no unencrypted copy is left on
    disk after the encrypted snapshot is written.
    """
    gz_data = gz_source.read_bytes()
    out_path = Path(dest_dir) / (gz_source.name + ".backup.enc")
    out_path.write_bytes(encrypt_gzip_bytes(gz_data, key))
    logger.info("encrypted_backup_written", path=str(out_path), size=out_path.stat().st_size)
    try:
        gz_source.unlink()
    except OSError:
        logger.warning("plaintext_gz_cleanup_failed", path=str(gz_source))
    return out_path
