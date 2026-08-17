# Plan: POS Hardening Extensions — `backend_fastapi/` (Implementation Handoff)

## Status: C.4 COMPLETE (6/6 tests passing). C.1 scaffolded but 3 tests failing (root cause + 1-line fix below). C.2 / C.3 NOT started.
## Baseline: 69 tests pass. Current total: **75 passed, 3 failed** (the 3 are C.1 `test_sync.py`).

## Goal
Implement four hardening extensions in **`backend_fastapi/`** (FastAPI + aiosqlite + SQLAlchemy 2.0 + bcrypt + JWT, single process, asyncio per-drug locks). Each is additive + gated (`settings.multi_terminal` / PIN peppering). Base invariants preserved: single-writer SQLite, FIFO checkout locks (R1), `client_txn_id` exact-once, bcrypt/scrypt/JWT auth.

## Already Done (verified, in source + tests)

### C.4 — PIN device-bound peppering (DONE, 6/6 green) ✅
- `app/shared/config.py`: `pin_kdf_iters=200_000`, `pin_lockout_*`, `pepper_backend/path/env_key`, `multi_terminal`, `device_id` + `_stable_device_id()` `.pharmacy_device_id`.
- `app/core/models.py`: `User.pin_salt/pin_failed_attempts/pin_locked_until/lockout_hmac`; `SyncOutbox`, `Discrepancy`, `SyncInventory` models.
- `app/core/database.py`: `migrate_schema` adds 4 PIN cols + creates `sync_outbox`/`discrepancies`/`sync_inventory` (idempotent).
- `app/shared/security.py`: rewrote (bcrypt+legacy scrypt+JWT intact) + **DPAPI via `ctypes`/`crypt32.dll`** (no pywin32/cryptography) + `file`/`env` Tier-2 backends; `PinPepper`; `hash_pin`/`verify_pin` (`False` for **all** candidates when pepper is `None`); `seal_lockout`/`verify_lockout` (HMAC over counters); `get_pin_pepper`/`set_pin_pepper`/`reset_pin_pepper`.
- `app/shared/schemas.py`: `PinLoginRequest`, `SyncPushEntry`, `SyncPushRequest`, `SyncPushResult`.
- `app/services/auth_service.py`: `AuthService.set_pin` + `AuthService.pin_login` (pepper check → tamper-check → lockout → verify → reset/reseal).
- `app/api/routers/auth_route.py`: `POST /login/pin`, `POST /pin` (admin-gated via `users.write`).
- `tests/test_pin_pepper.py`: happy, wrong-PIN lockout, unknown-user, **T54** (exfil → pepper unavailable → correct PIN fails), **T55** (tampered seal → forced lock) + untampered-passes. **ALL PASS.**

### C.1 — multi-terminal merge-sync (scaffolded, tests FAIL) ⚠️
- `app/core/repositories.py`: `SyncRepository` (append_outbox, find_by_client_txn_id, insert_merged [json-serializes dict payload], max_merge_seq, insert_discrepancy, seed_inventory, get_on_hand, set_on_hand).
- `app/services/sync_service.py`: `SyncService.push` (dedup by client_txn_id, `(device_id, local_seq)` ordering, additive deltas, `OVER_SOLD_CROSS_TERMINAL` → `Discrepancy`, assigns `merge_seq`).
- `app/api/routers/sync_route.py`: `POST /api/v1/sync/push` (gated `settings.multi_terminal`).
- `app/main.py`: `include_router(sync_router)`.
- `app/services/pos_service.py`: appends outbox on checkout commit when `settings.multi_terminal` (non-fatal).
- `tests/test_sync.py`: T49/T50/T51.

### ⚠️ ROOT CAUSE of the 3 C.1 failures + exact fix
`SyncRepository.seed_inventory` does **not commit** its row. The hub session (separate session via the test client) can't see the uncommitted `sync_inventory` row → `get_on_hand` returns `None` (treated as 0) → every sale is mis-flagged as an over-sell and decrements never persist. Same pattern as `test_pos` needing `await session.commit()` after seeding (`_receive`).

