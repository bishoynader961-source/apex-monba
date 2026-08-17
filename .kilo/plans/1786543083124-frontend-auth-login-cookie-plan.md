# Phase 2: Frontend Authentication Flow — Implementation Plan

> **Date:** 2026-08-12
> **Spec Source:** `MASTER_CODING_PROMPT.md` Section 10 (Login Interface & Auth Flow)
> **Current State Verified:** All referenced files read (see Context section below).
> **Agent Mode:** Native Plan Mode (planning only — no source edits in this session).
> **Plan File:** `.kilo/plans/1786543083124-frontend-auth-login-cookie-plan.md`

---

## 1. Context — Current Codebase State

### Frontend

- **`app/login/page.tsx`** (129 lines): Client component using inline `style={{}}` (NOT Tailwind). Calls `useAuthStore().login()` which POSTs via Axios to `http://localhost:8000`. Stores `access_token` in `localStorage`. Redirects to `/pos` (NOT `/dashboard`).
- **`stores/authStore.ts`** (41 lines): Zustand store. `login()` uses `api.post("/api/v1/auth/login")`, stores `access_token` in `localStorage`, fetches `/api/v1/auth/me` for user. `logout()` clears `localStorage`.
- **`lib/api.ts`** (81 lines): Axios instance. Reads `access_token` from `localStorage` for Bearer header. 401 interceptor reads `refresh_token` from `localStorage`, POSTs to FastAPI `/refresh` directly.
- **`middleware.ts`** (18 lines): Only sets `x-local-currency` header. NO auth guarding.
- **`app/page.tsx`** (18 lines): Home page using Tailwind CSS classes (`flex min-h-screen items-center justify-center`). This means Tailwind IS expected but...
- **`package.json`** (28 lines): No `tailwindcss`, `postcss`, or `autoprefixer` in dependencies. `postcss` IS in `node_modules` (transitive dep of Next.js). `autoprefixer` is NOT installed. No `tailwind.config.js` or `postcss.config.js` exists.
- **`app/globals.css`** (22 lines): CSS reset + dark theme custom properties. No `@tailwind` directives.
- **`app/layout.tsx`** (26 lines): Root layout with Paddle script, imports `./globals.css`.
- **`types/contracts.ts`** (137 lines): `LoginRequest {username, password}`, `Token {access_token, refresh_token, token_type, user: UserPublic}`, `UserPublic {id, username, display_name, role_id, is_active, created_at?}`, `CurrentUser {id, username, role, permissions}`, `ErrorResponse {error: {code, message, details}}`.
- **`package.json` scripts:** `dev`, `build`, `start`, `lint` only. No `test` script.

### Backend (read-only reference)

- **`backend_fastapi/app/api/routers/auth_route.py`**: `POST /api/v1/auth/login` accepts JSON `{username, password}`, returns `Token {access_token, refresh_token, token_type: "bearer", user: UserPublic}`. `POST /api/v1/auth/refresh` accepts `{refresh_token}`. `GET /me` returns `CurrentUser`.
- **`backend_fastapi/app/shared/schemas.py`**: `LoginRequest {username: str, password: str}`, `Token {access_token, refresh_token, token_type, user: UserPublic}`.
- **`backend_fastapi/app/services/auth_service.py`**: Lockout after 5 failed attempts (15-min lock). Legacy scrypt → bcrypt lazy upgrade.
- **`backend_fastapi/app/shared/config.py`**: `ACCESS_TOKEN_EXPIRE_MINUTES=480` (8h), `REFRESH_TOKEN_EXPIRE_DAYS=30`. `SECRET_KEY` from env.
- **`backend_fastapi/app/services/seed_service.py`**: Seeds admin user: `username="admin"`, `password="admin123"`, `role_id=1`.
- **`backend_fastapi/app/main.py`**: CORS allows `http://localhost:3000` and `http://127.0.0.1:3000` with `allow_credentials=True`. Uniform error contract: `{"error": {"code", "message", "details"}}`.

### Tooling state

- Next.js: `^16.2.10` installed in `node_modules`.
- React: `^19.1.0` — `useActionState` available.
- TypeScript: `^5.8.3`.
- `postcss`: installed (transitive). `tailwindcss`: NOT installed. `autoprefixer`: NOT installed.
- `@/ ` path alias configured in `tsconfig.json`.
- No test framework configured for the frontend.

---

## 2. Design Decisions & Risks

### Decision 1: Install Tailwind CSS

The spec (Section 10.1) mandates Tailwind CSS utility classes. `app/page.tsx` already uses them. But Tailwind is NOT installed.

