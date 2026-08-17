# Plan: JWT-Based Route Protection System — FastAPI Backend

> **Date:** 2026-08-12
> **Backend root:** `backend_fastapi/`
> **Reference prompt:** `.kilo/plans/1786534544166-jwt-route-protection-prompt.md`
> **Status:** Implementation-ready

---

## 1. Goal

Upgrade `app/api/deps.py` from a synchronous, header-parsing-only `get_current_user` to an **async** dependency that:

1. Extracts JWT via `OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")`.
2. Decodes + validates signature & expiration via the existing `decode_token()`.
3. Verifies `type == "access"` on the payload.
4. Parses `sub` → `user_id` and fetches the user from `UserRepository.get(user_id)`.
5. Raises `HTTPException(401, ...)` for every auth failure (missing token, invalid signature, expired token, wrong token type, missing/inactive user).
6. Returns a `CurrentUser` DTO backed by a verified DB record.

Wires into the existing `GET /api/v1/auth/me` route (no handler change needed).

---

## 2. Files to Change

| # | File | Action | Est. Lines |
|---|------|--------|-----------|
| 1 | `app/api/deps.py` | **REWRITE** — replace sync manual-header `get_current_user` with async DI-based version using `OAuth2PasswordBearer` + `UserRepository` | ~75 |
| 2 | `app/shared/schemas.py` | **ADD** — `TokenPayload` Pydantic model for type-safe JWT claim validation | ~15 |
| 3 | `tests/test_jwt_protection.py` | **NEW** — 7 test cases covering all auth paths | ~120 |
| 4 | `tests/test_auth_rbac.py` | **UPDATE** — change `test_inventory_requires_auth` assertion from `{"error": ...}` to `{"detail": ...}` | ~3 |

**Total:** ~213–260 lines (supplement with docstrings/edge-case tests to reach ~300).

---

## 3. Implementation Tasks (Ordered)

### Task 1 — Add `TokenPayload` schema (`app/shared/schemas.py`)

After `CurrentUser` (line 196), add:

```python
class TokenPayload(BaseModel):
    sub: str
    username: Optional[str] = None
    role: str = "unknown"
    permissions: list[str] = Field(default_factory=list)
    type: str = "access"
    exp: Optional[int] = None
    iat: Optional[int] = None
```

### Task 2 — Rewrite `app/api/deps.py`

Replace the entire file with:

- **Imports:** `Depends`, `HTTPException` from `fastapi`; `OAuth2PasswordBearer` from `fastapi.security`; `AsyncSession` from `sqlalchemy.ext.asyncio`; `get_session` from `app.core.database`; `UserRepository` from `app.core.repositories`; `AppException` from `app.shared.exceptions`; `CurrentUser` from `app.shared.schemas`; `decode_token` from `app.shared.security`.
- **Module-level:** `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")`
- **`get_current_user`** (async): see Section 4 for the exact 5-step sequence.
- **`require_permission`**: keep unchanged (already correct).

### Task 3 — Verify `GET /api/v1/auth/me` (`app/api/routers/auth_route.py`)

No code change. The route already uses `Depends(get_current_user)` — it will automatically pick up the rewritten dependency.

### Task 4 — Write tests (`tests/test_jwt_protection.py`)

7 tests (see Section 5). Use existing `client` + `session` fixtures from `conftest.py`.

### Task 5 — Update test (`tests/test_auth_rbac.py`)

Change `test_inventory_requires_auth` line 26 from `resp.json()["error"]["code"] == "unauthorized"` to `resp.json()["detail"] == "Not authenticated"`.

---

