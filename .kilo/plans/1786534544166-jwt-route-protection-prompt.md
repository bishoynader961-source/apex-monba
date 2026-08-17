# Task Prompt: JWT-Based Route Protection System — FastAPI Backend

> **Date:** 2026-08-12
> **Target Backend Root:** `backend_fastapi/`
> **Target Assistant:** AI Coding Assistant (Claude / GPT-4o / etc.)
> **Reference:** `MASTER_CODING_PROMPT.md` Sections 2.3, 2.4(G4), 4.4, 5.1, 7.2 (JWT Security), 8.2
> **Plan File:** `.kilo/plans/1786534544166-jwt-route-protection-prompt.md`
> **Code Target:** ~300 lines of implementation (across 4 files + tests)

---

## 1. Objective

Implement a production-ready, **asynchronous** JWT-based route protection system for the FastAPI backend. The system must:

1. Extract JWT bearer tokens via `OAuth2PasswordBearer` configured to interface with `/api/v1/auth/login`.
2. Decode and validate each token's **signature** and **expiration timestamp**.
3. Parse the user identifier (`sub` claim) and **verify the user exists** in the database by querying `UserRepository`.
4. Raise `HTTPException` with `401 Unauthorized` and a descriptive message for every authentication failure (missing token, invalid signature, expired token, inactive/deleted user).
5. Wire the protected `get_current_user` dependency into `GET /api/v1/auth/me` so the authenticated user's profile is returned.

---

## 2. Architecture Context (from `MASTER_CODING_PROMPT.md`)

The backend follows a **Layered / Clean Architecture** with four layers. Your implementation must respect this exact structure:

| Layer | Module Path | Responsibility |
|-------|-------------|---------------|
| **API Layer** | `app/api/` | HTTP routing, validation, dependency wiring |
| | `app/api/deps.py` | Authentication dependencies (`get_current_user`, `require_permission`) |
| | `app/api/routers/*_route.py` | Route handlers |
| **Service Layer** | `app/services/` | Business logic orchestration |
| **Data Access Layer** | `app/core/` | ORM models, repositories, database sessions |
| | `app/core/models.py` | SQLAlchemy 2.0 `Mapped[...]` ORM models |
| | `app/core/repositories.py` | Repository classes (`UserRepository`, etc.) |
| | `app/core/database.py` | Async engine, `get_session` dependency |
| **Shared Utilities** | `app/shared/` | Auth, config, schema, exceptions, logging |
| | `app/shared/security.py` | JWT token creation / decoding, password hashing |
| | `app/shared/schemas.py` | Pydantic v2 typed contracts |
| | `app/shared/config.py` | Pydantic `BaseSettings` from env vars |
| | `app/shared/exceptions.py` | `AppException` hierarchy |

**Design patterns mandated by the master prompt that apply here:**
- **Repository Pattern**: All database access goes through `UserRepository`; no raw ORM or SQL in the dependency layer.
- **Dependency Injection**: Use FastAPI's `Depends()` for `OAuth2PasswordBearer`, `get_session`, and `get_current_user`. The `require_permission` helper already depends on `get_current_user` via `Depends()`, so changes to `get_current_user` must remain DI-compatible.
- **Simplicity First**: Reuse the existing `decode_token` function in `app/shared/security.py`. Do not re-implement JWT decoding logic.

---

## 3. Current State Analysis (Read Before Editing)

### 3.1 `app/api/deps.py` (40 lines) — **TO BE REWRITTEN**

The current file defines a **synchronous** `get_current_user` that reads the `Authorization` header manually and **never queries the database**:

```python
# app/api/deps.py (lines 14-29, current)
def get_current_user(request: Request) -> CurrentUser:
    """Decode the ``Authorization: Bearer <token>`` header into a CurrentUser."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = header[len("Bearer ") :]
    claims = decode_token(token)                    # ← raises AppException on failure
    if claims.get("type") != "access":
        raise UnauthorizedError("Invalid token type")
    permissions = [str(p) for p in claims.get("permissions", [])]
    return CurrentUser(
        id=int(claims["sub"]),
        username=str(claims.get("username", claims["sub"])),
        role=str(claims.get("role", "unknown")),
        permissions=permissions,
    )
```