**Action:** Install `tailwindcss`, `postcss`, `autoprefixer` as dev dependencies. Create `tailwind.config.js` and `postcss.config.js`. Add `@tailwind base; @tailwind components; @tailwind utilities;` to `globals.css`.

**Risk:** Installing packages modifies `package.json` and `package-lock.json`. This is acceptable — Tailwind is required by the spec.

### Decision 2: Server Action vs. API Route

The spec says "Use Next.js Server Actions to set an HTTP-only cookie." Two approaches:

- **Server Action (`"use server"`)**: Uses `cookies()` from `next/headers` to set cookies. Invoked via `useActionState` with a `<form action={formAction}>`. Best for form-based submission with progressive enhancement.
- **API Route (`app/api/auth/login/route.ts`)**: Uses `res.cookies.set()` to set cookies. Invoked via `fetch` from client. Best for programmatic auth (e.g., `authStore.login()`).

**Chosen approach:** Both. Create `app/login/actions.ts` as the Server Action (primary login mechanism via `useActionState`). Create `app/api/auth/login/route.ts` as a route handler that the `authStore.login()` method can call programmatically. Both proxy to the same FastAPI endpoint and set the same cookies.

**Rationale:** The spec explicitly requires Server Actions. The existing `authStore.login()` uses Axios to call the backend directly — this needs to be refactored to call a Next.js API route instead (so cookies are set server-side). Both paths must exist.

### Decision 3: Auth store token storage strategy

Since HTTP-only cookies are NOT readable by client JavaScript, the Axios interceptor (`lib/api.ts`) cannot read the `access_token` from the cookie. Two options:

- **Option A:** Keep `access_token` in `localStorage` for the Axios interceptor, and ALSO set the HTTP-only cookie (the cookie is the "secure" store, localStorage is the "operational" store). The spec's requirement "set an HTTP-only cookie" is satisfied.
- **Option B:** Route ALL API calls through Next.js API routes that read the cookie server-side. This is a massive refactor beyond scope.

**Chosen approach:** Option A. The Server Action sets the HTTP-only `access_token` cookie + returns `access_token` in the response body. The client mirrors it to `localStorage` for the Axios interceptor. The `refresh_token` stays HTTP-only only (the refresh flow uses a `/api/auth/refresh` route that reads the cookie server-side).

**Rationale:** Surgical scope. The spec requires HTTP-only cookie storage (satisfied). The Axios interceptor pattern remains functional without a massive refactor. Future work can migrate to cookie-only.

### Decision 4: Redirect mechanism

The Server Action cannot call `redirect()` from `next/navigation` directly (it returns a state object, not a response). The client component must call `router.replace("/dashboard")` after the action returns `{success: true}`.

### Decision 5: Tailwind config scope

Add Tailwind to `package.json` `devDependencies` and `tailwind.config.js`. The `content` paths must include `./app/**/*.{ts,tsx}`, `./components/**/*.{tsx}`, `./hooks/**/*.{ts,tsx}`, `./stores/**/*.{ts,tsx}`, `./lib/**/*.{ts,tsx}`, `./types/**/*.{ts,tsx}`.

---

## 3. Tasks

### T1: Install Tailwind CSS & PostCSS configuration

**Files:**
- `package.json` (MODIFY → add `tailwindcss`, `autoprefixer` to `devDependencies`)
- `tailwind.config.js` (CREATE)
- `postcss.config.js` (CREATE)
- `app/globals.css` (MODIFY → add `@tailwind base; @tailwind components; @tailwind utilities;`)

**Action:**
1. `npm install -D tailwindcss postcss autoprefixer` (or manually edit `package.json` + `package-lock.json`).
2. Create `tailwind.config.js` with `content` array covering all `.tsx`/`.ts` files.
3. Create `postcss.config.js` with `module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } }`.
4. Prepend `@tailwind base; @tailwind components; @tailwind utilities;` to `app/globals.css`.

**Verify:** `npx tsc --noEmit` passes (no new type errors). Tailwind classes resolve in `app/page.tsx`.

---

### T2: Create Server Action for login (`app/login/actions.ts`)

**File:** `app/login/actions.ts` (CREATE)

