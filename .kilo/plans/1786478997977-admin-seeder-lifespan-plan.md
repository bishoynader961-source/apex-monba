# Plan — Admin User Auto-Seeding During FastAPI Startup

> **Generated:** 2026-08-11
> **Status:** Finalized (implementation-ready). Corrects a critical import-time defect in the original draft.
> **Verified baseline:** `backend_fastapi/.venv` Python 3.12.7, pytest 8.4.2, mypy 1.20.2. `pytest -q` → **41 passed**.
> **Mode:** Planning (Native Plan Mode). No source files are implemented here.
> **Follow-up:** client asks whether to (a) implement the saved plan or (b) keep refining.

---

## 0. Headline Verdict

The seed design is sound and fully reusable on existing abstractions. One **critical defect** was found in the draft and is corrected below in §3 (the `_sessionmaker` import). One test in §4 was broken and is replaced.

---

## 1. Goal

Integrate an idempotent default-admin seeder into the FastAPI application's existing
`@asynccontextmanager` lifespan in `app/main.py`, creating a user with
`username='admin'`, `password='admin123'` (bcrypt-hashed via the existing
`hash_password()`), `display_name='Admin User'`, `role_id=1` — only if no `admin`
user exists yet. A seeding failure must never crash application startup.

## 2. Codebase-Grounded Findings (verified by reading source)

### F1. Lifespan pattern already in place — no `@app.on_event` to replace
`app/main.py:43-48` uses the `@asynccontextmanager` lifespan pattern. A repo-wide
grep for `on_event` under `backend_fastapi/` returned **zero matches**
(`grep -r "on_event" backend_fastapi/` → "No files found"). The change is purely
additive: extend the existing lifespan body, not replace it.