**Problems addressed by this task:**
- `OAuth2PasswordBearer` is **not used** — manual header parsing instead.
- The function is **synchronous** and accepts `Request` directly — not DI-driven.
- **No database lookup** — it trusts the JWT `sub` claim without verifying the user still exists or is active.
- Errors use `UnauthorizedError` (an `AppException` subclass producing `{"error": {...}}` JSON), not `HTTPException`.

### 3.2 `app/shared/security.py` (108 lines) — **READ ONLY / MINOR ENHANCEMENT**

Key functions already exist — **reuse them, do not duplicate**:

```python
# app/shared/security.py (lines 104-108)
def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppException("Invalid or expired token", status_code=401, error_code="invalid_token") from exc
```

- `jwt.decode()` with `algorithms=["HS256"]` **already validates the signature** and **rejects expired tokens** (PyJWT checks `exp` automatically).
- On any `PyJWTError`, it raises `AppException` with `status_code=401`.
- `create_access_token(subject, role, permissions, username, expires_minutes)` signs with `HS256` and embeds `sub`, `username`, `role`, `permissions`, `type`, `iat`, `exp`.
- **Do not modify `decode_token`** — instead, call it from `get_current_user` and catch `AppException`, re-raising as `HTTPException`.

### 3.3 `app/core/repositories.py` (251 lines) — `UserRepository` (READ ONLY)

```python
# app/core/repositories.py (lines 188-222)
class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> Optional[User]: ...
    async def get(self, user_id: int) -> Optional[User]: ...
    async def create(self, username, display_name, password_hash, role_id) -> User: ...
    async def update_password_hash(self, user, password_hash) -> None: ...
    async def permissions_for_role(self, role_id: int) -> list[str]: ...
```

- `UserRepository.get(user_id: int)` is **already async** and returns `Optional[User]`.
- `User` model fields: `id: int`, `username: str`, `display_name: str`, `password_hash: bytes`, `role_id: int` (default 3), `is_active: int` (0 or 1, default 1).

### 3.4 `app/shared/schemas.py` (206 lines) — `CurrentUser` (READ + MINOR ADD)

```python
# app/shared/schemas.py (lines 192-196)
class CurrentUser(BaseModel):
    id: int
    username: str
    role: str
    permissions: list[str] = Field(default_factory=list)
```

- `CurrentUser` has **no** `model_config = ConfigDict(from_attributes=True)` — it is a plain DTO, not an ORM-backed schema.
- `UserPublic` (line 87) has `model_config = ConfigDict(from_attributes=True)` and fields: `id`, `username`, `display_name`, `role_id`, `is_active`, `created_at`.

### 3.5 `app/api/routers/auth_route.py` (47 lines) — `/me` ALREADY EXISTS

```python
# app/api/routers/auth_route.py (lines 39-41, current)
@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
```

- `GET /api/v1/auth/me` already uses `get_current_user` via `Depends()`. No code change is needed in the route handler itself — it will automatically pick up the rewritten async dependency. The assistant should **verify** this works end-to-end (not rewrite it).

### 3.6 `app/shared/exceptions.py` (70 lines) — Error Contract

```python
class AppException(Exception):
    def __init__(self, message, status_code=500, error_code="app_error", details=None): ...

class UnauthorizedError(AppException):
    def __init__(self, message="Authentication required"):
        super().__init__(message, status_code=401, error_code="unauthorized")
```

- The global handler in `app/main.py` (line 72-77) serializes any `AppException` into:
  ```json
  {"error": {"code": "...", "message": "...", "details": {}}}
  ```
- `HTTPException` (FastAPI built-in) instead serializes into:
  ```json
  {"detail": "..."}
  ```
- **This is an intentional requirement**: the user mandates `HTTPException`, not `AppException`, for auth failures. Tests must be updated accordingly (see Section 7.3).

### 3.7 `app/core/database.py` (81 lines) — `get_session` (READ ONLY)

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    ...
```
- `get_session` is the standard DB session dependency. Inject it into `get_current_user` via `Depends(get_session)`.

### 3.8 `app/shared/config.py` (56 lines) — `settings.jwt_secret`

```python
@property
def jwt_secret(self) -> str:
    return self.secret_key.get_secret_value()
