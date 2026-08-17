# Plan: Explicit CORS Middleware for Next.js Frontend

> **Date:** 2026-08-12
> **Target file:** `backend_fastapi/app/main.py`
> **Mode:** Plan → hand off to an implementation-capable agent (source edits are blocked in this session).

## Context (verified)

- Backend is FastAPI on Python 3.12.7, virtualenv at `backend_fastapi/.venv` (`python.exe` + `pytest.exe` present).
- `backend_fastapi/pyproject.toml` confirms deps; `[tool.pytest.ini_options] testpaths = ["tests"]`, `asyncio_mode = "auto"`.
- `main.py` lines 8-18 contain a **duplicate import block**: lines 14-18 re-import `FastAPI, Request`, `RequestValidationError`, `CORSMiddleware`, `JSONResponse`, `SQLAlchemyError` already imported at 8-12.
- CORS middleware at lines 61-67 uses `allow_origins=[settings.frontend_url]` — must become an explicit origin list.
- `settings` is still consumed elsewhere in the file: line 34 (`settings.debug`), line 47 (`settings.database_url`), line 55 (`settings.database_url`). Removing the `settings.frontend_url` reference does **not** orphan the `settings` import. (Failure mode F3 resolved.)
- `lifespan` function (lines 45-56) and `app = FastAPI(..., lifespan=lifespan)` (line 59) must remain untouched; `app.add_middleware(...)` is added post-construction and does not interact with `lifespan`.

## Decisions

| Decision | Choice |
|---|---|
| Remove duplicate import block (lines 14-18) | Yes — exact lines, no reformatting of lines 8-12 or 20-32. |
| Replace `allow_origins` value | `["http://localhost:3000", "http://127.0.0.1:3000"]` — no `max_age` / `expose_headers` added (Simplicity First). |
| Touch anything else | No. |

## Surgical edits

### Edit A — remove duplicate imports (lines 14-18)

Delete this exact block (keep the blank line at 13 and 19):

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
```

After Edit A, lines 8-12 become the sole import source for those names.

### Edit B — explicit CORS origins (line 63)

```diff
-    allow_origins=[settings.frontend_url],
+    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
```

## Verification plan (V1-V8)

Run from `backend_fastapi` using `.\.venv\Scripts\python`:

| ID | Check | Command | Expected |
|---|---|---|---|
| V1 | `CORSMiddleware` imported once | `rg -n "CORSMiddleware" app/main.py` | 2 matches (1 import + 1 `add_middleware` usage) |
| V2 | No duplicate FastAPI import | `rg -n "from fastapi import FastAPI" app/main.py` | 1 match |
| V3 | Explicit origins line | `rg -n "allow_origins" app/main.py` | exactly `allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],` |
| V4 | `lifespan=lifespan` intact | `rg -n "lifespan=lifespan" app/main.py` | 1 match on `FastAPI(...)` line |
| V5 | middleware after app | `rg -n "app = FastAPI\|app.add_middleware" app/main.py` | line numbers ascending |
| V6 | import smoke test | `.\.venv\Scripts\python -c "from app.main import app; print(type(app))"` | `<class 'fastapi.applications.FastAPI'>` |
| V7 | runtime CORS (origin echo) | `.\.venv\Scripts\python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); r=c.options('/', headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'GET'}); print(r.headers.get('access-control-allow-origin'))"` | `http://localhost:3000` |
| V8 | full test suite | `.\.venv\Scripts\pytest -q` | 0 failures |

> Note V7: `TestClient(app)` triggers the `lifespan` startup (DB init + seed). If the DB is unavailable in CI, V7/V8 can fail for environment reasons unrelated to this edit. Confirm `DATABASE_URL` / env is configured before attributing failure to the change.

## Risks & failure modes

- **F1** Removing duplicate block drops a needed name → V6 import smoke test catches; restore the missing name from lines 8-12.
- **F2** `lifespan` accidentally touched → V8 (seed/init) + V4 grep guard it.
- **F3** `settings` becomes unused → already resolved: lines 34/47/55 still use it. `rg -n "settings\." app/main.py` post-edit should show 3 usages.
- **F4** Origin not echoed → ensure `CORSMiddleware` is registered *before* any preflight is handled (it is, at `app.add_middleware` before routers). V7 with `127.0.0.1:3000` origin as a second check.

## Rollout

No migration. Runtime-only config. Restart uvicorn after edit. No other files modified.

## Status: COMPLETED (verified V1–V8)

**Edits applied** to `backend_fastapi/app/main.py`:
- Edit A: removed duplicate import block (old lines 14-18). ✓
- Edit B: `allow_origins` → explicit list `["http://localhost:3000", "http://127.0.0.1:3000"]`. ✓

**Verification results:**
| Criterion | Result |
|---|---|
| V1 `CORSMiddleware` x2 (import + usage) | ✅ `rg` → lines 10, 56 |
| V2 no dup `from fastapi import FastAPI` | ✅ line 8 only |
| V3 explicit origins line | ✅ line 57 |
| V4 `lifespan=lifespan` intact | ✅ line 53 |
| V5 middleware after `app = FastAPI` | ✅ 53 then 55 |
| V6 import smoke test | ✅ `<class 'fastapi.applications.FastAPI'>` |
| V7 runtime CORS echo | ✅ `http://localhost:3000` |
| V8 full test suite | ✅ 45 passed in 33.09s |

Failure mode F3 (`settings` unused): resolved — 3 remaining usages at lines 28/41/49.
No other files modified. No `.env`/DB changes.