**Action:**
- Mark `"use client"` — wait, no. Server Actions use `"use server"` at the top.
- Import `cookies` from `next/headers`, `fetch`, types `LoginRequest`, `UserPublic`.
- Define `loginAction(_prevState: LoginState | null, formData: FormData): Promise<LoginState>`.
- Extract `username` and `password` from `formData`.
- Validate: if empty, return `{error: "Username and password are required"}`.
- `fetch(`${API_BASE}/api/v1/auth/login`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({username, password}), cache: "no-store"})`.
- Catch network errors → return `{error: "Server unreachable"}`.
- If `!apiRes.ok`: extract `error.message` from backend uniform contract, return `{error: <msg>}`. For 401 specifically → "Invalid credentials".
- If success: `cookies()` → set `access_token` and `refresh_token` as HTTP-only, SameSite=Strict, conditional Secure, path="/", maxAge=480*60 and 30*24*60*60 respectively.
- Return `{success: true, user: data.user, access_token: data.access_token, refresh_token: data.refresh_token}`.

**Types:**
```ts
export interface LoginState {
  success?: boolean;
  error?: string;
  user?: UserPublic;
  access_token?: string;
  refresh_token?: string;
}
```

**Self-healing:** If `cookies()` API is unavailable or behaves differently in this Next.js version, fall back to setting cookies via `res.headers.append("Set-Cookie", ...)` in an API route. But per the spec, use Server Actions with `cookies()`.

---

### T3: Rewrite login page (`app/login/page.tsx`)

**File:** `app/login/page.tsx` (MODIFY — full rewrite)

**Action:**
- Keep `"use client"` (it uses `useActionState`, `useEffect`, `useRouter`).
- Import `useActionState` from `react`, `useRouter` from `next/navigation`, `loginAction` from `@/app/login/actions`, `useAuthStore` from `@/stores/authStore`.
- Use `useActionState(loginAction, null)` → `[state, formAction, isPending]`.
- `useEffect`: if `state?.success`: set `localStorage.setItem("access_token", state.access_token)`, call `useAuthStore.setUser(state.user)` (new method, sets minimal `CurrentUser` from `UserPublic` with `role: ""` and `permissions: []`), then `router.replace("/dashboard")`. Note: `setUser` only populates `id` and `username` from the login response — `role` and `permissions` are fetched lazily via `/me` when needed. For Phase 2 scope, RBAC permissions are not checked on `/dashboard`.
- If `state?.error`: display in red alert banner (`bg-red-100 text-red-800 rounded-md p-4 text-sm`).
- Form: `<form action={formAction}>` with `name="username"` and `name="password"` inputs, `disabled={isPending}`, submit button shows "Signing in…" when pending.
- Style with Tailwind CSS utility classes per Section 10.1.
- Replace `/pos` redirect with `/dashboard`.

**Critical:** The `<form action={formAction}>` pattern means the form submission is handled by the Server Action. Input fields use `name` attribute (not React state). No `onSubmit` handler needed — the form POSTs to the Server Action natively, and `useActionState` captures the return value.

---

### T4: Create API route for programmatic login (`app/api/auth/login/route.ts`)

**File:** `app/api/auth/login/route.ts` (CREATE)

**Action:**
- Export `POST(req: NextRequest)` handler.
- Parse JSON body `{username, password}`.
- `fetch` to FastAPI `/api/v1/auth/login`.
- On network error → return `{error: "Server unreachable"}` with status 502.
- On `!apiRes.ok` → return `{error: <normalized message>}` with backend status.
- On success → set HTTP-only cookies via `res.cookies.set()` + return `{success: true, user, access_token, refresh_token}`.

**Rationale:** `authStore.login()` uses `fetch` (not a Server Action), so it needs a route handler. The route handler duplicates the Server Action's logic but uses `res.cookies.set()` instead of `cookies()`.

---

### T5: Create API route for logout (`app/api/auth/logout/route.ts`)

**File:** `app/api/auth/logout/route.ts` (CREATE)

**Action:**
- Export `POST(req: NextRequest)` handler.
- Set `access_token` and `refresh_token` cookies to `""` with `maxAge: 0`.
- Return `{success: true}`.

---

### T6: Create API route for refresh (`app/api/auth/refresh/route.ts`)

**File:** `app/api/auth/refresh/route.ts` (CREATE)

**Action:**
- Export `POST(req: NextRequest)` handler.
- Read `refresh_token` cookie via `req.cookies.get("refresh_token")`.
- `fetch` to FastAPI `/api/v1/auth/refresh` with `{refresh_token}`.
- On success → set new `access_token` cookie + return `{access_token}`.
- On failure → return `{error: "..."}`, clear cookies.

---

### T7: Update auth store (`stores/authStore.ts`)

**File:** `stores/authStore.ts` (MODIFY)