```

- `settings.access_token_expire_minutes` defaults to 480 (8 hours).
- `settings.jwt_secret` is already imported and used by `security.py` — no config changes needed.

### 3.9 Existing Tests — `tests/test_auth_rbac.py` (107 lines)

- `test_me_and_logout` (line 53): logs in, calls `GET /api/v1/auth/me`, asserts `username` and `permissions`. **Should still pass** after the rewrite (valid token → 200).
- `test_inventory_requires_auth` (line 23): calls `GET /api/v1/inventory/medicines` with **no auth header**, then asserts `resp.json()["error"]["code"] == "unauthorized"`. **This WILL BREAK** because `OAuth2PasswordBearer` raises `HTTPException(401, "Not authenticated")` which returns `{"detail": "Not authenticated"}`. This test must be updated.
- `test_inventory_forbids_wrong_role` (line 29): uses a valid token but lacks permission → expects 403. Uses `require_permission("inventory.read")`. **Should still pass** (403 path is unchanged).

---

## 4. Technical Requirements

### 4.1 Security Infrastructure — `OAuth2PasswordBearer`

**Task:** Create an `OAuth2PasswordBearer` instance in `app/api/deps.py`, configured with `tokenUrl="api/v1/auth/login"`.

**Rationale:** `OAuth2PasswordBearer` automatically:
- Reads the `Authorization: Bearer <token>` header.
- Returns the token string when injected via `Depends()`.
- Raises `HTTPException(status_code=401, detail="Not authenticated")` when the header is absent or malformed — satisfying the "missing token → 401" requirement without manual header parsing.

**Exact specification:**
```python
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")
```

- The `tokenUrl` value **must** be `api/v1/auth/login` (relative path, no leading slash) — this is the FastAPI convention and matches the actual login endpoint registered at `app/api/routers/auth_route.py:17` (`router = APIRouter(prefix="/api/v1/auth")`).
- Place this instance at **module level** in `app/api/deps.py`, alongside the existing `require_permission` function.

### 4.2 Authentication Logic — Async `get_current_user`

**Task:** Rewrite `get_current_user` to be **asynchronous** and perform a full 5-step verification sequence.

**Sequence (each step is mandatory):**

| Step | Action | Failure → |
|------|--------|-----------|
| 1 | Extract JWT via `Depends(oauth2_scheme)` (OAuth2PasswordBearer) | 401 (automatic, FastAPI raises `HTTPException`) |
| 2 | Decode token + validate signature & expiration via `decode_token(token)` | Catch `AppException` → raise `HTTPException(401, "Invalid or expired token")` |
| 3 | Verify `claims["type"] == "access"` (reject refresh tokens) | `HTTPException(401, "Invalid token type")` |
| 4 | Parse `sub` claim → `user_id = int(claims["sub"])` and fetch from DB | If parsing fails → `HTTPException(401, "Malformed token: missing user identifier")` |
| 5 | `UserRepository(session).get(user_id)` — verify user exists & is active | If `user is None` or `user.is_active != 1` → `HTTPException(401, "User not found or inactive")` |

**Key constraints:**
- The function signature **must** be:
  ```python
  async def get_current_user(
      token: str = Depends(oauth2_scheme),
      session: AsyncSession = Depends(get_session),
  ) -> CurrentUser:
  ```
- `session` is injected via `Depends(get_session)` from `app.core.database`.
- `User.is_active` is an **`int`** (0 or 1) in the existing ORM model — check `!= 1`, not `!= True`.
- After the DB lookup succeeds, construct and return a `CurrentUser` Pydantic model:
  ```python
  return CurrentUser(
      id=user.id,
      username=user.username,
      role=str(claims.get("role", "unknown")),
      permissions=[str(p) for p in claims.get("permissions", [])],
  )
  ```
- `role` and `permissions` **must come from the JWT claims** (not the DB), because the JWT is the source of truth for the authenticated session. The DB lookup is for **existence + active status verification only**.
- Wrap the `decode_token` call in a `try/except AppException` block — do NOT call `jwt.decode()` directly. Reuse the existing `decode_token` function for DRY compliance (master prompt Section 2.3, Protocol I: Dependency Reliability).

### 4.3 Robust Error Handling — `HTTPException` with 401

**Task:** Every authentication failure must raise `HTTPException(status_code=401, detail="<descriptive message>")`.

**Specific scenarios and required messages:**

| Scenario | Source | HTTP Status | `detail` message |
|----------|--------|-------------|------------------|
| No `Authorization` header | `OAuth2PasswordBearer` | 401 | `"Not authenticated"` (automatic, FastAPI default) |
| Malformed header (no "Bearer " prefix) | `OAuth2PasswordBearer` | 401 | `"Not authenticated"` (automatic) |
| Invalid signature / tampered token | `decode_token` raises `AppException` | 401 | `"Invalid or expired token"` |
| Expired `exp` claim | `decode_token` raises `AppException` (PyJWT `ExpiredSignatureError`) | 401 | `"Invalid or expired token"` |
| Missing/invalid `sub` claim | `int(claims["sub"])` raises | 401 | `"Malformed token: missing user identifier"` |
| `type` claim ≠ `"access"` (refresh token used) | explicit check | 401 | `"Invalid token type"` |
| User ID not in database | `UserRepository.get` returns `None` | 401 | `"User not found or inactive"` |
| User deactivated (`is_active == 0`) | `user.is_active != 1` | 401 | `"User not found or inactive"` |

**Constraints:**
- **Do not** use `UnauthorizedError` or `AppException` for these 401 responses — use `HTTPException` exclusively as mandated.
- `OAuth2PasswordBearer` sets the `WWW-Authenticate: Bearer` response header automatically on its 401 responses. Preserve this behavior.
- `HTTPException` produces `{"detail": "<message>"}` by default. This is the expected response format for auth failures. All tests and assertions must accommodate this format.
- The `require_permission` function (line 32-39) should **keep using `ForbiddenError`** for its 403 responses — it is a separate concern (authorization, not authentication) and its existing behavior must not change.

### 4.4 Integration & Verification — `GET /api/v1/auth/me`

**Task:** Verify the `GET /api/v1/auth/me` endpoint correctly uses the rewritten async `get_current_user`.

**Current endpoint (no change needed in the route itself):**
```python
@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
```

**Verification checklist:**
- A valid access token must produce `200 OK` with the authenticated user's `id`, `username`, `role`, and `permissions`.
- No token at all must produce `401` with `{"detail": "Not authenticated"}`.
- An invalid/tampered token must produce `401` with `{"detail": "Invalid or expired token"}`.
- An expired token must produce `401` with `{"detail": "Invalid or expired token"}`.
- A valid token for a deleted or deactivated user must produce `401` with `{"detail": "User not found or inactive"}`.

---

## 5. Implementation Plan — File by File

### File 1: `app/api/deps.py` (REWRITE — ~75 lines)

**Full rewrite of the module.** Replace the entire file content. Imports:

```python
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.repositories import UserRepository
from app.shared.exceptions import AppException
from app.shared.schemas import CurrentUser
from app.shared.security import decode_token
```

Then:
- Instantiate `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")` at module level.
- Define the async `get_current_user` as specified in Section 4.2.
- Keep `require_permission` unchanged (it already works with async `get_current_user` via `Depends()`).

