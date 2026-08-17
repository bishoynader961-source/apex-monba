# Plan: Add slowapi Rate Limiting to backend_fastapi Auth Endpoints

## Goal
Add IP-based rate limiting to `/api/v1/auth/login` and `/api/v1/auth/login/pin` to prevent
credential/PIN brute-force attacks at the network layer. Uses `slowapi` (already installed in
`.venv` at v0.1.10 but **not** declared in `pyproject.toml`).

## Scope (surgical, no feature creep)
- **Apply rate limits only** on the two auth endpoints listed above. No other routes touched.
- **One new module** (`app/shared/rate_limit.py`) for the limiter singleton + custom handler.
- **Three existing files modified** (`main.py`, `auth_route.py`, `config.py`) + `pyproject.toml`.
- **One new test file** (`tests/test_rate_limit.py`) + `tests/conftest.py` reset fixture.
- Total: ~7 files touched.

## Verified context

### Current state
- **87 tests pass** (`pytest -q` → 87 passed, 0 failed).
- `slowapi 0.1.10` + `limits 5.8.0` installed in `.venv` but absent from `pyproject.toml`.
- FastAPI 0.141.1 / Starlette 1.6.0 / Python 3.12.7.
- Error contract: `{"error": {"code": str, "message": str, "details": {}}}`.
- Auth routes in `app/api/routers/auth_route.py:21-29` (`POST /login`, `POST /login/pin`).
- `app/main.py:54` creates the `FastAPI` instance; routes included at `:113-120`.
- `app/shared/config.py` — env-based `Settings` (`@lru_cache`, `settings = get_settings()`).
- `app/shared/exceptions.py` — `AppException` hierarchy; global handler at `main.py:73-78`.
- Existing PIN lockout: account-level 5 attempts → 15 min lock (in `auth_service.py:134-183`).
  Rate limiting adds a *network-level* layer on top.

### Constraints from AGENTS.md
- Async-only (never sync SQLAlchemy). slowapi is ASGI-compatible; works with async.
- No placeholders / TODOs. Complete error handling + logging.
- `PROJECT_MAP.md` / `FLOW_LOGIC.md` / `VERIFICATION_CHECKLIST.md` read (no conflicts).
- Update docs after completion (state sync).

### slowapi API (verified)
- `from slowapi import Limiter, _rate_limit_exceeded_handler` — both importable.
- `from slowapi.errors import RateLimitExceeded` — subclass of `starlette.HTTPException`.
- `from slowapi.middleware import SlowAPIMiddleware` — importable.
- `from slowapi.util import get_remote_address` — standard IP key function.
- `Limiter(key_func=..., default_limits=[...], storage_uri=None)` → in-memory by default.
- `limiter.reset()` — clears all rate-limit counters (for test isolation).
- `limiter.limit("5/minute")` — decorator for per-route limits.
- Default handler returns `{"error": "Rate limit exceeded: ..."}` — does NOT match app error
  contract → need a custom `RateLimitExceeded` handler.

## Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Storage backend | In-memory (slowapi default) | Single-process kiosk deployment; Redis adds an external dependency with no benefit on a single terminal. |
| Key function | `get_remote_address` | Standard for brute-force protection; limits per-IP, not per-account (attacker rotates IPs less than usernames). |
| Rate limits | Login: 5/min; PIN: 5/min | Matches account-level lockout threshold (5 attempts). Network layer complements the DB-level lockout. |
| Limiter scope | Auth routes only | Scope discipline per user's request. Other endpoints not in scope. |
| Config | Env-configurable via `Settings` | Follows project pattern: `POS_AUTH_RATE_LIMIT="5/minute"`, `POS_PIN_RATE_LIMIT="5/minute"`. |
| Exception format | Custom handler → app error contract | All errors must return `{"error":{"code","message","details"}}`. Default slowapi format would break the contract. |
| Test isolation | Autouse fixture calling `limiter.reset()` | All test requests share the same client IP (`127.0.0.1` via ASGI transport); without reset, rate-limited tests cascade-fail. |
| `pyproject.toml` | Add `slowapi>=0.1.9,<1.0` + `limits>=5.0,<7.0` | Currently installed but undeclared; pin to current versions. |