**Action:**
- `login()`: POST to `/api/auth/login` (route from T4). The route returns `{success, user: UserPublic, access_token, refresh_token}`. On success: store `access_token` in `localStorage` (for Axios), then fetch `/api/v1/auth/me` via the `api` Axios instance to get `CurrentUser` (with `role` + `permissions`), set `token` + `user` in store. Throw on error.
- Add `setUser(user: UserPublic | null)`: sets `user` in store, constructing a minimal `CurrentUser` from `UserPublic` fields (`id`, `username`) with `role: ""` and `permissions: []`. Used by the login page's `useActionState` effect for immediate state sync.
- `logout()`: POST to `/api/auth/logout` (route from T5). Clear `localStorage`. Set `token=null, user=null`.

**Type mismatch flag:** `UserPublic` (from `types/contracts.ts`) has `role_id: number` but `CurrentUser` has `role: string` and `permissions: string[]`. The FastAPI `/login` endpoint returns `Token.user: UserPublic` (no `permissions` field). The `useAuthStore` currently stores `CurrentUser | null` (which has `role` + `permissions`).

**Chosen approach:** Keep the existing pattern — in `authStore.login()`, after storing tokens from the `/api/auth/login` response, fetch `/api/v1/auth/me` (via the `api` Axios instance) to get the `CurrentUser` with `role` + `permissions`. This matches the existing `authStore.login()` implementation (which calls `api.get("/api/v1/auth/me")` after login). The `setUser()` method accepts the login response's `user` (as `UserPublic`) for the immediate state update, but the full `CurrentUser` is fetched separately.

**Note:** `app/license/page.tsx` calls `isAuthenticated()` but does NOT call `hasPermission()`. The only caller of `hasPermission()` is `app/pos/page.tsx` (indirectly via route protection). So the `CurrentUser.permissions` field is only used for RBAC checks, which are not part of Phase 2 scope. The `setUser()` method should accept `UserPublic | null` and the store's `user` state remains `CurrentUser | null`. For the `setUser()` path (called from the login page's `useActionState` effect), only `id` and `username` are populated from `UserPublic`; `role` and `permissions` are fetched lazily via `/me`.

---

### T8: Update Axios interceptor (`lib/api.ts`)

**File:** `lib/api.ts` (MODIFY)

**Action:**
- Keep reading `access_token` from `localStorage` (set by `authStore.login`).
- On 401: POST to `/api/auth/refresh` (route from T6) instead of posting to FastAPI directly. The route reads the HTTP-only `refresh_token` cookie server-side.
- On successful refresh: store new `access_token` in `localStorage`, retry original request.
- On refresh failure: clear localStorage, reject.

---

### T9: Update middleware (`middleware.ts`)

**File:** `middleware.ts` (MODIFY)

**Action:**
- After existing currency logic, check `access_token` cookie.
- If path is `/login` and `access_token` exists → redirect to `/dashboard`.
- If path starts with `/dashboard` (or other protected routes) and no `access_token` → redirect to `/login`.
- Keep existing matcher config (it already excludes `/api/*`).

**Protected routes to guard:** `/dashboard`. Per the spec, only `/dashboard` is explicitly mentioned. Also consider `/pos`, `/inventory`, etc. — but these are out of scope for Phase 2. Guard `/dashboard` + any `/dashboard/*` subpath.

---

### T10: Create dashboard page (`app/dashboard/page.tsx`)

**File:** `app/dashboard/page.tsx` (CREATE)

**Action:**
- `"use client"` component.
- Check `useAuthStore().isAuthenticated()` — if false, redirect to `/login`.
- Display a minimal dashboard: title "Dashboard", a welcome message, and a logout button.
- Style with Tailwind CSS classes matching the login page aesthetic.

---

### T11: Update CHANGELOG.md

**File:** `CHANGELOG.md` (MODIFY)

**Action:**
- Add M8 entry: "Frontend Authentication Flow (Phase 2)" with:
  - Tailored login page with Tailwind CSS.
  - Server Actions with HTTP-only cookies.
  - Middleware protection for `/dashboard`.
  - Auth store + Axios interceptor refactor.
  - Verification: `npx tsc --noEmit` 0 errors, `npm run build` success.

---

## 4. Affected Files Summary

### Files to CREATE

| File | Purpose |
|------|---------|
| `tailwind.config.js` | Tailwind CSS configuration with content paths. |
| `postcss.config.js` | PostCSS configuration for Tailwind + Autoprefixer. |
| `app/login/actions.ts` | Server Action (`"use server"`) for login form submission. |
| `app/api/auth/login/route.ts` | API route for programmatic login (used by `authStore.login()`). |
| `app/api/auth/logout/route.ts` | API route to clear auth cookies. |
| `app/api/auth/refresh/route.ts` | API route to refresh tokens server-side (reads HTTP-only cookie). |
| `app/dashboard/page.tsx` | Minimal protected dashboard page. |

