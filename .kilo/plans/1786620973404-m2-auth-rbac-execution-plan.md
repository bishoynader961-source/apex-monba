# M2 Execution Plan — Authentication & Authorization (Auth & RBAC)

> **Status of M2 in repo today:** Already implemented and marked `✅ VERIFIED` in `CHANGELOG.md:44` (backend + frontend). This plan documents the **complete, implementation-ready** step-by-step execution of M2 so it can be re-built from the M1 scaffold, audited, or onboarded. It reflects the *current verified state* of the codebase (including the slowapi rate-limiting added in M10 and the 7 mypy `--strict` debt resolved in M10.5).
>
> **Spec source:** `MASTER_IMPLEMENTATION_PROMPT.md` §2.3 (layered backend), §4.3–4.5 (state mgmt), §5.1 (auth API contract), §6 Security (`bcrypt` cost 12, HS256, 8h/30d, secrets from env), §8 Milestone 2. Reconciled plan: `.kilo/plans/1786452469480-pharmacy-refactor-plan.md` (`### M2 — Auth & RBAC`).
> **Mode:** Plan only — no source/DB files are modified here.

---

## 1. Scope & Goal

Deliver a **stateless**, JWT-based auth + RBAC system for the FastAPI backend and the Next.js frontend, backed by the **preserved `pharmacy.db`** `users`/`roles`/`permissions`/`role_permissions` tables. No table/column renames, no schema additions for M2 (the `pin_*` columns and `lockout_hmac` belong to the later C.4 kiosk-PIN hardening, also already present).

**Success criteria (terminal):**
- `cd backend_fastapi && python -m pytest -q` → all tests pass (auth suite green)
- `cd backend_fastapi && python -m mypy app --strict` → **0 errors**
- `cd . && npx tsc --noEmit` → **0 errors**

---

## 2. Required Resources

| Resource | Version / Detail | Notes |
|---|---|---|
| Python | 3.12.7 | venv at `backend_fastapi/.venv` |
| FastAPI | 0.141.1 | async, Pydantic v2 |
| SQLAlchemy | 2.0.x (async `aiosqlite`) | `app/core/database.py`, `app/core/models.py` |
| bcrypt | `>=4.2,<5.0` | **direct** `bcrypt` package (NOT `passlib` — broken on bcrypt 4.x / 3.13+, per plan §R4) |
| PyJWT | `>=2.9,<3.0` | HS256, `create_access_token`/`create_refresh_token`/`decode_token` |
| slowapi + limits | `>=0.1.9,<1.0` / `>=5.0,<7.0` | M10 network-layer rate limiting on `/login` + `/login/pin` (5/min IP) |
| python-dotenv / pydantic-settings | per `pyproject.toml` | `Settings` loaded from `.env` |
| Node / Next.js | 16.x / 19.x (App Router) | frontend at repo root |
| Zustand | `^4.5.7` | `stores/authStore.ts` |
| Axios | `^1.19.0` | `lib/api.ts` interceptors |
| Tailwind CSS | v3.4+ (`@tailwindcss/postcss` for v4) | `app/globals.css`, `tailwind.config.js`, `postcss.config.js` |

**Environment variables (`.env`, git-ignored):**
```
SECRET_KEY=<64+ random chars>            # JWT signing secret (HS256)
ACCESS_TOKEN_EXPIRE_MINUTES=480          # 8h
REFRESH_TOKEN_EXPIRE_DAYS=30
PHARMACY_DB_URL=sqlite+aiosqlite:///./pharmacy.db
FRONTEND_URL=http://localhost:3000
POS_AUTH_RATE_LIMIT=5/minute             # M10
POS_PIN_RATE_LIMIT=5/minute              # M10 (C.4)
# C.4 pepper (kiosk PIN) — not strictly required for M2 login/password path
POS_PEPPER_BACKEND=dpapi-local-machine  # file/env fallback on non-Windows
POS_PEPPER_PATH=pepper.store
POS_PEPPER_ENV_KEY=PHARMACY_PEPPER_KEY
```