**Note:** `UnauthorizedError` import can be removed since it is no longer used in this file. `ForbiddenError` must remain for `require_permission`.

### File 2: `app/shared/schemas.py` (ADD — ~15 lines)

**Add a `TokenPayload` Pydantic model** after the `CurrentUser` class (line 196) for type-safe parsing of decoded JWT claims:

```python
class TokenPayload(BaseModel):
    """Type-safe representation of an access-token JWT payload."""

    sub: str
    username: Optional[str] = None
    role: str = "unknown"
    permissions: list[str] = Field(default_factory=list)
    type: str = "access"
    exp: Optional[int] = None
    iat: Optional[int] = None
```

**Usage:** In `get_current_user`, after `decode_token` returns the claims dict, validate it through `TokenPayload.model_validate(claims)` for type safety. If validation fails, raise `HTTPException(401, "Malformed token")`. This catches structurally-invalid payloads (missing `sub`, wrong types).

### File 3: `app/api/routers/auth_route.py` (NO CHANGE)

The `/me` endpoint already uses `Depends(get_current_user)`. No modification required. The assistant should **verify** it works with the rewritten dependency, not rewrite it.

### File 4: `tests/test_jwt_protection.py` (NEW — ~120 lines)

Create a new test file with the following test cases. Use the existing `client` and `session` fixtures from `conftest.py`. Use `httpx.AsyncClient` for requests.

