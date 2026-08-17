# Plan: C.2 — Granular OTA Delta Applier (pure Python, file-swap + rollback)

## Goal
A dependency-free, pure-Python updater that applies a SHA-256-manifested file set to a target tree with verify-before-write, atomic backup, and automatic rollback. Signature matches the requested reference: `verify_and_apply_ota(manifest_path, update_dir, target_dir) -> bool`.

## Scoped to / out of scope
- IN scope: file-set replace/append + verification + rollback. Single source file `app/services/ota_service.py`, manifest example `deployment/ota_manifest.json`, tests `tests/test_ota.py`. Stdlib only (`hashlib`, `json`, `shutil`, `pathlib`).
- OUT of scope: API endpoint to trigger OTA; process restart coordination; N-version rollback (single backup→restore is sufficient); deleting files absent from manifest; hot-reload of live-imported modules; PyInstaller/`build_exe.py` bundling.

## Current state
- No OTA/update/manifest code exists anywhere in the repo (verified via glob/grep). `backend_fastapi/deployment/` does not exist yet.
- Topology (from `run_services.py`): FastAPI runs `app.main:app` via uvicorn from `backend_fastapi/`; live import tree is `backend_fastapi/app/`. File-swap must therefore run while the process is stopped — an **operational constraint**, not code (documented).

## Resolved decisions
- D1 Manifest: `{"version": str (optional), "files": [{"path": str, "sha256": str (hex)]}`. Path is relative to `update_dir` and applied identically under `target_dir`.
- D2 Contract: `verify_and_apply_ota(manifest_path, update_dir, target_dir) -> bool`. True = full success; **False on any failure** (missing/empty manifest, bad JSON, missing file, hash mismatch, copy error, post-verify failure, restore failure). No exceptions surfaced.
- D3 Verify-first: hash every manifest file in `update_dir` **before** touching `target_dir`; abort on first mismatch/missing. Fail closed.
- D4 Rollback: `backup = target_dir.parent / "_backup_current"`; remove prior backup; if `target_dir` exists, `copytree(target→backup)`. On any apply error: `rmtree(target_dir)` (if present) + `copytree(backup→target_dir)`; return False.
- D5 Apply: `shutil.copy2` each file (mkdir parents, `exist_ok`); preserves mtime/mode.
- D6 Post-verify: after apply, re-hash each written file in `target_dir` and compare to manifest; if mismatch, restore from backup and return False (defends against partial writes on crash).
- D7 No deletions: only add/replace files listed in manifest. Safer; matches reference.
- D8 Concurrency: none in code (single-process offline run); orchestrator owns target_dir choice + restart.

## Data flow
manifest + update_dir → [verify hashes] → [backup target] → [copy files] → [post-verify hashes] → return True; OR on any error → [restore from backup] → return False.

## Failure modes handled
- Missing/invalid manifest → False, no target mutation.
- Missing file in `update_dir` → False (verify phase), target untouched.
- Hash mismatch → False (verify phase), target untouched.
- Copy error mid-apply → restore backup, False.
- Post-verify mismatch → restore backup, False.
- Restore itself fails → best-effort; False; log.

## Task list
- TASK 1 (T52-src): Create `app/services/ota_service.py`:
  - `class OtaApplier: __init__(manifest_path, update_dir, target_dir)`
  - `_hash_file(path) -> str` (sha256, 64KiB chunks).
  - `verify_update() -> bool` (verify phase).
  - `_backup() -> None` / `_restore() -> bool`.
  - `apply() -> bool` (verify → backup → copy loop → post-verify; restore on any failure).
  - module-level `verify_and_apply_ota(manifest_path, update_dir, target_dir) -> bool` delegating to `OtaApplier`.
- TASK 2 (T52-manifest): Create `deployment/ota_manifest.json` example matching D1 (2 sample files w/ real sha256 placeholders; note: ship real hashes from impl).
- TASK 3 (T52-tests): Create `tests/test_ota.py` (T52) with TDD scenarios (see Validation).
- TASK 4: Wire nothing live (no restart/API) — out of scope. Document operational run constraint in module docstring.

## Validation
- `tests/test_ota.py`:
  - T52-a happy path: valid manifest → returns True; target files updated with exact content.
  - T52-b tampered hash → False; target unchanged (verify-before-write).
  - T52-c missing file in update_dir → False; target unchanged.
  - T52-d copy failure → returns False; target restored to pre-update content (monkeypatch a copy to raise).
  - T52-e post-verify defense (optional, impl choice): corrupt a copied file post-write → rollback.
  - T52-f idempotent re-run → True both times.
- `pytest tests/test_ota.py -q` → 5–6 passed.
- `pytest -q` full suite → 81+ passed, 0 failed (no regressions to existing).
- `py_compile app/services/ota_service.py` clean; ruff/mypy on new file.

## Risks / rollback
- Single backup file-name collision if two appliers run concurrently — acceptable (offline, single-process). If needed later, timestamp the backup (out of scope now).
- No deletion support: removed files stay in target — operator must purge if a module is dropped (documented).
- Revert = delete `app/services/ota_service.py`, `tests/test_ota.py`, `deployment/`.

## Hardening status (2026-08-16)
- **All three fixes + C.2 complete and green.** `pytest -q` → 87 passed, 0 failed (no regressions).
  - **Fix A (SQLite write safety):** `database.py` `busy_timeout=30000` + `journal_mode=WAL` + `synchronous=NORMAL` on file-backed connections (async-native via `event.listen(engine.sync_engine, "connect", ...)`); covered by `test_ram.py::test_sqlite_pragmas_applied_on_file_backed_engine`.
  - **Fix B (RAM):** `lock_manager.py` `_locks` is a bounded `OrderedDict` LRU (`_LOCK_MAXSIZE=4096`, `_evict_lock` never evicts a held lock); covered by `test_ram.py::test_lock_cache_is_bounded` + `test_lock_cache_lru_recency`.
  - **Fix C (PIN brute-force):** untouched here — already complete (`security.py` PinPepper+PBKDF2+tamper-evident lockout, `/pin`+`/login/pin`), `test_pin_pepper.py` 6/6 incl. T54/T55.
- **Sync tests (T49/T50/T51):** fixed by `seed_inventory` now committing (`repositories.py`), so the hub sees seeded stock.
- **C.2 (OTA applier):** `app/services/ota_service.py` + `tests/test_ota.py` (T52-a..f) + `deployment/ota_manifest.json`/`.updates/`. Green.
- No remaining items in this plan. Next scope decision is open (see question).
