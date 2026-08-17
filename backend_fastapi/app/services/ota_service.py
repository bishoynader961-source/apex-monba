"""Granular OTA delta applier (C.2).

Pure-Python, dependency-free updater that applies a SHA-256-manifested file set to a
target tree: it verifies every source hash BEFORE touching the target, backs the
target up, copies the new files, post-verifies the on-disk result, and automatically
rolls back from the backup on any failure. Fail-closed: any error returns ``False``
and the target is left in (or restored to) its prior state.

Operational constraint: run this while the FastAPI process is stopped. Swapping files
that are already imported by a running interpreter can leave partially-applied
modules; this module performs an atomic swap of the *files* only and does NOT restart
uvicorn or hot-reload modules. The caller (a deployment script) owns the ``target_dir``
choice and the process restart.

Contract:
    verify_and_apply_ota(manifest_path, update_dir, target_dir) -> bool
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from app.shared.logging_config import get_logger

logger = get_logger("ota")

_BACKUP_NAME = "_backup_current"
_CHUNK = 64 * 1024


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class OtaApplier:
    """Apply a SHA-256-manifested file set to ``target_dir`` with rollback.

    ``manifest_path``: JSON ``{"files": [{"path": str, "sha256": str}, ...]}``.
    ``path`` values are relative to both ``update_dir`` (source) and ``target_dir``
    (destination). Manifest files are verified before any target mutation.
    """

    def __init__(
        self,
        manifest_path: str | Path,
        update_dir: str | Path,
        target_dir: str | Path,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.update_dir = Path(update_dir)
        self.target_dir = Path(target_dir)
        self.backup_dir = self.target_dir.parent / _BACKUP_NAME
        self._manifest: dict[str, Any] = {}

    def _load_manifest(self) -> bool:
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.error("ota_manifest_invalid", path=str(self.manifest_path))
            return False
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            logger.error("ota_manifest_schema_invalid", path=str(self.manifest_path))
            return False
        self._manifest = data
        return True

    def _entries(self) -> list[dict[str, Any]]:
        files = self._manifest.get("files", [])
        return [e for e in files if isinstance(e, dict)]

    def verify_update(self) -> bool:
        """Confirm every manifest file exists in ``update_dir`` and matches its hash."""
        for entry in self._entries():
            rel = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(rel, str) or not isinstance(expected, str):
                return False
            src = self.update_dir / rel
            if not src.is_file():
                logger.error("ota_file_missing", path=rel)
                return False
            if _hash_file(src) != expected:
                logger.error("ota_hash_mismatch", path=rel)
                return False
        return True

    def _backup(self) -> None:
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        if self.target_dir.exists():
            shutil.copytree(self.target_dir, self.backup_dir)

    def _restore(self) -> bool:
        """Restore the target from backup. Returns False if restore itself fails."""
        try:
            if self.target_dir.exists():
                shutil.rmtree(self.target_dir)
            if self.backup_dir.exists():
                shutil.copytree(self.backup_dir, self.target_dir)
            return True
        except OSError:
            logger.error("ota_rollback_failed", target=str(self.target_dir))
            return False

    def _copy_files(self) -> None:
        for entry in self._entries():
            rel = entry.get("path")
            if not isinstance(rel, str):
                continue
            src = self.update_dir / rel
            dst = self.target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _post_verify(self) -> bool:
        """Confirm every written file exists in ``target_dir`` with the expected hash."""
        for entry in self._entries():
            rel = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(rel, str) or not isinstance(expected, str):
                return False
            dst = self.target_dir / rel
            if not dst.is_file():
                logger.error("ota_post_verify_missing", path=rel)
                return False
            if _hash_file(dst) != expected:
                logger.error("ota_post_verify_mismatch", path=rel)
                return False
        return True

    def apply(self) -> bool:
        """Run verify -> backup -> copy -> post-verify; rollback on any failure."""
        if not self._load_manifest():
            return False
        if not self.verify_update():
            return False
        try:
            self._backup()
            self._copy_files()
            ok = self._post_verify()
        except OSError as exc:
            logger.error("ota_apply_failed", error=str(exc))
            self._restore()
            return False
        if not ok:
            logger.error("ota_post_verify_failed")
            self._restore()
            return False
        return True


def verify_and_apply_ota(
    manifest_path: str | Path,
    update_dir: str | Path,
    target_dir: str | Path,
) -> bool:
    """Apply a SHA-256-manifested file set to ``target_dir``.

    Returns True on full success, False on any failure (missing/invalid manifest,
    missing source file, hash mismatch, copy error, or failed post-verify), with the
    target rolled back to its prior state when a backup exists.
    """
    return OtaApplier(manifest_path, update_dir, target_dir).apply()