### Files to MODIFY

| File | Modification |
|------|-------------|
| `package.json` | Add `tailwindcss`, `autoprefixer`, `postcss` to `devDependencies`. |
| `app/globals.css` | Prepend `@tailwind base; @tailwind components; @tailwind utilities;`. |
| `app/login/page.tsx` | Full rewrite: Server Action form, Tailwind CSS, redirect to `/dashboard`. |
| `stores/authStore.ts` | `login()` POSTs to `/api/auth/login`; `logout()` POSTs to `/api/auth/logout`; add `setUser()` method. |
| `lib/api.ts` | Update 401 interceptor to POST to `/api/auth/refresh` (cookie-based). |
| `middleware.ts` | Add auth guard for `/dashboard` (check `access_token` cookie). |
| `CHANGELOG.md` | Add M8 entry. |

### Files to NOT touch

- `backend_fastapi/` — all backend files are verified complete (CHANGELOG M2).
- `backend/app.py` — Flask license service, isolated, must remain untouched.
- `pharmacy.db` — must not be modified.
- `.env`, `.env.local` — must not be modified.
- `run_services.py` — must not be modified.
- `app/layout.tsx`, `app/page.tsx` — must not be modified (only login page + new dashboard).
- `types/contracts.ts` — must not be modified (contracts are established).
- `package-lock.json` — updated automatically by `npm install`.

---

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Tailwind CSS not installed | Login page won't render correctly (classes won't apply) | T1 installs Tailwind + PostCSS. Verify with `npx tailwindcss -i app/globals.css -o .next/static/css/tailwind-output.css --watch` (or just `npm run build`). |
| `cookies()` API unavailable in Next.js 16.2.10 | Server Action can't set cookies | Fallback: use API route with `res.cookies.set()`. Verify by checking `next/headers` export at runtime. |
| `useActionState` not available in React 19.1.0 | Login form won't work | `useActionState` is stable in React 19 RC. Fallback: use `useState` + `fetch` if unavailable. |
| `UserPublic` → `CurrentUser` type mismatch | Store can't be updated with user from login | Use `login()` flow: after login, fetch `/api/v1/auth/me` to get `CurrentUser` with `role` + `permissions`. |
| Axios interceptor reading from `localStorage` while cookie is HTTP-only | Double storage, but functional | Documented as progressive improvement. Cookie is the secure store; localStorage is operational. |
| Middleware `access_token` cookie check | If cookie name differs, auth fails | Use `"access_token"` as cookie name (matching T3/T4). |
| Dev environment HTTP (no HTTPS) | `Secure` flag would prevent cookie in dev | Conditional: `secure: process.env.NODE_ENV === "production"`. |
| `authStore.login()` callers exist | `app/login/page.tsx` (being rewritten), `app/license/page.tsx` (not being changed) | The `authStore.login()` signature must remain compatible: `login(payload: LoginRequest): Promise<void>`. The new version calls `/api/auth/login` route internally. `app/license/page.tsx` calls `useAuthStore((s) => s.login)` and `isAuthenticated()` — these must still work. |

---

## 6. Validation Plan

### Type safety
1. `npx tsc --noEmit` → must pass with 0 errors.
2. All new files must be fully type-annotated. No `any` (use `unknown` with narrowing).

### Build
1. `npm run build` → must succeed (catches Server Action issues, Tailwind config errors).

### Lint
1. `npm run lint` → must pass with 0 warnings on new/changed files.

### Manual verification (requires running dev server + backend)
1. Start services: `python run_services.py` (starts FastAPI + Next.js).
2. Navigate to `http://localhost:3000/login`.
3. Verify Tailwind styles are applied (card layout, blue button, red error banner).
4. Submit empty form → HTML5 validation triggers (required fields).
5. Submit wrong credentials → "Invalid credentials" appears in red banner.
6. Submit `admin` / `admin123` → redirected to `/dashboard`.
7. Check cookies in DevTools → `access_token` and `refresh_token` are HTTP-only, SameSite=Strict.
8. Check `localStorage` → contains `access_token` (for Axios).
9. Navigate to `/dashboard` in incognito (no cookies) → redirected to `/login`.
10. Click logout → cookies cleared, `localStorage` cleared, redirected to `/login`.

### Backend integrity (no regressions)
1. `cd backend_fastapi && python -m pytest -q` → all 41 tests still pass.
2. `cd backend_fastapi && python -m mypy app --strict` → 0 errors.

---

## 7. Open Questions

None. All decisions are resolved in Section 4. The implementation can proceed directly.