---

## 3. Backend Implementation Steps (ordered)

### TASK 1 — ORM models (`app/core/models.py`)
M2 requires the `User`, `Role`, `Permission`, `RolePermission` models already present in `app/core/models.py` (lines 92–~150). Verify:
- `User`: `id`, `username`, `display_name`, `password_hash: Mapped[bytes]` (LargeBinary), `role_id`, `is_active: int=1`, `failed_attempts: int=0`, `locked_until: Optional[str]`, plus C.4 `pin_hash/pin_salt/pin_failed_attempts/pin_locked_until/lockout_hmac` (already present).
- `Role`: `id`, `name`, `description`, `is_system`.
- `Permission`: `id`, `feature_key`, `description`.
- `RolePermission`: `role_id`, `permission_id`, `granted: int=1`.
- Timestamps: `created_at: Optional[str]` on `User` (string ISO, not `DateTime` — matches `UserPublic.created_at`).
- **No schema migrations for M2** — these tables exist in `pharmacy.db`. `create_schema()` (idempotent `Base.metadata.create_all`) is safe to run.

### TASK 2 — Pydantic schemas (`app/shared/schemas.py`)
Already defined (lines 158–321). Verify exact contracts:
- `UserPublic`: `id, username, display_name, role_id, is_active=1, created_at?`
- `UserCreate`: `username: str`, `display_name: str=""`, `password: str = Field(min_length=8)`, `role_id: int=3`
- `LoginRequest`: `username, password`
- `Token`: `access_token, refresh_token, token_type="bearer", user: UserPublic`
- `RefreshRequest`: `refresh_token`
- `CurrentUser`: `id, username, role, permissions: list[str]`
- `TokenPayload`: `sub, username?, role="unknown", permissions: list[str], type="access", exp?, iat?`

> **Spec deviation to note:** `MASTER_IMPLEMENTATION_PROMPT.md:569` requires password policy "Min 8 chars, **upper+lower+number**". Current `UserCreate` enforces **only** `min_length=8` (no character-class rule). Plan decision: keep `min_length=8` for compatibility with the seeded admin (`admin`/`admin123` violates the upper+lower+number rule). Flag as a known deviation; do **not** add the complexity rule in M2.

### TASK 3 — Security primitives (`app/shared/security.py`)
Already implemented (lines 62–349). Verify each public symbol exists and is typed for `--strict`:
- `hash_password(password) -> bytes` — `bcrypt.hashpw(..., bcrypt.gensalt(rounds=12))`
- `verify_password(password, hashed) -> bool` — bcrypt + legacy scrypt transparent path (`_verify_legacy`, hmac.compare_digest)
- `upgrade_legacy_hash(password) -> bytes` — re-hash to bcrypt (lazy upgrade on first successful legacy login)
- `create_access_token(subject, role, permissions, username?, expires_minutes?) -> str` — HS256, `type="access"`, `exp`
- `create_refresh_token(subject, expires_days?) -> str` — HS256, `type="refresh"`, `exp`
- `decode_token(token) -> dict` — `jwt.decode(..., algorithms=["HS256"])`; raises `AppException` (401) on any `PyJWTError`
- JWT secret sourced from `settings.jwt_secret` (env `SECRET_KEY`)

> **M10.5 fix already applied:** `verify_pin` (C.4) `salt` param is `Optional[bytes]` (line 317). `PinPepper.derive()` returns are `cast(Optional[bytes], ...)` — mypy clean.

### TASK 4 — Repository layer (`app/core/repositories.py`)
`UserRepository` (lines 260–294) must provide:
- `get_by_username(username) -> Optional[User]`
- `get(user_id) -> Optional[User]`
- `create(username, display_name, password_hash, role_id) -> User` (sets `is_active=1`)
- `update_password_hash(user, password_hash) -> None`
- `permissions_for_role(role_id) -> list[str]` — joins `Permission`↔`RolePermission` where `granted==1`
- `RoleRepository`/`PermissionRepository` (or inline `select`) for seeding roles + perms in tests.