## 4. `get_current_user` Logic (Precise Spec)

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    # Step 2: Decode + validate signature & exp
    try:
        claims = decode_token(token)
    except AppException:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Step 3: Validate token payload structure via Pydantic
    try:
        payload = TokenPayload.model_validate(claims)
    except ValidationError:
        raise HTTPException(status_code=401, detail="Malformed token")

    # Reject refresh tokens
    if payload.type != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Step 4: Parse sub claim
    try:
        user_id = int(payload.sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Malformed token: missing user identifier")

    # Step 5: Fetch user from DB — wrapped in explicit transaction
    async with session.begin():
        user = await UserRepository(session).get(user_id)
    if user is None or user.is_active != 1:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return CurrentUser(
        id=user.id,
        username=user.username,
        role=payload.role,
        permissions=payload.permissions,
    )
```

**Key facts:**
- `decode_token` raises `AppException` (not `jwt.PyJWTError`) — catch `AppException`.
- `User.is_active` is `int` (0 = inactive, 1 = active), NOT `bool`.
- `role` and `permissions` come from JWT claims (JWT is session source of truth; DB lookup is for existence + active check only).
- `OAuth2PasswordBearer` auto-raises `HTTPException(401, "Not authenticated")` when the `Authorization` header is missing/malformed.
- **Transaction safety:** `get_current_user` and the route handler share the same cached `AsyncSession` (FastAPI `use_cache=True` default). The `session.get()` call inside `UserRepository.get()` starts an autobegin transaction on the shared session. Using `async with session.begin():` wraps the read in an explicit transaction that commits/rolls back on block exit, leaving the session clean for the route handler's own `session.begin()` call (e.g., `PosService.process_checkout`). Without this, the handler would get "A transaction is already begun on this Session."

---

## 5. Test Cases

| # | Test Name | Setup | Expected Result |
|---|-----------|-------|-----------------|
| 1 | `test_me_returns_user_with_valid_token` | Create user via `UserRepository.create`; generate token via `create_access_token(str(user.id), role, perms, username=user.username)` | 200; `username` matches; `permissions` present |
| 2 | `test_me_without_token_returns_401` | No auth header | 401; `detail` = `"Not authenticated"` |
| 3 | `test_me_with_tampered_token_returns_401` | Valid token with one char changed | 401; `detail` contains `"Invalid or expired token"` |
| 4 | `test_me_with_expired_token_returns_401` | `create_access_token(..., expires_minutes=-1)` | 401; `detail` contains `"Invalid or expired token"` |
| 5 | `test_me_with_refresh_token_returns_401` | `create_refresh_token(str(user.id))` | 401; `detail` contains `"Invalid token type"` |
| 6 | `test_me_with_valid_token_for_inactive_user_returns_401` | Create user, deactivate (set `is_active=0`), get token | 401; `detail` contains `"User not found or inactive"` |
| 7 | `test_me_with_valid_token_for_deleted_user_returns_401` | Create user, delete from DB, get token | 401; `detail` contains `"User not found or inactive"` |
| 8 | `test_oauth2_scheme_token_url_configured` | Import `oauth2_scheme` | `oauth2_scheme.model.flows.password.tokenUrl == "api/v1/auth/login"` |

**Test helpers available (from `conftest.py`):** `client` fixture (`AsyncClient` with `get_session` override), `session` fixture (`AsyncSession`).

**Test data helpers (from `app.shared.security`):** `hash_password("password123")`, `create_access_token(...)`, `create_refresh_token(...)`.

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `get_current_user` becomes async — breaks sync callers | All callers use `Depends()`, which handles async transparently | Verified: `require_permission`, `auth_route.py`, `inventory_route.py`, `users_route.py` all use `Depends(get_current_user)` or `Depends(require_permission)` |
| `HTTPException` response format differs from `AppException` format | Existing tests checking `{"error": {"code": ...}}` will fail for unauthenticated path | Update `test_inventory_requires_auth` (line 26) to assert `{"detail": "Not authenticated"}` |
| `is_active` is `int`, not `bool` | `if not user.is_active` would be truthy for `is_active=0` but also falsy for `is_active=""` (edge case) | Use `user.is_active != 1` (explicit int comparison) |
| `TokenPayload.model_validate` strictness | If JWT claims use non-standard types, validation may fail unexpectedly | `sub` is `str` in JWT; `permissions` is `list[str]` — both match the model. Catch `ValidationError` and convert to 401 |
| `mypy --strict` on async `Depends` | Missing type annotations on `Depends()` return | Annotate `-> CurrentUser` and `-> Callable[[CurrentUser], CurrentUser]` |
| Circular import | `deps.py` imports from `security.py` | Verified: `security.py` does NOT import from `deps.py` — no cycle |
| Shared session transaction conflict | Autobegin transaction from `session.get()` leaks into route handler's `session.begin()` → "A transaction is already begun on this Session" | Wrap `session.get()` in `async with session.begin():` to terminate the transaction cleanly before the handler runs |

---

## 7. Out of Scope

- Modifying `app/shared/security.py` (reuse `decode_token` as-is).
- Modifying `app/core/repositories.py` or `app/core/models.py` (reuse existing `UserRepository`).
- Modifying `app/services/auth_service.py` (token issuance already correct).
- Modifying `app/main.py` (exception handler + CORS already configured).
- Adding `python-multipart` (not needed for bearer token extraction).
- Implementing refresh-token endpoint changes or cookie storage.
- Frontend changes.

---

## 8. Validation Steps

Run from `backend_fastapi/`:

```bash
# Type check (strict mode)
mypy app/

# New test suite
pytest tests/test_jwt_protection.py -v

# Full suite (no regressions)
pytest tests/ -q

# Spot checks
grep 'tokenUrl="api/v1/auth/login"' app/api/deps.py    # V1
grep "async def get_current_user" app/api/deps.py      # V2
grep "UserRepository" app/api/deps.py                  # V3
```

---

## 9. Success Criteria

| # | Criterion | How Verified |
|---|-----------|-------------|
| V1 | `OAuth2PasswordBearer` with `tokenUrl="api/v1/auth/login"` | grep match |
| V2 | `get_current_user` is `async` | grep match |
| V3 | `get_current_user` queries `UserRepository` | grep match |
| V4 | Missing token → 401 `{"detail": "Not authenticated"}` | Test 2 passes |
| V5 | Expired token → 401 `{"detail": "Invalid or expired token"}` | Test 4 passes |
| V6 | Tampered token → 401 | Test 3 passes |
| V7 | Refresh token → 401 `{"detail": "Invalid token type"}` | Test 5 passes |
| V8 | Deleted/inactive user → 401 | Tests 6+7 pass |
| V9 | Valid token → 200 with profile | Test 1 passes |
| V10 | `mypy --strict` 0 errors | `mypy app/` exits 0 |
| V11 | Full test suite passes (53 tests) | `pytest tests/ -q` all pass |
| V12 | `require_permission` 403 still works | `test_inventory_forbids_wrong_role` passes |
| V13 | POS checkout works (transaction safety) | `test_pos.py` all 4 pass |