#### Test 1: `test_me_returns_user_with_valid_token`
- Seed a user via `UserRepository.create(...)`.
- Obtain an access token by calling `create_access_token` directly (or via login).
- Call `GET /api/v1/auth/me` with `Authorization: Bearer <token>`.
- Assert: `200`, response `username` matches, `permissions` present.

#### Test 2: `test_me_without_token_returns_401`
- Call `GET /api/v1/auth/me` with no `Authorization` header.
- Assert: `401`, `resp.json()["detail"]` contains `"Not authenticated"`.

#### Test 3: `test_me_with_tampered_token_returns_401`
- Create a valid token, then modify one character.
- Call `GET /api/v1/auth/me` with the tampered token.
- Assert: `401`, `resp.json()["detail"]` contains `"Invalid or expired token"`.

#### Test 4: `test_me_with_expired_token_returns_401`
- Use `create_access_token` with `expires_minutes=-1` (or `-5`) to generate an already-expired token.
- Call `GET /api/v1/auth/me` with it.
- Assert: `401`, `resp.json()["detail"]` contains `"Invalid or expired token"`.

#### Test 5: `test_me_with_refresh_token_returns_401`
- Generate a refresh token via `create_refresh_token`.
- Call `GET /api/v1/auth/me` with it as bearer.
- Assert: `401`, `resp.json()["detail"]` contains `"Invalid token type"`.

#### Test 6: `test_me_with_valid_token_for_deleted_user_returns_401`
- Create a user, generate an access token for them, then delete the user from the DB (or set `is_active=0`).
- Call `GET /api/v1/auth/me` with the token.
- Assert: `401`, `resp.json()["detail"]` contains `"User not found or inactive"`.

#### Test 7: `test_oauth2_scheme_token_url_configured`
- Import `oauth2_scheme` from `app.api.deps`.
- Assert `oauth2_scheme.token_url == "api/v1/auth/login"`.

### File 5: `tests/test_auth_rbac.py` (UPDATE — ~5 lines)

**Update `test_inventory_requires_auth`** (line 23-26) to use the new `HTTPException` response format:

```python
# BEFORE (breaks with OAuth2PasswordBearer):
async def test_inventory_requires_auth(client: AsyncClient, session) -> None:
    resp = await client.get("/api/v1/inventory/medicines")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"

# AFTER (use HTTPException format):
async def test_inventory_requires_auth(client: AsyncClient, session) -> None:
    resp = await client.get("/api/v1/inventory/medicines")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"
```

---

## 6. Coding Standards Mandate (from `MASTER_CODING_PROMPT.md`)

Every line of code must adhere to the following standards. These are **non-negotiable**:

### 6.1 File Organization
- Place auth dependencies in `app/api/deps.py` (API Layer — dependency injection surface).
- Place JWT utilities in `app/shared/security.py` (Shared Utilities Layer).
- Place `TokenPayload` schema in `app/shared/schemas.py`.
- Place tests in `tests/` (mirror source structure: `tests/test_jwt_protection.py`).
- No micro-files: keep the security dependency and `require_permission` in the same `deps.py` module.

### 6.2 Type Safety
- **All** function signatures must use full Python type annotations.
- Use `from __future__ import annotations` at the top of every Python file (existing project convention).
- Use explicit Pydantic models for all payloads (`CurrentUser`, `TokenPayload`).
- No `any` types — use `dict[str, Any]` only where the JWT payload type is genuinely dynamic (this is already the case in `decode_token`).
- Run `mypy` with the project's strict configuration (`[tool.mypy] strict = true` in `pyproject.toml`).

### 6.3 Error Patterns
- Authentication failures (401) → `HTTPException(status_code=401, detail="...")`.
- Authorization failures (403) → `ForbiddenError` (unchanged, via `AppException` handler).
- Application errors (400, 404, 409, 500) → `AppException` subclasses (unchanged).
- Never raise bare `Exception` or `RuntimeError` from dependencies.

### 6.4 Dependency Injection
- `OAuth2PasswordBearer` injected as `token: str = Depends(oauth2_scheme)`.
- Database session injected as `session: AsyncSession = Depends(get_session)`.
- `require_permission` injects `get_current_user` as `user: CurrentUser = Depends(get_current_user)`.
- No manual `Request` parsing — all extraction flows through DI.