## Files & changes

### TASK 1 — `app/shared/rate_limit.py` (NEW)
Module-level singleton `limiter` + custom exception handler that conforms to the app error contract.

```python
from __future__ import annotations
from typing import Any
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from app.shared.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=None,  # in-memory
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    ...
```

- `limiter` uses `get_remote_address` → no `default_limits` (applies only where `@limiter.limit()` is used).
- `rate_limit_exceeded_handler` returns:
  ```json
  {"error": {"code": "rate_limited", "message": "Too many requests", "details": {"retry_after": "<seconds>"}}}
  ```
  Extracts `Retry-After` from `exc` headers if available.

### TASK 2 — `app/shared/config.py` (MODIFY)
Add two fields to `Settings`:
```python
auth_rate_limit: str = Field(default="5/minute", alias="POS_AUTH_RATE_LIMIT")
pin_rate_limit: str = Field(default="5/minute", alias="POS_PIN_RATE_LIMIT")
```
Add to `.env.example`:
```env
POS_AUTH_RATE_LIMIT=5/minute
POS_PIN_RATE_LIMIT=5/minute
```

### TASK 3 — `app/main.py` (MODIFY)
Wire limiter middleware + exception handler **before** route inclusion:
```python
from app.shared.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```
Insert after `app = FastAPI(...)` (line 54) and before `app.add_middleware(CORSMiddleware, ...)` (line 56).
Order: `SlowAPIMiddleware` must be registered (wraps the app to check limits before routing).

### TASK 4 — `app/api/routers/auth_route.py` (MODIFY)
Add decorator imports and apply to both endpoints:
```python
from app.shared.rate_limit import limiter

@router.post("/login", response_model=Token)
@limiter.limit(settings.auth_rate_limit)  # wait, decorator runs at import; need static
```
**Issue**: `@limiter.limit()` is evaluated at import time, but `settings` is `@lru_cache` and available at import. Use `settings.auth_rate_limit` directly — it's a string constant at import time.

Actually — `@limiter.limit()` accepts a string or callable. `settings.auth_rate_limit` returns a `str` at import time (settings is loaded at module import). This works.

```python
from app.shared.config import settings
from app.shared.rate_limit import limiter

@limiter.limit(settings.auth_rate_limit)
@router.post("/login", response_model=Token)
async def login(...)
```
Note: decorator order — `@limiter.limit` must be **above** `@router.post` (outermost = rate limit check runs first, then FastAPI routing). This is the standard slowapi pattern.

### TASK 5 — `backend_fastapi/pyproject.toml` (MODIFY)
Add to `[project.dependencies]`:
```toml
"slowapi>=0.1.9,<1.0",
"limits>=5.0,<7.0",
```

### TASK 6 — `tests/conftest.py` (MODIFY)
Add autouse fixture to reset limiter state between tests:
```python
@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.shared.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()
```
This goes alongside the existing `_reset_locks` autouse fixture.

### TASK 7 — `tests/test_rate_limit.py` (NEW)
Test cases:
1. **`test_auth_login_rate_limited`** — Send 6 login requests to `/api/v1/auth/login`; assert 5th returns 200/401, 6th returns 429 with `{"error": {"code": "rate_limited", ...}}`.
2. **`test_auth_login_pin_rate_limited`** — Same for `/api/v1/auth/login/pin`.
3. **`test_rate_limit_reset_does_not_block`** — After `limiter.reset()`, requests succeed normally (verifies test fixture isolation).
4. **`test_health_not_rate_limited`** — `/api/v1/health` not rate-limited (scope discipline).

## Verifiable goals (final)
1. `pytest tests/test_rate_limit.py -q` → **5 passed**.
2. `pytest -q` → **92 passed, 0 failed** (87 existing + 5 new; existing tests must not break despite sharing client IP).
3. `mypy --strict app` → **0 new errors** (7 pre-existing errors in other files remain).
4. `ruff check app tests` → clean (if ruff configured; otherwise skip).