**Fix 1 (required):** `app/core/repositories.py` `seed_inventory` — add `await self.session.commit()` at the end.

Current (line 406-413):
```python
    async def seed_inventory(self, product_name: str, on_hand: int) -> None:
        from sqlalchemy import delete
        from app.core.models import SyncInventory

        await self.session.execute(
            delete(SyncInventory).where(SyncInventory.product_name == product_name)
        )
        self.session.add(SyncInventory(product_name=product_name, on_hand=on_hand))
```
→ append `await self.session.commit()`.

**Fix 2 (robustness, recommended):** `set_on_hand` uses `UPDATE` only — if the row doesn't exist (hub receives a sale for an unseeded product), 0 rows update. Make it an upsert so the hub tracks products it hasn't pre-seeded. Replace the `update(...)` body with:
```python
from sqlalchemy import insert
await self.session.execute(
    insert(SyncInventory)
    .values(product_name=product_name, on_hand=on_hand)
    .on_conflict_do_update(
        index_elements=[SyncInventory.product_name], set_={"on_hand": on_hand}
    )
)
```

Apply Fix 1, then re-run `pytest tests/test_sync.py -q`. Expected: T49/T50/T51 pass (75→78).

## Remaining Tasks (not yet done)

### C.3 — RAM caps (in-app; no Electron/Caddy in-repo)
1. `app/core/database.py` `_configure_pragmas` — add `cache_size=-20000`, `mmap_size=268435456`, `journal_size_limit=67108864`, `synchronous=NORMAL` (WAL-safe); skip on `:memory:`.
2. `app/shared/config.py` — add `uvicorn_workers: int = 1` (document `--workers 1` REQUIRED for asyncio-lock semantics) + `db_max_connections` cap; comment block for Windows Job-object / Caddy deployment caps.
3. `tests/test_ram.py` CREATE (T53) — on an in-mem DB, assert the pragmas applied (`PRAGMA cache_size`, `mmap_size`); document the 200-checkout RSS budget as a manual kiosk gate (CI cannot assert OS RSS).

### C.2 — granular OTA (backend-module delta; no Go/Rust binary in-repo)
1. `app/services/ota_service.py` CREATE — `OtaApplier.apply(manifest)`: verify per-layer sha256, stage to temp dir, atomic rename of the target module tree, **rollback to prior dir on failure**, then `await create_schema()` (migrations).
2. `deployment/ota_manifest.json` CREATE — `{layers:[{name,sha256,size,path}]}`.
3. `tests/test_ota.py` CREATE (T52) — only changed layer fetched (mock HTTP + cache by sha256), tampered sha256 → rollback, `current` unchanged.

## Validation
- `cd backend_fastapi && .venv\Scripts\python -m pytest -q` → 69 baseline + 6 C.4 + 3 C.1 (+ remaining C.2/C.3) green; **0 failures**.
- `py_compile` all touched modules; `ruff` if configured.
- C.4: `tests/test_pin_pepper.py` confirms exfiltration resistance (T54) + tamper-evident lockout (T55).
- C.1: `tests/test_sync.py` confirms dedup/over-sell/FIFO (T49/T50/T51) after Fix 1.

## Open (low) — defaults chosen
1. OTA source: local file/staged dir (no HTTP client built; deployment fetches). 
2. Multi-terminal hub: one designated primary + manual promotion.
3. RAM RSS enforcement: in-app caps + pragmas here; hard OS caps (Job object) are a deployment-config concern, not in-repo code.

## Out of Scope (explicitly)
- NSSM/Caddy/Electron/Next.js/TypeScript `lib/*` (do not exist in this repo).
- `setup.iss`/`install.ps1`/`updater.exe` (no Inno Setup/PowerShell/Caddy kiosk in-repo).
- Cloud/mobile sync; FDE rollout; active-active simultaneous writers.