### F2. `User` model columns (not the spec's literal names)
`app/core/models.py:91-103`:
- `username: Mapped[str]` — `String`, **no UNIQUE constraint** (idempotency must use a SELECT, not rely on `IntegrityError`).
- `display_name: Mapped[str]` — `String`.
- `password_hash: Mapped[bytes]` — `LargeBinary` (the spec's "password" column is actually `password_hash`).
- `role_id: Mapped[int]` — `Integer`, default=3, **no FK constraint** to `roles.id` (so `role_id=1` won't fail even if no `roles` row is present).
- `is_active: Mapped[int]` — `Integer`, default=1.
- `created_at: Mapped[Optional[str]]` — nullable, no Python/DB default in the model.

### F3. Password hashing already exists — use it, do not duplicate
`app/shared/security.py:30-32`:
```python
def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
```
- bcrypt cost 12, returns `bytes` — matches `password_hash: Mapped[bytes]`.
- Single source of truth (used by `AuthService.register` and existing tests).
- `bcrypt>=4.2,<5.0` declared in `pyproject.toml:13`.

### F4. `UserRepository` already has the exact methods needed
`app/core/repositories.py:188-210`:
- `get_by_username(self, username: str) -> Optional[User]` (line 192) — idempotency SELECT.
- `create(self, username: str, display_name: str, password_hash: bytes, role_id: int) -> User` (line 199) — sets `is_active=1`, commits + refreshes.
- Both accept/return `AsyncSession`; follow the repository pattern (service layer uses repositories, not raw ORM).

### F5. Database infrastructure is available in the lifespan
`app/core/database.py`:
- `init_engine(url)` (line 62) — sets module-level globals `_engine` and `_sessionmaker`.
- `create_schema()` (line 76) — `Base.metadata.create_all`.
- `_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None` (line 31) — initialized to `None`, reassigned to a real maker only inside `init_engine()`.
- `get_session()` (line 68) — async-generator dependency; accesses `_sessionmaker` **as a module global** and calls it via `async with _sessionmaker() as session:` (line 72).

### F6. Logging: structlog wraps stdlib logging
`app/shared/logging_config.py` provides `get_logger(name)` returning a structlog logger.
`main.py:33` already uses `logger = get_logger("fastapi")`. Per Protocol IV (Safe Logging),
`get_logger("seeder")` is consistent with the codebase and satisfies the requirement.

### F7. No schema or routing changes needed
`User` model, `UserRepository`, `hash_password()`, `create_schema()` all already exist.
No new tables, columns, or routes. Non-destructive (Requirement V5 satisfied).

### F8. Style baseline (for new files)
`app/services/auth_service.py` (the canonical service): `from __future__ import annotations`,
module docstring, then grouped stdlib/third-party/local imports, then constants.
`app/services/__init__.py` is a one-line comment marker. `backend_fastapi/app/services/` already exists.

## 3. Corrected Design & Data Flow

```
lifespan(app)
  ├── init_engine(settings.database_url)          ← existing; sets database._sessionmaker
  ├── await create_schema()                       ← existing; creates tables if missing
  ├── async with database._sessionmaker() as session:  ← NEW: module-attribute lookup at call-time
  │     ├── try: await seed_admin_if_absent(session)   ← NEW: idempotent seeding
  │     │     ├── UserRepository.get_by_username("admin")
  │     │     │     └── if found → log "skipped", return False
  │     │     └── else → hash_password("admin123") → UserRepository.create(...)
  │     │           └── log "created", return True
  │     └── except Exception: log, swallow          ← defense-in-depth (never block startup)
  └── yield  ← existing: app starts serving requests
```

### ⚠️ CRITICAL FIX: how `_sessionmaker` is referenced (corrects draft §"Design & Data Flow")
The original draft proposed `from app.core.database import ... _sessionmaker`, which
**captures the value `None` at import time** (verified: `from app.core.database import
_sessionmaker; print(_sessionmaker)` → `None`). Even after `init_engine()` reassigns the
*module* attribute, the *local* name imported into `main.py` stays `None`, so
`_sessionmaker()` would raise `TypeError: 'NoneType' object is not callable`
and crash startup — the exact failure the plan must prevent.

**Fix:** import the module object and dereference the attribute at call time
(mirroring how `get_session()` itself accesses `_sessionmaker` at `database.py:72`):
```python
from app.core import database
# ...inside lifespan, after init_engine():
async with database._sessionmaker() as session:
    ...
```
`init_engine()` mutates `database._sessionmaker` via `global`, and `database` is the same
module object, so `database._sessionmaker` resolves to the real maker. This does **not**
modify `app/core/database.py`.

`_sessionmaker()` returns an `AsyncSession` usable as an `async with` context manager
(`async_sessionmaker`/`AsyncSession` implement `__aenter__`/`__aexit__`), guaranteeing
transaction/session cleanup and connection release — identical to `get_session()`'s body.

## 4. Affected Files

| File | Change | Risk |
|------|--------|------|
| `backend_fastapi/app/services/seed_service.py` | CREATE — `seed_admin_if_absent(session)` | Low — new file |
| `backend_fastapi/app/main.py` | MODIFY — add seeding call in lifespan after `create_schema()` | Low — additive |
| `backend_fastapi/tests/test_seed.py` | CREATE — tests for create, hash, idempotency, error-swallow | Low — new test file |

**Do NOT touch:** `app/core/models.py`, `app/core/database.py`, `app/shared/security.py`,
`app/core/repositories.py`, all routers, `pharmacy.db`, `app/api/`, `app/shared/config.py`,
`app/shared/exceptions.py`, `app/shared/schemas.py`.

## 5. Detailed Changes

### 5.1 Create `app/services/seed_service.py`

```python
"""Default admin user seeding — idempotent, best-effort, startup-safe."""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.shared.logging_config import get_logger
from app.shared.security import hash_password

logger = get_logger("seeder")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_DISPLAY_NAME = "Admin User"
DEFAULT_ADMIN_ROLE_ID = 1


async def seed_admin_if_absent(session: AsyncSession) -> bool:
    """Seed a default admin user if none exists.

    Returns True if a new admin was created, False if it already existed.
    Never raises — all errors are logged and swallowed so startup is not blocked.
    """
    try:
        repo = UserRepository(session)
        existing = await repo.get_by_username(DEFAULT_ADMIN_USERNAME)
        if existing is not None:
            logger.info("seed_admin_skipped", reason="user_exists", username=DEFAULT_ADMIN_USERNAME)
            return False

        password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        await repo.create(
            username=DEFAULT_ADMIN_USERNAME,
            display_name=DEFAULT_ADMIN_DISPLAY_NAME,
            password_hash=password_hash,
            role_id=DEFAULT_ADMIN_ROLE_ID,
        )
        logger.info(
            "seed_admin_created",
            username=DEFAULT_ADMIN_USERNAME,
            role_id=DEFAULT_ADMIN_ROLE_ID,
        )
        return True
    except SQLAlchemyError as exc:
        logger.error("seed_admin_db_error", error=str(exc), username=DEFAULT_ADMIN_USERNAME)
        await session.rollback()
        return False
    except Exception as exc:  # noqa: BLE001 — last line of defense for startup safety
        logger.error("seed_admin_unexpected_error", error=str(exc), username=DEFAULT_ADMIN_USERNAME)
        return False
```

**mypy strict notes:** `AsyncSession` typed import; `get_logger` returns `Any` (acceptable, matches `main.py:33`); `exc` used in each branch; `session.rollback()` awaited. No `# type: ignore` needed for source files.

### 5.2 Modify `app/main.py` lifespan (lines 43–48)

Add import of the module (not the symbol) and the seeding block:

```python
from app.core import database
from app.core.database import create_schema, init_engine
from app.services.seed_service import seed_admin_if_absent
```

(Existing lines 27-30 already import `create_schema, init_engine` from `app.core.database`.
The surgical edit adds `from app.core import database` and `from app.services.seed_service
import seed_admin_if_absent` alongside.)

Replace the lifespan body:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine(settings.database_url)
    await create_schema()
    async with database._sessionmaker() as session:  # noqa: S106 — attribute resolved at call-time
        try:
            await seed_admin_if_absent(session)
        except Exception:  # noqa: BLE001 — seed failure must never block startup
            logger.error("seed_admin_lifespan_error", exc_info=True)
    logger.info("startup_complete", database=settings.database_url)
    yield
```

The redundant `try/except` around `seed_admin_if_absent` is intentional defense-in-depth:
`seed_admin_if_absent` already swallows internally, but the wrapper guarantees the lifespan
cannot be killed by an unforeseen non-Exception (e.g. `KeyboardInterrupt` is `BaseException`
and is deliberately NOT caught here — only `Exception`).

### 5.3 Create `tests/test_seed.py`

Uses the existing `session` fixture from `tests/conftest.py` (in-memory aiosqlite,
`expire_on_commit=False`, `Base.metadata.create_all`). `asyncio_mode = "auto"` in
`pyproject.toml` means no `@pytest.mark.asyncio` decorator needed (matches `test_auth.py`).

```python
"""Tests for admin user seeding — creation, hashing, idempotency, startup safety."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import bcrypt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.services.seed_service import seed_admin_if_absent


async def test_seed_creates_admin_if_absent(session: AsyncSession) -> None:
    result = await seed_admin_if_absent(session)
    assert result is True
    user = await UserRepository(session).get_by_username("admin")
    assert user is not None
    assert user.display_name == "Admin User"
    assert user.role_id == 1
    assert user.is_active == 1


async def test_seed_password_is_bcrypt_hashed(session: AsyncSession) -> None:
    await seed_admin_if_absent(session)
    user = await UserRepository(session).get_by_username("admin")
    assert user is not None
    assert user.password_hash.startswith(b"$2")
    assert bcrypt.checkpw(b"admin123", user.password_hash)


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    await seed_admin_if_absent(session)
    user1 = await UserRepository(session).get_by_username("admin")
    assert user1 is not None
    original_hash = user1.password_hash
    result = await seed_admin_if_absent(session)
    assert result is False
    user2 = await UserRepository(session).get_by_username("admin")
    assert user2 is not None
    assert user2.password_hash == original_hash  # password not re-hashed or reset


async def test_seed_swallows_db_error(session: AsyncSession) -> None:
    """A SQLAlchemyError during lookup must not propagate — returns False only."""
    with patch.object(
        UserRepository,
        "get_by_username",
        new_callable=AsyncMock,
        side_effect=SQLAlchemyError("connection lost"),
    ):
        result = await seed_admin_if_absent(session)
    assert result is False
```

**Replaces** the draft's broken `test_seed_does_not_duplicate` (which added a row but never
committed, called seed, or asserted — a no-op test). The new `test_seed_swallows_db_error`
covers V4 (failure → no crash, returns `False`); idempotency row-count is covered by
`test_seed_is_idempotent`.

## 6. Failure Modes Considered

| Failure | Mitigation |
|---------|-----------|
| DB unreachable at startup | `seed_admin_if_absent` catches `SQLAlchemyError`, rolls back, returns `False`; lifespan `try/except` also guards. App still yields and serves (health endpoint unaffected). |
| `admin` already exists (concurrent first-start) | `get_by_username` SELECT-first; no UNIQUE constraint, so no `IntegrityError` race — duplicate insert avoided by the check, not the constraint. |
| `bcrypt` import missing | Already a declared dependency (`bcrypt>=4.2,<5.0`); `hash_password` is the shared function. |
| `_sessionmaker` still `None` after `init_engine` | Impossible — `init_engine()` sets `_sessionmaker` synchronously before the lifespan body proceeds. The `database._sessionmaker` attribute is resolved at call-time (post-init). |
| Seed raises a non-`Exception` (`BaseException` like `KeyboardInterrupt`) | NOT caught by `except Exception` — propagates correctly so shutdown interrupts are not masked. |

## 7. Validation Plan (Verifiable Goals)

| # | Test | How to verify |
|---|------|---------------|
| V1 | Admin created on fresh DB | `seed_admin_if_absent(session)` → `UserRepository.get_by_username("admin")` is not None |
| V2 | Password is bcrypt-hashed | `bcrypt.checkpw(b"admin123", user.password_hash)` is True; hash starts with `b"$2"` |
| V3 | Idempotent — second call returns False | Call twice → second returns `False`; `password_hash` unchanged (not re-hashed) |
| V4 | No crash on error | `patch.object(UserRepository, "get_by_username", AsyncMock(side_effect=SQLAlchemyError(...)))` → returns `False`, no propagation |
| V5 | `display_name='Admin User'`, `role_id=1`, `is_active=1` | Query user after seeding, assert all three |
| V6 | No `@app.on_event` | `grep -r "on_event" backend_fastapi/` → zero matches (confirmed) |
| V7 | No schema/route changes | `git -C backend_fastapi diff --stat` shows only `main.py` modified + `seed_service.py` (new) + `test_seed.py` (new) |
| V8 | New tests pass | `cd backend_fastapi && .venv\Scripts\pytest tests/test_seed.py -v` — 4 green |
| V9 | Full suite no regression | `cd backend_fastapi && .venv\Scripts\pytest -q` — existing 41 + new 4 = ≥45 passed, 0 failed |
| V10 | mypy strict on touched source | `cd backend_fastapi && .venv\Scripts\mypy app/services/seed_service.py app/main.py` — 0 errors |
| V11 | App starts with seeding | `uvicorn app.main:app` (or pytest `TestClient`) → logs contain `seed_admin_created` or `seed_admin_skipped`; health endpoint serves |

## 8. Open Questions (resolved)

None. All decisions grounded in codebase inspection:
- **Hash lib:** `bcrypt` via existing `hash_password()` — already a dependency.
- **Session in lifespan:** `database._sessionmaker()` (module attribute, resolved at call-time) — corrects the draft's import-time-None defect; mirrors `get_session()` at `database.py:72`.
- **Logging:** `get_logger("seeder")` — consistent with `main.py`'s `get_logger("fastapi")`.
- **`role_id=1`:** No FK constraint on `User.role_id`, so inserting `role_id=1` is safe regardless of `roles` table state; spec requires it.
- **`created_at`:** Not set by seed (consistent with `UserRepository.create`); nullable column, acceptable.
- **`main.py` duplicate imports (lines 8–18):** Pre-existing stylistic redundancy; left untouched per Surgical Editing Protocol ("Do not improve adjacent code").
