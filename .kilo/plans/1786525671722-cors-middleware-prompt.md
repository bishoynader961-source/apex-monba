# Task Prompt: Implement Explicit CORS Middleware for Next.js Frontend

> **Date:** 2026-08-12
> **Target File:** `backend_fastapi/app/main.py`
> **Target Assistant:** AI Coding Assistant (Claude 3.5 / GPT-4o / etc.)
> **Architecture Context:** Enterprise Pharmacy Management System — FastAPI backend (Python 3.12.7) + Next.js frontend (React/TypeScript on port 3000).
> **Plan File:** `.kilo/plans/1786525671722-cors-middleware-prompt.md`

---

## 1. Current State (Read Before Editing)

The file `backend_fastapi/app/main.py` currently:
- Imports `CORSMiddleware` from `fastapi.middleware.cors` — it appears in the import block at lines 10 and 16. The second occurrence (line 16) is part of a **redundant duplicate import block** at lines 14-18.
- Defines a `@asynccontextmanager` `lifespan` function (lines 45-56) that initializes the database engine, creates schema, and seeds an admin user.
- Instantiates the FastAPI app at line 59:
  ```python
  app = FastAPI(title="Pharmacy Suite API", version="0.1.0", lifespan=lifespan)
  ```
- Adds CORS middleware at lines 61-67, but with **incorrect `allow_origins`**:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=[settings.frontend_url],   # ← THIS MUST CHANGE
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

## 2. Required Changes (Surgical Edit Only)

### 2.1 Clean Up Duplicate Imports (lines 8-18)

Remove the redundant second import block. After the edit, the import section should contain each name exactly once:

```python
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
```

**Do NOT** reorder or reformat the existing import groups beyond removing the duplicate lines. Leave all other imports (lines 20-32) untouched.

### 2.2 Update CORS `allow_origins` (lines 61-67)

Replace the middleware configuration so that `allow_origins` uses an explicit list of frontend origins instead of `settings.frontend_url`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2.3 Verify Constraint — `lifespan` Is Not Affected

The `lifespan` argument passed to `FastAPI(...)` at line 59 must remain **unchanged**. The CORS middleware (`app.add_middleware(...)`) is added to the app instance *after* construction; it does not interact with or overwrite the `lifespan` parameter. Confirm this by verifying that `lifespan=lifespan` still appears on the `FastAPI(...)` constructor line and that the `lifespan` function definition (lines 45-56) is untouched.

## 3. Constraints & Guardrails

| Constraint | How to Satisfy |
|---|---|
| No placeholders / TODOs | All code must be fully implemented. |
| Type safety | No new untyped code introduced. |
| Simplicity First | Only modify the import section and the `allow_origins` value. Do not add extra configuration (e.g., `max_age`, `expose_headers`). |
| Asset preservation | Do not modify or delete any other file. |
| Flow adherence | This change supports the Next.js frontend (port 3000) calling the FastAPI backend — consistent with Sections 2.2 and 6 of the Master Coding Prompt. |
| Surgical editing | Do not reformat, refactor, or "improve" adjacent code beyond the two required edits. |

## 4. Success Criteria (Verifiable Goals)

| # | Criterion | Verification Method |
|---|---|---|
| V1 | `CORSMiddleware` imported exactly once | `grep -n "CORSMiddleware" backend_fastapi/app/main.py` → 2 matches (1 import, 1 usage in `add_middleware`) |
| V2 | No duplicate import lines | Visually inspect or `grep -n "from fastapi import FastAPI" backend_fastapi/app/main.py` → exactly 1 match |
| V3 | `allow_origins` is the explicit list | `grep -n "allow_origins" backend_fastapi/app/main.py` → exactly one line: `allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],` |
| V4 | `lifespan=lifespan` still present on FastAPI constructor | `grep -n "lifespan=lifespan" backend_fastapi/app/main.py` → 1 match on the `FastAPI(...)` line |
| V5 | Middleware still added after app instantiation | `app.add_middleware(` appears after `app = FastAPI(...)` in the file |
| V6 | App boots without import errors | `cd backend_fastapi && .venv\Scripts\python -c "from app.main import app; print(type(app))"` → prints `<class 'fastapi.applications.FastAPI'>` |
| V7 | CORS configured correctly at runtime | `cd backend_fastapi && .venv\Scripts\python -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); r=c.options('/', headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'GET'}); print(r.headers.get('access-control-allow-origin'))"` → prints `http://localhost:3000` |
| V8 | No regressions in existing test suite | `cd backend_fastapi && .venv\Scripts\pytest -q` → all existing tests pass |

## 5. Affected Files

| File | Change Type | Description |
|---|---|---|
| `backend_fastapi/app/main.py` | MODIFY | (1) Remove duplicate import block (lines 14-18). (2) Replace `allow_origins=[settings.frontend_url]` with explicit list. |

**Do NOT touch any other file.**

## 6. Failure Modes Considered

| Failure | Mitigation |
|---|---|
| Removing the duplicate import block accidentally removes a needed name | After edit, run V6 (import smoke test). If any `ImportError` occurs, restore the missing import. |
| `lifespan` is accidentally removed or modified | V4 checks `grep` for `lifespan=lifespan`. V8 checks full test suite (lifespan powers DB init + seeding). |
| `settings` import becomes unused after removing `settings.frontend_url` | Keep `settings` import — it is still used by `settings.database_url` and `settings.debug` in the lifespan and logging config. Verify with `grep -n "settings\." backend_fastapi/app/main.py`. |
| CORS `allow_origins` rejects legitimate frontend | V7 tests with `Origin: http://localhost:3000` and expects `access-control-allow-origin: http://localhost:3000` in the response. Repeat with `http://127.0.0.1:3000`. |

## 7. Rollout / Migration

No migration needed. This is a purely runtime configuration change — no database schema, no persisted state. Restart the uvicorn server after applying the edit to pick up the new CORS configuration.