### TASK 5 — Auth service (`app/services/auth_service.py`)
`AuthService` (lines 48–186) responsibilities:
1. **`authenticate(username, password) -> User`**
   - Lookup; reject (`UnauthorizedError`) if missing or `is_active != 1`.
   - Account-lockout throttle: parse `locked_until`; if future → `ForbiddenError("Account locked due to too many failed attempts")`.
   - Wrong password → increment `failed_attempts`; at `MAX_FAILED_ATTEMPTS` (5) set `locked_until = now + LOCKOUT_MINUTES` (15). Commit. Raise `UnauthorizedError`.
   - **Success:** reset `failed_attempts=0`, `locked_until=None`; **lazy legacy upgrade** — if `password_hash` does not start with `$2`, re-hash via `upgrade_legacy_hash(password)` + `update_password_hash`. Commit. Return user.
2. **`_build_token(user) -> Token`** — resolve role name (`Role.name`) + `permissions_for_role`, issue HS256 access (8h) + refresh (30d).
3. **`login(username, password) -> Token`** — `authenticate` → `_build_token`.
4. **`refresh(refresh_token) -> Token`** — `decode_token`; reject if `type != "refresh"`; reload user (active check); rebuild token.
5. **`register(UserCreate) -> UserPublic`** — conflict check (`ConflictError` 409 if username exists); `hash_password`; `UserRepository.create`.
6. `get_auth_service(session=Depends(get_session)) -> AuthService` factory.

> C.4 (`set_pin`, `pin_login`, tamper-evident `lockout_hmac`) is already present and out of M2-core scope but lives in the same service — keep as-is.

### TASK 6 — Auth dependencies (`app/api/deps.py`)
Already implemented (lines 32–108), `--strict` clean. Verify:
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")`
- `get_current_user(token, session) -> CurrentUser`: decode → validate `TokenPayload` → reject `type != "access"` (401) → `int(sub)` → lookup user inside `async with session.begin()` → reject inactive (401). Returns `CurrentUser(id, username, role, permissions)` from **JWT claims** (DB only validates existence/active).
- `require_permission(perm) -> Callable`: `Depends(get_current_user)` then `if perm not in user.permissions: raise ForbiddenError`.

### TASK 7 — Auth routers (`app/api/routers/auth_route.py`)
Already implemented (lines 1–67). Verify routes + rate-limit decorators:
- `POST /api/v1/auth/login` → `@limiter.limit(get_auth_limit())` **inner** decorator (below `@router.post`); `request: Request` param required by slowapi.
- `POST /api/v1/auth/login/pin` → `@limiter.limit(get_pin_limit())` (C.4).
- `POST /api/v1/auth/pin` (set PIN) → `require_permission("users.write")`.
- `POST /api/v1/auth/refresh` → `RefreshRequest`.
- `POST /api/v1/auth/register` (201) → `require_permission("users.write")`.
- `GET /api/v1/auth/me` → `get_current_user`.
- `POST /api/v1/auth/logout` → 200 (stateless; client discards tokens).

### TASK 8 — App wiring (`app/main.py`)
Already done (lines 56–59):
- `app.state.limiter = limiter`
- `app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)` (M10)
- `app.include_router(auth_router)`
- Uniform error handlers (`AppException` → `{"error":{"code","message","details"}}`), CORS to `FRONTEND_URL`, security headers middleware.

### TASK 9 — Seed default admin (`app/services/seed_service.py`)
Already implemented. Idempotent `seed_admin_if_absent(session)`: creates `admin`/`admin123` (role_id=1) if absent; swallows all errors (never blocks startup). Called in `lifespan` after `create_schema`.

---

## 4. Frontend Implementation Steps (ordered)

### TASK 10 — TS contracts (`types/contracts.ts`)
Verify `CurrentUser`, `UserPublic`, `Token`, `LoginRequest`, `RefreshRequest`, `ErrorResponse` interfaces mirror the Pydantic models (lines 6–46). `Medicine`/`Batch`/`Receipt*` interfaces already present for later milestones.

