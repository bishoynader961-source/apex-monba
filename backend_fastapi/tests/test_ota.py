"""C.2 — Granular OTA delta applier tests.

Uses isolated ``tmp_path`` trees (no touch to real ``app/``). Covers the manifest
schema, verify-before-write, atomic backup+rollback, copy-failure rollback,
post-verify defense, and idempotent re-application.
"""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from app.services.ota_service import OtaApplier, verify_and_apply_ota


def _write_update(update_dir, rel_path, content):
    p = update_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _make_manifest(manifest_path, files):
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"files": files}))
    return manifest_path


def _apply(update_dir, target_dir, files):
    manifest = _make_manifest(
        update_dir / "manifest.json",
        [{"path": rel, "sha256": sha} for rel, sha in files],
    )
    return verify_and_apply_ota(manifest, update_dir, target_dir)


# ── T52-a: happy path ──────────────────────────────────────────────────────────
def test_T52a_apply_success(tmp_path):
    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    sha = _write_update(update_dir, "app/shared/config.py", b"NEW CONFIG\n")
    assert _apply(update_dir, target_dir, [("app/shared/config.py", sha)]) is True
    assert (target_dir / "app/shared/config.py").read_bytes() == b"NEW CONFIG\n"


# ── T52-b: tampered hash is rejected before any target mutation ─────────────────
def test_T52b_tampered_hash_rejected_no_mutation(tmp_path):
    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "app/shared").mkdir(parents=True)
    (target_dir / "app/shared/config.py").write_text("ORIGINAL", encoding="utf-8")
    sha = _write_update(update_dir, "app/shared/config.py", b"NEW CONFIG\n")
    # Wrong expected hash in the manifest.
    assert _apply(update_dir, target_dir, [("app/shared/config.py", sha + "00")]) is False
    # Target untouched (verify-before-write).
    assert (target_dir / "app/shared/config.py").read_text(encoding="utf-8") == "ORIGINAL"


# ── T52-c: missing source file is rejected before any target mutation ──────────
def test_T52c_missing_source_file_rejected(tmp_path):
    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    # Manifest references a file that does not exist in update_dir.
    assert _apply(update_dir, target_dir, [("app/missing.py", "0" * 64)]) is False
    assert not (target_dir / "app/missing.py").exists()


# ── T52-d: copy failure rolls back to the original target ──────────────────────
def test_T52d_copy_failure_rolls_back(tmp_path, monkeypatch):
    from app.services import ota_service

    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    sha = _write_update(update_dir, "app/shared/config.py", b"NEW CONFIG\n")
    (target_dir / "app/shared").mkdir(parents=True)
    (target_dir / "app/shared/config.py").write_text("ORIGINAL", encoding="utf-8")

    def boom(src, dst, *a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(ota_service.shutil, "copy2", boom)
    ok = _apply(update_dir, target_dir, [("app/shared/config.py", sha)])

    assert ok is False
    # Rollback restored the original content.
    assert (target_dir / "app/shared/config.py").read_text(encoding="utf-8") == "ORIGINAL"


# ── T52-e: post-verify mismatch triggers rollback ─────────────────────────────
def test_T52e_post_verify_mismatch_rolls_back(tmp_path, monkeypatch):
    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    sha = _write_update(update_dir, "app/shared/config.py", b"NEW CONFIG\n")
    (target_dir / "app/shared").mkdir(parents=True)
    (target_dir / "app/shared/config.py").write_text("ORIGINAL", encoding="utf-8")

    applier = OtaApplier(update_dir / "manifest.json", update_dir, target_dir)
    _make_manifest(applier.manifest_path, [{"path": "app/shared/config.py", "sha256": sha}])

    # Force post-verify to report failure; monkeypatch auto-restores the method.
    monkeypatch.setattr(OtaApplier, "_post_verify", lambda self: False)
    ok = applier.apply()

    assert ok is False
    # Rollback restored the original content.
    assert (target_dir / "app/shared/config.py").read_text(encoding="utf-8") == "ORIGINAL"


# ── T52-f: idempotent re-application ───────────────────────────────────────────
def test_T52f_idempotent(tmp_path):
    update_dir = tmp_path / "update"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    sha = _write_update(update_dir, "app/shared/config.py", b"NEW CONFIG\n")
    assert _apply(update_dir, target_dir, [("app/shared/config.py", sha)]) is True
    assert _apply(update_dir, target_dir, [("app/shared/config.py", sha)]) is True
    assert (target_dir / "app/shared/config.py").read_bytes() == b"NEW CONFIG\n"
