# Plan — Default Admin Seeder (`seed_admin.py`)

> **Generated:** 2026-08-11
> **Mode:** Planning (Native Plan Mode). No source files are implemented here.
> **Follow-up:** client asks whether to (a) implement the saved plan or (b) keep refining.

## Goal
One standalone, re-runnable Python script (`python seed_admin.py`) that idempotently inserts a
single default admin into a `users` table, hashed with bcrypt, against a SQLite DB configurable via
`DATABASE_URL`. Must satisfy V1–V7 of the task spec.

## Resolved decisions (from codebase grounding)

| # | Spec says | Conflict / finding | Resolution |
|---|---|---|---|
| D1 | Default URL `sqlite:///./pharmacy.db` (sync URL) with **async** engine/Session | (a) `sqlite:///` is a sync URL and is rejected by `create_async_engine`; (b) defaulting at the live `pharmacy.db` risks colliding with the existing real `users` table (`password_hash BLOB`, no UNIQUE, different schema) → `CREATE TABLE IF NOT EXISTS` no-ops and inserts fail; also violates "no asset destruction". | Use `sqlite+aiosqlite:///./seed_admin.db` as the safe default, overridable by `DATABASE_URL`. To target the real app DB, the operator sets `DATABASE_URL=sqlite+aiosqlite:///./pharmacy.db` and the script **adapts to the existing `users` schema** (see D4) rather than creating a new one. |
| D2 | passlib[bcrypt] hashing; MASTER §3.1 `bcrypt` lib | `passlib==1.7.4` is known-broken with `bcrypt>=4.x` (`ModuleNotFoundError: No module named 'bcrypt.__about__'`). The existing `backend_fastapi` uses the `bcrypt` lib directly in `app/shared/security.py`. | **Use `bcrypt` directly** (`bcrypt.hashpw` + `bcrypt.gensalt(rounds=12)`) to match the existing app and avoid the passlib/bcrypt 4.x incompatibility. Add `bcrypt>=4.2,<5.0` to project deps (already present). If the team strictly requires passlib, pin `bcrypt<4` (e.g. `bcrypt==3.2.2`) — recorded as an alternative. |
| D3 | `check_same_thread=False` comment only | Async `aiosqlite` single-connection needs `check_same_thread=False`; also set `pool_pre_ping=True`. | Engine: `create_async_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)`. |
| D4 | Spec schema `users(username,password,display_name,role_id)` | **Confirmed by user feedback — real `pharmacy.db` uses a different schema** (`password_hash` BLOB, no UNIQUE on `username`, extra columns `is_active`...). Running the spec schema against `pharmacy.db` would crash (inserts into a non-existent `password` column) and, because there's no UNIQUE constraint, the `IntegrityError` backstop would **not** prevent duplicates. | **Single, safe mode only.** The script manages its **own** `users` table (spec schema, UNIQUE username) in a dedicated default DB (`sqlite+aiosqlite:///./seed_admin.db`). `DATABASE_URL` override is supported for arbitrary targets, but pointing at `pharmacy.db` is explicitly **unsupported and documented as out of scope** (would require a separate migration). This rejects the dual-schema "real-DB mode" as too bug-prone and contrary to "Simplicity First". |

### Recommendation (default to implement)
- Async engine, `sqlite+aiosqlite:///./seed_admin.db` as the **only** supported default target.
- `bcrypt` lib directly (cost 12), **not** passlib (avoids D2 breakage).
- Standalone `users` table with UNIQUE(username) — the spec schema, exactly.
- Targeting the real `pharmacy.db` is **out of scope** for this script (documented risk D4);
  a future migration task would align the seeder to the real schema (or reuse `app.shared.security`).

## Out-of-scope / known risks (do not silently handle)
- **Schema mismatch (D4):** never auto-adapt to `pharmacy.db`. If `DATABASE_URL` points at
  `pharmacy.db`, `create_all` is a no-op (table exists) and the insert will fail loudly against the
  real columns — acceptable: it prevents silent corruption. Document this.
- **Missing UNIQUE in real DB:** not reachable because the seeder only creates its own table.


## Open questions (blocking, one to confirm)
1. **Hashing library:** OK to use `bcrypt` directly (matches existing `security.py`, avoids passlib 4.x incompatibility), or must we use `passlib` (requires pinning `bcrypt<4`)?
2. **Default target DB:** OK to default to a dedicated `seed_admin.db` (safe, non-mutating) rather than the spec's literal `sqlite:///./pharmacy.db`? (Required to satisfy "no asset destruction" + V2.)
3. **Real-DB mode:** should the script also support seeding the **existing app `users` table** in `pharmacy.db` (columns `password_hash`/`username`/`display_name`/`role_id`), or only the standalone table?

Default answers assumed above; flip if otherwise.

## Affected boundaries (do not touch)
- `pharmacy.db`, `backend/app.py`, `backend/license_db.sqlite`, `license_gate.py` — preserved.
- The script is fully self-contained: no import of the FastAPI app package (§5.1).

## Data flow
1. `get_database_url()` → env `DATABASE_URL` else `sqlite+aiosqlite:///./seed_admin.db`.
2. `create_async_engine(...)` → `async_sessionmaker`.
3. `Base.metadata.create_all` (standalone mode only).
4. Pre-check: `select(User).where(username=='admin')` → skip if present.
5. `bcrypt.hashpw("admin123", bcrypt.gensalt(rounds=12))` → store digest.
6. `session.add` → `commit`; `IntegrityError` (UNIQUE race) → `rollback` + warn.
7. `finally`: `engine.dispose()` (session via `async with`).

## File layout (single file: `seed_admin.py` at repo root)
- Top imports: `os, sys, logging, asyncio, bcrypt, sqlalchemy` (`create_async_engine`, `async_sessionmaker`, `select`, `Integer/String/Mapped/mapped_column`, `DeclarativeBase`, `IntegrityError/OperationalError/SQLAlchemyError`).
- Module docstring, logging config, `User` model, `get_database_url`, `create_engine_for`, `hash_password`, `seed_admin`, `main` → `asyncio.run`.

## Robustness / failure modes
- `OperationalError` on connect → log stderr, `return 1`.
- `IntegrityError` on insert → `rollback`, warn, skip (idempotent backstop).
- All DB access inside `try/except/finally`; engine disposed in `finally`.
- No `print`; all status via `logging` to stderr.

## Validation plan (V1–V7)
- V1: `python seed_admin.py` → exit 0, no traceback.
- V2–V5: query `sqlite3 seed_admin.db "SELECT username,display_name,role_id,length(password) FROM users"` → 1 row, `display_name='Admin User'`, `role_id=1`, hash length ~60 and starts `$2b$`; `pwd_context`/`bcrypt.checkpw('admin123', hash)` → True; second run → "already exists", count still 1.
- V6: `DATABASE_URL=sqlite+aiosqlite:///./nope/broken.db python seed_admin.py` → exit 1, stderr log; forced duplicate (manual insert before re-run) → handled.
- V7: `python -m pyflakes seed_admin.py` clean; `mypy --strict` (best-effort, script not in app package) clean.