### TASK 11 — Axios client + interceptors (`lib/api.ts`)
Verify (lines 1–74):
- `api` instance with `baseURL = NEXT_PUBLIC_API_BASE_URL ?? http://localhost:8000`.
- **Request interceptor:** attach `Authorization: Bearer <access_token>` from `localStorage`.
- **Response interceptor (401):** `fetch("/api/auth/refresh", {method:"POST"})` (reads HTTP-only `refresh_token` cookie server-side) → store new `access_token` → retry once. On failure → `clearToken()`.

### TASK 12 — Auth store (`stores/authStore.ts`)
Verify (lines 1–74): `token`, `user`, `setToken`, `setUser`, `fetchCurrentUser` (`GET /api/v1/auth/me`), `login` (proxy `/api/auth/login`), `logout` (proxy `/api/auth/logout` + clear storage), `hasPermission`, `isAuthenticated`.

### TASK 13 — Server Actions + Route Handlers
- `app/login/actions.ts` (`"use server"`): `loginAction` POSTs to FastAPI `/api/v1/auth/login`, sets **HTTP-only, SameSite=Strict** cookies (`access_token` 480min, `refresh_token` 30d), returns `{success, user, access_token, refresh_token}`. Secure flag only in prod.
- `app/api/auth/login/route.ts`: proxies to FastAPI, sets cookies.
- `app/api/auth/refresh/route.ts`: reads `refresh_token` cookie → FastAPI `/refresh` → sets new `access_token` cookie.
- `app/api/auth/logout/route.ts`: clears both cookies.

### TASK 14 — Login page (`app/login/page.tsx`)
Verify (lines 1–86): `"use client"`, `useActionState(loginAction)`, Tailwind card, username/password inputs, on success stores `access_token` in `localStorage` mirror + `fetchCurrentUser()` + redirect `/dashboard`. Shows `state.error` (normalized from uniform error contract).

### TASK 15 — Middleware + Dashboard (`middleware.ts`, `app/dashboard/page.tsx`)
- `middleware.ts` (lines 1–32): protect `/dashboard`, `/pos`, `/inventory`, `/users`, `/reports`, `/settings`, `/license`; redirect unauthenticated → `/login`; redirect authenticated `/login` → `/dashboard`. **Note:** it checks the `access_token` *cookie* (HTTP-only) — consistent with the cookie-based flow.
- `app/dashboard/page.tsx`: minimal protected route + logout button (already present per M8).

### TASK 16 — Tailwind config
Verify `tailwind.config.js`, `postcss.config.js`, and `@tailwind base/components/utilities` in `app/globals.css` exist (added in M8). `package.json` must list `tailwindcss`/`@tailwindcss/postcss`/`postcss`/`autoprefixer` (present in `devDependencies`).

---

## 5. Test Plan (TDD — backend)

Existing suite (must stay green): `test_auth.py` (5), `test_auth_rbac.py` (5), `test_pin_pepper.py` (8, C.4), `test_jwt_protection.py` (8), `test_seed.py`, `test_rate_limit.py` (5, M10). Target coverage for M2:

| # | Test (file) | Assertion |
|---|---|---|
| A1 | `test_auth.py::test_login_success_bcrypt` | POST `/login` valid → 200, `token_type=bearer`, `access_token`+`refresh_token` present, `user.username` matches |
| A2 | `test_auth.py::test_login_wrong_password` | wrong pw → 401, `error.code="unauthorized"` |
| A3 | `test_auth.py::test_login_legacy_hash_lazy_upgrade` | legacy scrypt BLOB → login 200 → re-read hash now starts `$2`, `verify_password` passes |
| A4 | `test_auth.py::test_register_and_login` | admin token → POST `/register` 201 → login 200 |
| A5 | `test_auth.py::test_register_duplicate_conflict` | duplicate → 409, `error.code="conflict"` |
| R1 | `test_auth_rbac.py::test_inventory_requires_auth` | GET `/inventory/medicines` no token → 401 (`detail="Not authenticated"`) |
| R2 | `test_auth_rbac.py::test_inventory_forbids_wrong_role` | cashier (pos.checkout) → 403, `error.code="forbidden"` |
| R3 | `test_auth_rbac.py::test_inventory_allowed_with_permission` | pharmacist (inventory.read) → 200 |
| R4 | `test_auth_rbac.py::test_me_and_logout` | `/me` → 200 + permissions; `/logout` → 200 |
| R5 | `test_auth_rbac.py::test_register_requires_admin` | pharmacist → 403; admin → 201 |
| R6 | `test_auth_rbac.py::test_account_lockout_after_failures` | 5 wrong → 6th correct → 403 (uses `limiter.reset()` to isolate M10 rate limit) |
| J1–J8 | `test_jwt_protection.py` | valid→200; missing→401; tampered→401; expired→401; refresh-as-access→401; inactive→401; deleted→401; oauth2 tokenUrl configured |
| P1–P8 | `test_pin_pepper.py` | happy path; wrong-PIN lockout; unknown user 401; T54 exfiltrated-DB cannot verify; T55 tamper forces lock; sealed passes (C.4) |

**Frontend:** no Jest/RTL configured; `tsc --noEmit` is the verification surface. Smoke-test the login flow manually via `run_services.py` (Flask :5000, FastAPI :8000, Next :3000).

---

## 6. Validation Sequence (exact commands)

```
cd backend_fastapi
python -m pytest tests/test_auth.py tests/test_auth_rbac.py tests/test_pin_pepper.py tests/test_jwt_protection.py tests/test_seed.py tests/test_rate_limit.py -q
# → all green

python -m mypy app --strict
# → Success: no issues found in 32 source files

cd ..
npx tsc --noEmit
# → exit 0

python run_services.py   # manual smoke: login at http://localhost:3000 → /dashboard
```

---

## 7. Risks & Rollback

| Risk | Mitigation |
|---|---|
| `passlib` + bcrypt 4.x incompatibility | Use `bcrypt` directly (cost 12). Already done. |
| Legacy `scrypt` hashes lock out all users | Lazy upgrade on first successful login; never mass-migrate. Verified by A3. |
| JWT secret weak in prod | `SECRET_KEY` env-only, ≥64 chars; `run_services.py` sets dev default (replace in prod). |
| Account brute-force | M10 `slowapi` 5/min IP limit on `/login`+`/login/pin` + account lockout (5 fails → 15-min lock). |
| Refresh-token replay | Stateless: client discards; no server-side revocation list in M2 (acceptable for kiosk). |
| CORS / cookie mismatch | CORS `allow_origins=[FRONTEND_URL]`, `allow_credentials=True`; cookies `SameSite=Strict`, `secure` in prod. |

**Rollback:** M2 is additive (no schema changes to `pharmacy.db` core tables). Revert router + service + `deps.py` + frontend auth files; re-run mypy/pytest.

---

## 8. Open Questions / Deviations

1. **Password complexity:** Spec asks upper+lower+number; implementation enforces only `min_length=8` (to keep `admin123` valid). **Recommendation:** keep `min_length=8` in M2; revisit as a separate hardening task if required by compliance.
2. **Refresh-token revocation:** Not implemented (stateless design). Acceptable for single-kiosk; flag if multi-terminal rotation is needed.
3. **`/logout` is a no-op server-side** (tokens not revoked). Client discards. Fine for M2.

---

## 9. Milestones (achieved as one cohesive M2)

- **M2.1** Backend auth core: models, schemas, security, repository, service, deps, routers, app wiring, seed. → `pytest` + `mypy --strict` clean.
- **M2.2** Frontend auth: contracts, Axios interceptors, store, server actions, route handlers, login page, middleware. → `tsc --noEmit` clean.
- **M2.3** Integrated verification: full auth + RBAC test suite green; manual smoke through `run_services.py`.

> **Current repo state:** M2.1 + M2.2 + M2.3 are complete and verified (`CHANGELOG.md:44`). This plan is the canonical re-execution / audit reference.