## Risk & rollback
- **Risk**: Rate limiter state leaks across tests. **Mitigation**: autouse `_reset_rate_limiter` fixture in conftest.
- **Risk**: All test requests share IP `127.0.0.1` → any test hitting auth endpoints 5+ times will hit 429. **Mitigation**: reset fixture runs before/after every test (already added). Audit existing tests: `test_auth.py` has at most 4 login calls per test → safe. `test_pin_pepper.py` has up to 6 PIN login calls per test → **needs the reset fixture** to work with rate limiting.
  - **Critical**: `test_pin_pepper.py:test_pin_login_wrong_pin_lockout` makes 6 requests to `/login/pin`. With 5/min limit, the 6th would get 429 instead of 403. The reset fixture (autouse, runs before each test function) clears the counter so each test starts fresh. This must be verified.
- **Rollback**: Remove `@limiter.limit()` decorators + remove middleware registration + remove autouse fixture. Zero data impact.

## Rollback / scope edge cases
- If `slowapi` causes import errors in production, the fallback is to remove the decorator + handler lines (5-line rollback per file).
- `storage_uri=None` (in-memory) is fine for single-process. If multi-process deployment is needed later, set `storage_uri="redis://..."`.

## Validation (final)
1. `pytest tests/test_rate_limit.py -q` → **5 passed**.
2. `pytest -q` → **92 passed, 0 failed** (87 existing + 5 new).
3. `mypy --strict app/` → 7 pre-existing errors, **0 new** errors.

## Implementation deviation log (2026-08-17)
- **Decorator order**: `@limiter.limit()` must be the INNER decorator (below `@router.post`), NOT above. slowapi's `async_wrapper` is only invoked if it is the registered route endpoint. With `@limiter.limit` as outer decorator, FastAPI registers the unwrapped function → rate limiter never fires. Fixed by swapping order.
- **No SlowAPIMiddleware**: slowapi 0.1.10's `async_wrapper._inject_headers` is incompatible with FastAPI Pydantic-model responses — it checks `isinstance(response, Response)` but receives the model object. Additionally, `SlowAPIMiddleware.dispatch` calls `_inject_headers` after `call_next`, where Starlette 1.6.0's `call_next` may return a non-`Response` type. Both paths crash with `"parameter \`response\` must be an instance of starlette.responses.Response"`. Fix: omit `SlowAPIMiddleware`, set `headers_enabled=False` on the `Limiter` (makes `_inject_headers` a no-op), rely on the decorator's in-process `_check_request_limit` enforcement alone.
- **`request: Request` parameter**: slowapi's decorator requires the endpoint function signature to contain a parameter named `request` or `websocket`. Added `request: Request` as first parameter to both `/login` and `/login/pin` handlers. FastAPI injects `Request` automatically; body parsing of `LoginRequest`/`PinLoginRequest` is unaffected.
- **Handler type annotation**: `rate_limit_exceeded_handler` typed as `(Request, Exception)` (not `RateLimitExceeded`) to satisfy `Starlette.add_exception_handler`'s expected `Callable[[Request, Exception], Response | Awaitable[Response]]` signature. Uses `getattr` for `headers`/`detail` internally.
- **Existing test adaptation**: `test_auth_rbac.py::test_account_lockout_after_failures` and `test_pin_pepper.py::test_pin_login_wrong_pin_lockout` send 6 requests to rate-limited endpoints. Added `limiter.reset()` before the 6th request to separate network rate-limiting from account-level lockout testing.
- **Test count**: 5 tests in `test_rate_limit.py` (not 4 as planned — added `test_me_endpoint_rate_limited` to verify `/me` is not rate-limited).

## Architecture change from plan
- **TASK 3** in the plan called for `app.add_middleware(SlowAPIMiddleware)`. This was replaced with `app.state.limiter = limiter` only (no middleware), per the implementation deviation log above. The `@limiter.limit()` decorator handles enforcement in-process; `app.add_exception_handler(RateLimitExceeded, ...)` handles the 429 response rendering.
