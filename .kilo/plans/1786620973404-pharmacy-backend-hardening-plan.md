# Plan: Pharmacy FastAPI Backend Hardening (3 Fixes)

## Goal
Apply the three backend hardening fixes (A: SQLite multi-instance write safety, B: RAM efficiency, C: PIN brute-force) to `backend_fastapi/`. C is already complete; A is partial; B is unstarted **but now explicitly IN-SCOPE** (see TASK 3). Three sync tests are currently failing and block a green suite.

## Verified current state (corrected vs. prior summary)
- Stack: **async** FastAPI + aiosqlite + SQLAlchemy 2.0 `AsyncSession` (`database.py`). NOT sync SQLAlchemy — the sync-flavored reference in the request translates to `event.listen(engine.sync_engine, "connect", ...)`, already wired at `database.py:58`. Do NOT introduce sync `Engine`/`db.query()`.
- **C (PIN brute-force) — DONE & green.** `security.py`: `PinPepper` (DPAPI-local-machine/file/env), PBKDF2 200k iters (`pin_kdf_iters`), `verify_pin` returns False for every candidate when pepper is None (off-machine = no offline brute-force). Tamper-evident lockout via `seal_lockout`/`verify_lockout`; `auth_route.py` `/pin` + `/login/pin`; `migrate_schema` adds `pin_salt/pin_failed_attempts/pin_locked_until/lockout_hmac`; `test_pin_pepper.py` 6/6 incl. T54/T55. **No action.**
- **A (SQLite concurrency) — PARTIAL.** `database.py:34` `_configure_pragmas` sets `busy_timeout=5000` + WAL for file-backed connections. Gaps: timeout too short (ref wants 30000); missing `synchronous=NORMAL`. Write serialization across instances relies on WAL+busy_timeout (readers don't block; writers retry/wait) plus in-process per-drug `asyncio.Lock` (`lock_manager.py`, used by `PosService`/`InventoryService`) and atomic `session.begin()` commits. No polling/SELECT loops exist.
- **B (RAM efficiency) — UNSTARTED, now IN-SCOPE.** `lock_manager.py:16` `_locks: dict[str, asyncio.Lock] = {}` is unbounded (one entry per distinct drug-name, never evicted) — the concrete realization of "no unbounded dicts" for a long-running 4–8GB kiosk. `settings`/`_pepper` are already bounded singletons (fine). TASK 3 below bounds it.
- **3 failing tests** (`pytest -q` → 75 passed, 3 failed): `test_sync.py` T49/T50/T51. Root cause: `SyncRepository.seed_inventory` (`repositories.py:406`) does `delete`+`add` with NO commit, so the conftest `client` fixture (fresh session per request, same StaticPool engine — `conftest.py:47`) cannot see the seed → hub push never decrements → stale reads. Fix = add `await self.session.commit()` after the insert (matches `append_outbox` precedent at line 352). Do NOT add commit to `set_on_hand`/`get_on_hand` — they are internal primitives of `push`, committed once atomically at `sync_service.py:55`.

## Resolved decisions
1. Async, not sync. All edits stay async-aiosqlite; do not port the sync `create_engine(isolation_level="SERIALIZABLE")` reference. SQLite has no true SERIALIZABLE; the effective equivalent (WAL + busy_timeout + per-drug lock + single-writer commit) is already the design.
2. SQLite concurrency fix lives at the engine/prisma layer (`database.py`), not the service layer — satisfies "without modifying how the service layer calls the DB."
3. `lock_manager._locks` LRU eviction must never evict a held lock (check `lock.locked()`) — correctness over memory.

## Task list

### TASK 1 (P0) — Fix the 3 failing sync tests
- File: `app/core/repositories.py:406` `seed_inventory`.
- Edit: add `await self.session.commit()` after `self.session.add(SyncInventory(product_name=product_name, on_hand=on_hand))`.
- Do NOT touch `set_on_hand` (line 424) or `get_on_hand`.
- Verifiable goal: `pytest tests/test_sync.py -q` → 3 passed (T49 over_sells==1 & stock 0; T50 stock 3; T51 stock 4 & merge_seq_max 3).
- Validation: re-run `pytest -q` → 78 passed, 0 failed.

### TASK 2 (P0) — Complete Fix A: SQLite write-safety pragmas
- File: `app/core/database.py:34` `_configure_pragmas`.
- Edits: `busy_timeout=5000` → `busy_timeout=30000`; add `cur.execute("PRAGMA synchronous=NORMAL")` for file-backed (after WAL). Keep in-memory skip.
- Verifiable goal (new test): open a file-backed engine via `build_engine("sqlite+aiosqlite:///./<tmp>.db")`, run a real connection, assert `PRAGMA busy_timeout`==30000, `PRAGMA journal_mode`==wal, `PRAGMA synchronous`==normal.
- Validation: `pytest tests/test_ram.py -q` → new test passes; full suite green.

### TASK 3 (P1, IN-SCOPE) — Fix B: bound `lock_manager._locks` growth (RAM)
- File: `app/core/lock_manager.py:16`.
- Edit: replace `_locks: dict` with a bounded LRU (`collections.OrderedDict`, `maxsize` configurable, default 4096). `get_lock` moves-to-end on hit; on insert over capacity, evict oldest NOT-held lock (`not lock.locked()`); if the oldest is held, skip eviction for it (scan next). `reset_locks` clears the LRU.
- Verifiable goal (new test): seed >> 4096 distinct drug names; assert `len(_locks) <= maxsize`; assert a concurrently held lock is retained during eviction pressure; assert `reset_locks()` clears.
- Scope: **IN-SCOPE** — confirmed by user. This reframes the previously-over-claimed "RAM fix" as a real, targeted change; it is the only unbounded memory growth vector in the hot path.

### TASK 4 (DONE) — Verify Fix C
- No code. Run `pytest tests/test_pin_pepper.py -q` → 6 passed (already green). Close.

## Validation (final)
- `pytest -q` → 78 passed, 0 failed (75 + 3 newly green).
- `ruff check app tests` clean (lint). `mypy --strict app` clean (typecheck).
- No schema/migration changes required: `sync_outbox`/`discrepancies`/`sync_inventory`/`users` PIN columns already exist via `migrate_schema`.

## Files touched
- `app/core/repositories.py` (TASK 1)
- `app/core/database.py` (TASK 2)
- `app/core/lock_manager.py` (TASK 3)
- `tests/test_sync.py` (existing, now green)
- `tests/test_ram.py` (new: pragma assertion + LRU bound — created by impl agent)

## Risk / rollback
- TASK 1 commit in `seed_inventory` is the single point of failure for T49–T51; revert = remove the one line.
- TASK 2 pragma changes only affect file-backed DBs (in-memory skipped) — no test breakage.
- TASK 3 LRU eviction is append-only new logic; `reset_locks`/acquire/release semantics unchanged.

## Status (verified 2026-08-16)
- **Implemented & green.** T1 (`commit()` added in `seed_inventory`), T2 (`busy_timeout=30000` + `synchronous=NORMAL` + WAL in `_configure_pragmas`), T3 (bounded LRU lock cache in `lock_manager.py`) applied; `tests/test_ram.py` added. T4 verified green.
- **Full suite:** 81 passed, 0 failed (75 prior + 3 fixed sync + 3 new ram). `test_sync.py` T49/T50/T51, `test_ram.py` ×3, `test_pin_pepper.py` ×6 all green.
- No schema/migration or service-layer changes. Cross-instance write safety = WAL + `busy_timeout(30000)` + per-drug `asyncio.Lock` + single-writer commit.
- The three authorized fixes (A/B/C) are complete. Remaining work is a **scope decision**, not a code task in this plan.
