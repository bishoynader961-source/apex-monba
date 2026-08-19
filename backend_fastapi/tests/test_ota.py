"""Offline-apply tests for the OTA delta applier (B4).

Exercises ``OtaApplier`` / ``verify_and_apply_ota`` across the fail-closed
contract: happy path, invalid/missing manifest, hash mismatch (target
untouched), and rollback on post-verify failure.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ota_service import OtaApplier, verify_and_apply_ota


def _write_manifest(update_dir: Path, files: dict[str, bytes]) -> Path:
    manifest = {"files": [{"path": name, "sha256": _hash(b)} for name, b in files.items()]}
    path = update_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _hash(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _seed(update_dir: Path, files: dict[str, bytes]) -> Path:
    for name, data in files.items():
        dst = update_dir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return _write_manifest(update_dir, files)


def test_apply_happy_path(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    (target / "old.txt").write_bytes(b"stale")

    files = {"a.txt": b"alpha", "sub/b.txt": b"beta"}
    manifest = _seed(update, files)

    assert verify_and_apply_ota(manifest, update, target) is True
    assert (target / "a.txt").read_bytes() == b"alpha"
    assert (target / "sub/b.txt").read_bytes() == b"beta"
    assert (target / "old.txt").read_bytes() == b"stale"  # untouched, preserved


def test_invalid_manifest_json(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    bad = update / "manifest.json"
    bad.write_text("{not valid json", encoding="utf-8")

    assert verify_and_apply_ota(bad, update, target) is False


def test_manifest_missing_source_file(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    # Manifest claims a file that is not present in update_dir.
    manifest = update / "manifest.json"
    manifest.write_text(
        json.dumps({"files": [{"path": "ghost.txt", "sha256": _hash(b"x")}]}),
        encoding="utf-8",
    )
    assert verify_and_apply_ota(manifest, update, target) is False
    # Target must be left untouched (no backup/restore churn).
    assert not (target / "ghost.txt").exists()


def test_hash_mismatch_blocks_apply(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    (update / "a.txt").write_bytes(b"alpha")
    (target / "a.txt").write_bytes(b"original")
    manifest = update / "manifest.json"
    # Declare the wrong hash for a.txt.
    manifest.write_text(
        json.dumps({"files": [{"path": "a.txt", "sha256": _hash(b"WRONG")}]}),
        encoding="utf-8",
    )
    assert verify_and_apply_ota(manifest, update, target) is False
    # Original target content preserved (verify step failed before mutation).
    assert (target / "a.txt").read_bytes() == b"original"


def test_rollback_on_post_verify_failure(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    (target / "a.txt").write_bytes(b"original")

    files = {"a.txt": b"alpha"}
    manifest = _seed(update, files)

    applier = OtaApplier(manifest, update, target)
    # Force post-verify to fail so apply() must roll the target back.
    applier._post_verify = lambda: False  # type: ignore[method-assign]
    assert applier.apply() is False
    # Target restored to its pre-apply state.
    assert (target / "a.txt").read_bytes() == b"original"


def test_verify_update_detects_mismatch(tmp_path: Path) -> None:
    update = tmp_path / "update"
    target = tmp_path / "target"
    update.mkdir()
    target.mkdir()
    files = {"a.txt": b"alpha"}
    manifest = _seed(update, files)
    applier = OtaApplier(manifest, update, target)
    assert applier._load_manifest() is True
    assert applier.verify_update() is True

    # Corrupt the on-disk source; verify_update must now fail.
    (update / "a.txt").write_bytes(b"tampered")
    assert applier.verify_update() is False