### 6.5 No Placeholders
- Every function must have a complete, runnable implementation.
- No `# TODO`, `pass`, or `NotImplementedError`.

### 6.6 Simplicity First
- Reuse `decode_token` (don't re-implement JWT validation).
- Reuse `UserRepository.get` (don't write inline SQL).
- Reuse `CurrentUser` (don't create a parallel model).
- The `/me` route handler needs no changes — it already works.

### 6.7 Proof, Not Hope
- Run type checker, linter, and test suite. See Section 8 for exact commands.

---

## 7. Testing Requirements

### 7.1 Test Framework
- Tests use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).
- HTTP requests use `httpx.AsyncClient` with `ASGITransport` (configured in `conftest.py`).
- Database uses in-memory SQLite (`sqlite+aiosqlite:///:memory:`) per the `client` fixture.
- Test files go in `tests/` alongside existing tests.

### 7.2 Test Patterns to Follow
- Use the existing `client` fixture (provides `AsyncClient` with `get_session` overridden).
- Use the existing `session` fixture (provides `AsyncSession`).
- Use `UserRepository(session)` to seed users.
- Use `hash_password("password123")` from `app.shared.security` for seeding.
- Use `create_access_token(str(user.id), role, permissions, username=user.username)` from `app.shared.security` to generate tokens in tests without going through the login endpoint.
- Use `create_refresh_token(str(user.id))` to generate expired/refresh tokens.

### 7.3 Error Response Format Transition
The existing codebase uses `AppException` → `{"error": {"code": ..., "message": ...}}` for errors. The new auth dependencies use `HTTPException` → `{"detail": "..."}`. 

**All new tests must assert against `{"detail": "..."}`**. Existing tests that check `{"error": ["code"]}` for the **unauthenticated** path (specifically `test_inventory_requires_auth`) must be updated to `{"detail": "..."}`.

### 7.4 Required Test Cases (7 tests, listed in Section 5.4)
All 7 tests in the new `tests/test_jwt_protection.py` must pass. Additionally, all tests in `tests/test_auth.py` and `tests/test_auth_rbac.py` must pass (with the one updated assertion in `test_inventory_requires_auth`).

---

## 8. Verification Steps

Run these commands **exactly** from the `backend_fastapi/` directory:

```bash
# 1. Type check (strict mode per pyproject.toml)
mypy app/

# 2. Run the full test suite (all must pass)
pytest tests/ -v

# 3. Run only the new JWT protection tests
pytest tests/test_jwt_protection.py -v

# 4. Verify OAuth2PasswordBearer is imported exactly once in deps.py
grep -n "OAuth2PasswordBearer" app/api/deps.py

# 5. Verify the /me endpoint still resolves
cd backend_fastapi && .venv\Scripts\python -c "from app.main import app; routes = [r.path for r in app.routes]; assert '/api/v1/auth/me' in routes, 'me endpoint missing'; print('me endpoint OK')"

# 6. Confirm no HTTPException is raised from decode_token path without being caught
grep -n "jwt.PyJWTError\|PyJWTError" app/api/deps.py   # should return nothing — jwt is not imported in deps.py
```

> **Note on environment:** The project does not currently list `python-multipart` in `pyproject.toml`. `OAuth2PasswordBearer` for **token extraction** (reading the bearer header) does **not** require `python-multipart`. Only the OAuth2 password **grant flow** (form-encoded login) needs it. Since login uses JSON (`LoginRequest` Pydantic model), no new dependency is needed.

---

## 9. Success Criteria (Verifiable Goals)

| # | Criterion | Verification |
|---|-----------|--------------|
| **V1** | `OAuth2PasswordBearer` instantiated with `tokenUrl="api/v1/auth/login"` | `grep 'tokenUrl="api/v1/auth/login"' app/api/deps.py` → 1 match |
| **V2** | `get_current_user` is `async` | `grep "async def get_current_user" app/api/deps.py` → 1 match |
| **V3** | `get_current_user` queries `UserRepository` | `grep "UserRepository" app/api/deps.py` → at least 1 match |
| **V4** | Missing token → `401` with `{"detail": "Not authenticated"}` | `pytest tests/test_jwt_protection.py::test_me_without_token_returns_401 -v` passes |
| **V5** | Expired token → `401` with `{"detail": "Invalid or expired token"}` | `pytest tests/test_jwt_protection.py::test_me_with_expired_token_returns_401 -v` passes |
| **V6** | Tampered token → `401` | `pytest tests/test_jwt_protection.py::test_me_with_tampered_token_returns_401 -v` passes |
| **V7** | Refresh token rejected → `401` with "Invalid token type" | `pytest tests/test_jwt_protection.py::test_me_with_refresh_token_returns_401 -v` passes |
| **V8** | Deleted/inactive user → `401` | `pytest tests/test_jwt_protection.py::test_me_with_valid_token_for_deleted_user_returns_401 -v` passes |
| **V9** | Valid token → `200` with full user profile | `pytest tests/test_jwt_protection.py::test_me_returns_user_with_valid_token -v` passes |
| **V10** | `mypy --strict` passes with 0 errors | `mypy app/` exits 0 |
| **V11** | Full test suite passes (no regressions) | `pytest tests/ -q` → all passed |
| **V12** | `require_permission` still returns `403` for permission deficits | `pytest tests/test_auth_rbac.py::test_inventory_forbids_wrong_role -v` passes |

---

## 10. Failure Modes & Mitigations

| Failure | Root Cause | Mitigation |
|---------|-----------|------------|
| `OAuth2PasswordBearer` raises `403` instead of `401` | `tokenUrl` uses wrong scheme or `Bearer` header missing | Ensure `tokenUrl="api/v1/auth/login"` and requests send `Authorization: Bearer <token>` |
| `decode_token` raises `AppException` that is not caught | `try/except AppException` block missing around `decode_token` call | Wrap in `try/except AppException`, re-raise as `HTTPException(401, ...)` |
| `User.is_active` check fails | `is_active` is `int` (0/1), not `bool` | Check `user.is_active != 1`, not `not user.is_active` |
| `mypy --strict` fails on untyped `Depends()` | Missing return type annotations | Annotate `-> CurrentUser` on `get_current_user`, `-> Callable[[CurrentUser], CurrentUser]` on `require_permission` |
| `JWTError` not caught | `jwt` module not imported in `deps.py` | Do NOT import `jwt` in `deps.py`. Catch `AppException` from `decode_token` instead. |
| Existing `test_inventory_requires_auth` fails | Asserts old `{"error": {"code": ...}}` format | Update assertion to `resp.json()["detail"] == "Not authenticated"` |
| `TokenPayload.model_validate` rejects valid claims | `sub` is `str` in token but `int` expected | Keep `TokenPayload.sub` as `str` (matches JWT `sub` claim type). Convert to `int` separately after validation. |
| `get_session` not available | ImportError on `app.core.database` | Verify the import path is `from app.core.database import get_session` |
| `Circular import` between `deps.py` and `security.py` | Importing `app.shared.security` in `deps.py` while `security.py` imports from `deps.py` | `security.py` does NOT import from `deps.py` — verify no circular dependency exists before writing |

---

## 11. Out of Scope

- Do **not** modify `app/shared/security.py` beyond what is necessary (reuse `decode_token` as-is).
- Do **not** modify `app/services/auth_service.py` — token creation in login is already correct.
- Do **not** modify `app/core/repositories.py` or `app/core/models.py` — `UserRepository` already exists and works.
- Do **not** modify `app/main.py` — the global exception handler already covers `AppException`; `HTTPException` is handled natively by FastAPI.
- Do **not** implement token refresh or cookie storage in this task — the `/me` endpoint only validates existing tokens.
- Do **not** add `python-multipart` as a dependency — `OAuth2PasswordBearer` token extraction does not require it.

---

## 12. Summary of Expected Deliverables

| Deliverable | File | Lines (est.) |
|-------------|------|-------------|
| Rewritten auth dependencies | `app/api/deps.py` | ~75 |
| New `TokenPayload` schema | `app/shared/schemas.py` (addition) | ~15 |
| New test suite | `tests/test_jwt_protection.py` | ~120 |
| Updated assertion | `tests/test_auth_rbac.py` (1 test) | ~3 |
| **Total** | | **~213–260 lines** |

The remaining ~40–90 lines (to reach ~300) should come from comprehensive docstrings, type annotations, and edge-case handling in the test file (e.g., testing that a non-Bearer `Authorization` header scheme is rejected, or that a token with `sub` as a non-integer fails gracefully).
