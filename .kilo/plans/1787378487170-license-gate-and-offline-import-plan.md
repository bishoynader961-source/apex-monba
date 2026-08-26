# Plan: License Gate Flag + Offline License File Import

**Status:** Planning complete — awaiting implementation
**Date:** 2026-08-22
**Tauri version:** 2.11.3 (`tauri-plugin-log`, `tauri-plugin-shell` currently installed; **no dialog/fs plugins**)

---

## 1. Context & Current State

### 1.1 Architecture
- **Frontend**: Next.js 16 + React 19 + TypeScript + Zustand + Axios, bundled by Tauri as a desktop sidecar (`src-tauri/`). Dev URL `http://127.0.0.1:3000`; release spawns `.next/standalone/server.js` on port 3000 and the FastAPI backend on port 8000.
- **Backend**: FastAPI (`backend_fastapi/`) + async SQLAlchemy 2.0 + SQLite. Layered: API → Services → Core (models/repos) → Shared (schemas, security, config, exceptions).
- **Tauri**: `Cargo.toml` has only `tauri-plugin-log` + `tauri-plugin-shell`. `@tauri-apps/api` npm package is **not installed** (only `@tauri-apps/cli` dev dep). CSP in `tauri.conf.json` allows `connect-src 'self' http://localhost:8000 http://127.0.0.1:8000`.

### 1.2 Current license state (no lock screen exists)
- `app/layout.tsx` — root server component, no license check.
- `middleware.ts` — auth-only gate (checks `access_token` cookie on protected routes), **no license enforcement**.
- `/dashboard` and `/pos` pages — auth-only (`useAuthStore.isAuthenticated()`), **no license gate**.
- `app/license/page.tsx` — manual key-entry form + Creem purchase button. **Not a lock screen.**
- `stores/licenseStore.ts` — has `validate(licenseKey, hardwareId)` but is **never auto-invoked** to gate routes.
- `lib/api/license.ts` — `validateLicense()` → `POST /api/v1/license/validate`; `initiateCheckout()` → `POST /api/v1/license/checkout`.
- `lib/deviceId.ts` — `getDeviceId()` reads/writes `localStorage["pp_device_id"]`.
- `backend_fastapi/.../license_route.py` — `POST /api/v1/license/validate` (checks local SQLite `licenses` table first, falls back to Flask `LICENSE_GATE_URL` proxy), `/checkout` (Creem), `/admin/manage`, `GET /status` (reachability only).
- `backend_fastapi/.../models.py` — `License` ORM: `license_key, email, status, created_at, expires_at, subscription_id, hardware_id, offline_until`.
- `backend_fastapi/.../repositories.py` — `LicenseRepository`: `get_by_key`, `create`, `update_status`, `extend_expires_at`, `bind_hardware`.

### 1.3 Confirmed design decisions
1. **Tauri config separation** — `${env:VAR:default}` substitution in `tauri.conf.json` for `productName` + `identifier`.
2. **License gate flag** — New `useLicenseGate` hook + `LicenseGate` component, bypassed when `NEXT_PUBLIC_REQUIRE_LICENSE === "false"`.
3. **Offline license file** — HMAC-SHA256 signed JSON (`.json`/`.lic`), validated via `LICENSE_SIGNING_SECRET`, saved to SQLite via `LicenseRepository`.
4. **Tauri file dialog** — `tauri-plugin-dialog` (open) + `tauri-plugin-fs` (readTextFile); button hidden in non-Tauri (web browser) context.

---

## 2. Scope

### In scope
- New `NEXT_PUBLIC_REQUIRE_LICENSE` env flag + license gate hook/component wrapping protected routes.
- New `POST /api/v1/licenses/activate-file` FastAPI endpoint with HMAC signature validation + SQLite persistence.
- Tauri config split (Test vs Prod identity) via env-var substitution.
- Tauri dialog + fs plugin wiring (`Cargo.toml`, `lib.rs`, `capabilities/default.json`).
- `@tauri-apps/api` npm dependency addition.
- "Import License File" button on the license activation UI.
- Frontend API function (`importLicenseFile`) + typed response contract.
- Backend + frontend tests.
- `.env.test` template + `.env.example` / `backend_fastapi/.env.example` updates.

### Out of scope
- No changes to existing `/api/v1/license/*` endpoints or the Flask proxy logic.
- No changes to Creem checkout flow or webhook handling.
- No changes to the legacy `license_gate.py` (CustomTkinter) — it is a separate legacy desktop app, not the Tauri/Next.js stack.
- No asymmetric RSA/ECDSA signing (HMAC-SHA256 with a backend secret is sufficient per user confirmation).
- No full audit of CORS/CSRF for the new endpoint beyond following existing patterns.

---

## 3. Design Decisions

### 3.1 Tauri Test vs Prod separation (Decision 1 — confirmed)
Use Tauri 2.x **environment-variable substitution** in `tauri.conf.json`:
```jsonc
"productName": "${env:TAURI_PRODUCT_NAME:PharmacySuite}",
"identifier": "${env:TAURI_BUNDLE_IDENTIFIER:com.pharmacy.suite}"
```
- **Prod** (default): `PharmacySuite` / `com.pharmacy.suite`.
- **Test**: set `TAURI_PRODUCT_NAME=Pharmacy POS Test` + `TAURI_BUNDLE_IDENTIFIER=com.pharmacy.pos.test` when invoking `tauri dev` / `tauri build`.

### 3.2 License gate hook (Decision 2 — confirmed)
- `NEXT_PUBLIC_REQUIRE_LICENSE` is a build-time inlined Next.js env var (per `.env.example` docs: "Set these BEFORE `npm run build`").
- Hook `useLicenseGate(pathname)` logic:
  1. `requireLicense = process.env.NEXT_PUBLIC_REQUIRE_LICENSE !== "false"`.
  2. `shouldGate = requireLicense && LICENSED_PATHS.some(p => pathname.startsWith(p))` where `LICENSED_PATHS = ["/dashboard", "/pos"]`.
  3. If `!shouldGate` → `{ loading: false, licensed: true }` (render children).
  4. If `shouldGate` → read `localStorage["pp_license_key"]`. If absent → `{ licensed: false }`. If present → call `validateLicense(licenseKey, getDeviceId())`; on success → licensed; on error → not licensed.

### 3.3 Offline license file format (Decision 3 — confirmed)
HMAC-SHA256 signed JSON. Extensions: `.json` and `.lic` (both JSON).

**Canonical fields (everything except `signature`):**
```jsonc
{
  "license_key": "PHARM-XXXX-XXXX-XXXX",
  "email": "customer@example.com",
  "expires_at": "2027-01-01T00:00:00Z",
  "status": "active",            // 'active' | 'revoked' | 'expired' | 'grace'
  "hardware_id": "device-fingerprint",  // optional — if present, must match requesting device
  "issued_at": "2026-08-22T00:00:00Z"
}
```

**Signature**: `hex(hmac_sha256(LICENSE_SIGNING_SECRET, canonical_json))` where `canonical_json = json.dumps(fields_except_signature, sort_keys=True, separators=(",", ":"))`.

**Backend validation flow:**
1. Parse JSON, extract `signature`, canonicalize remaining fields.
2. Recompute HMAC with `settings.license_signing_secret`; `hmac.compare_digest`. Mismatch → `403 license_signature_invalid`.
3. Validate `license_key` format (`PHARM-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}`). Invalid → `400`.
4. Check `expires_at` (ISO parse, `Z` → `+00:00`). Expired → `403 license_expired`.
5. Check `hardware_id`: if present in file, must match the `hardware_id` sent in the request body (from the client's `getDeviceId()`). Mismatch → `403 hardware_mismatch`. If absent, bind to the requesting device.
6. Persist: `LicenseRepository.create()` if the key doesn't exist; otherwise `update_status` + `bind_hardware` (idempotent). Set `offline_until = now + LICENSE_OFFLINE_GRACE_HOURS`.
7. Return `LicenseValidationResult` (mirrors `LicenseValidationResult` Pydantic schema).
8. Frontend persists `license_key` to `localStorage["pp_license_key"]` on success.

### 3.4 Tauri file dialog (Decision 4 — confirmed)
- Rust plugins: `tauri-plugin-dialog` (open picker) + `tauri-plugin-fs` (readTextFile).
- JS bindings: `@tauri-apps/api` npm package (imports `@tauri-apps/api/dialog` + `@tauri-apps/api/fs`).
- Capabilities: add `"dialog:allow-open"` + `"fs:allow-read"` + `fs:scope` allow-list (`$DOWNLOAD/*`, `$DESKTOP/*`, `$DOCUMENT/*`) to `capabilities/default.json` (see G2 — without the scope, `readTextFile` throws `PermissionDenied` on files from user directories).
- Non-Tauri fallback: In a plain browser, the "Import License File" button is hidden and a message "License file import is available in the desktop app" is shown. Detection: `typeof window !== "undefined" && "__TAURI__" in window`.

### 3.5 Endpoint path note
The user specified `/api/v1/licenses/activate-file` (plural `licenses`), but the existing router prefix is `/api/v1/license` (singular). To honor the user's exact path **without** breaking existing `/api/v1/license/*` routes, the `activate-file` handler will be registered on a **separate router** with `prefix="/api/v1/licenses"` in a new file `backend_fastapi/app/api/routers/license_file_route.py`, included in `main.py`. (An alternative — using the singular prefix `/api/v1/license/activate-file` — would be more consistent but deviates from the user's spec. Flagged as a consideration but not a blocker.)

---

## 4. Affected Files (ordered)

### 4.1 Tauri & environment
| File | Action | Change |
|------|--------|--------|
| `src-tauri/tauri.conf.json` | **Modify** | `productName` → `${env:TAURI_PRODUCT_NAME:PharmacySuite}`; `identifier` → `${env:TAURI_BUNDLE_IDENTIFIER:com.pharmacy.suite}` |
| `src-tauri/Cargo.toml` | **Modify** | Add `tauri-plugin-dialog = "2"` + `tauri-plugin-fs = "2"` to `[dependencies]` |
| `src-tauri/src/lib.rs` | **Modify** | `.plugin(tauri_plugin_dialog::init())` + `.plugin(tauri_plugin_fs::init())` in the builder chain |
| `src-tauri/capabilities/default.json` | **Modify** | Add `"dialog:allow-open"`, `"fs:allow-read"`, and an `fs:scope` allow-list block (`$DOWNLOAD/*`, `$DESKTOP/*`, `$DOCUMENT/*`) to `permissions` |
| `package.json` | **Modify** | Add `@tauri-apps/api` to `dependencies` (v2, matching `@tauri-apps/cli` ^2) |
| `.env.test` (new) | **Create** | `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, `NEXT_PUBLIC_REQUIRE_LICENSE=false`, `NEXT_PUBLIC_PADDLE_CLIENT_TOKEN=` (commented) |
| `.env.example` (root) | **Modify** | Add `NEXT_PUBLIC_REQUIRE_LICENSE=true` (documented as build-time inlined; default is enforce) |
| `backend_fastapi/.env.example` | **Modify** | Add `LICENSE_SIGNING_SECRET=` (documented) |
| `backend_fastapi/app/shared/config.py` | **Modify** | Add `license_signing_secret: SecretStr` field with `alias="LICENSE_SIGNING_SECRET"` (default empty → HMAC always fails in dev until set) |

### 4.2 Backend (FastAPI)
| File | Action | Change |
|------|--------|--------|
| `backend_fastapi/app/shared/schemas.py` | **Modify** | Add `LicenseFileRequest { hardware_id: str, file_content: str }` |
| `backend_fastapi/app/api/routers/license_file_route.py` (new) | **Create** | `POST /api/v1/licenses/activate-file` — HMAC validation + SQLite persistence via `LicenseRepository` + `settings.license_signing_secret` |
| `backend_fastapi/app/core/repositories.py` | **Inspect** | `LicenseRepository` already has `create`, `get_by_key`, `bind_hardware`, `update_status` — **no new methods needed** (reuse). Verify `License` model fields cover `offline_until` (they do, per `models.py:351`). |
| `backend_fastapi/app/main.py` | **Modify** | `from app.api.routers.license_file_route import router as license_file_router` + `app.include_router(license_file_router)` |
| `backend_fastapi/tests/test_license_file_import.py` (new) | **Create** | Tests: valid file creates license; bad HMAC → 403; expired → 403; HWID mismatch → 403; malformed → 400; idempotent re-import; 410 on revoked |

### 4.3 Frontend (Next.js / Tauri)
| File | Action | Change |
|------|--------|--------|
| `types/contracts.ts` | **Modify** | Add `LicenseFileResponse` interface (mirrors backend `LicenseValidationResult.`); add `LicenseFileRequest` TS type for the API call |
| `lib/api/license.ts` | **Modify** | Add `importLicenseFile(hardwareId, fileContent)` → `POST /api/v1/licenses/activate-file`; persist `pp_license_key` to localStorage on success |
| `hooks/useLicenseStore.ts` | **Modify** | After successful `validate()`, persist `licenseKey` to `localStorage["pp_license_key"]` (so the gate can re-validate on reload) |
| `hooks/useLicenseGate.ts` (new) | **Create** | License gate hook (see §3.2) — checks `NEXT_PUBLIC_REQUIRE_LICENSE`, pathname, persisted key, calls `validateLicense` |
| `components/LicenseGate.tsx` (new) | **Create** | Client component: renders `<LoadingSplash>` while checking; redirects to `/license` if not licensed + shouldGate; renders children otherwise |
| `app/layout.tsx` | **Modify** | Import + wrap `{children}` in `<LicenseGate>` |
| `app/license/page.tsx` | **Modify** | Add "Import License File (.json / .lic)" button — uses `@tauri-apps/api/dialog` `open()` + `@tauri-apps/api/fs` `readTextFile()`; on success calls `importLicenseFile`, redirects to `/dashboard`; shows error toast; in non-Tauri context shows disabled message |
| `components/LoadingSplash.tsx` (new, minimal) | **Create** | Simple "Loading …" splash for gate loading state |

### 4.4 PROJECT_MAP.md / FLOW_LOGIC.md
| File | Action | Change |
|------|--------|--------|
| `PROJECT_MAP.md` | **Modify** (documentation) | Add entries to `[TEACH_STACK]` + `[SYSTEM_FLOW]` for the license gate + file import; update ORPHANS/PENDING |
| `FLOW_LOGIC.md` | **Modify** (documentation) | Add license gate bypass flow + offline file import data flow |

---

## 5. Data Flow

### 5.1 License gate (page load)
```
App mount (app/layout.tsx)
  → LicenseGate component (client)
    → usePathname() → pathname
    → useLicenseGate(pathname)
      ├─ NEXT_PUBLIC_REQUIRE_LICENSE === "false" → licensed=true (bypass)
      └─ else + pathname starts with /dashboard or /pos
         → localStorage["pp_license_key"]?
            ├─ none → licensed=false → router.replace("/license")
            └─ present → validateLicense(key, getDeviceId())
               ├─ 200 → licensed=true → render children
               └─ 4xx/5xx → licensed=false → router.replace("/license")
```

### 5.2 License key activation (manual entry)
```
User enters key on /license → useLicenseStore.validate(key, hwId)
  → lib/api/license.ts:validateLicense() → POST /api/v1/license/validate
  → Backend checks local SQLite first, Flask fallback
  → On success: store.status set + localStorage["pp_license_key"] = key
```

### 5.3 Offline license file import
```
User clicks "Import" on /license (Tauri context only)
  → @tauri-apps/api/dialog:open() → file path
  → @tauri-apps/api/fs:readTextFile(path) → raw fileContent (string)
  → lib/api/license.ts:importLicenseFile(hwId, fileContent)
    → POST /api/v1/licenses/activate-file { hardware_id, file_content }
      → Backend: parse JSON, HMAC verify, check expiry/HWID
        → LicenseRepository.create() or update_status() + bind_hardware()
        → Return LicenseValidationResult
  → On success: localStorage["pp_license_key"] = result.license_key
    → Success → router.replace("/dashboard")
  → On error: setError(msg)
```

---

## 6. Implementation Steps (ordered, sequential)
> **Critical gotchas (apply throughout — see §12 for details):**
> - **G1 Build-time inlining**: `NEXT_PUBLIC_*` is baked into the JS bundle at build time. Clean `.next/` when toggling the flag between Test/Prod.
> - **G2 Tauri capabilities + fs scopes**: `capabilities/default.json` must grant `dialog:allow-open`, `fs:allow-read`, AND an `fs:scope` allow-list for `$DOWNLOAD/*`, `$DESKTOP/*`, `$DOCUMENT/*` — otherwise `readTextFile()` throws `PermissionDenied` when reading files from user directories.
> - **G3 Timezone awareness**: Backend must compare `expires_at` against `datetime.now(timezone.utc)`, never naive local time.
> - **G4 Offline grace**: `activate-file` must set `offline_until`; the `/validate` and gate-check paths must respect it.

> Each step → verify → move to next.

**Step 1 — Backend: config + schemas** [G3 applies to expiry checks in Step 2]
- Add `license_signing_secret` to `config.py` (`SecretStr`, `alias="LICENSE_SIGNING_SECRET"`, default `SecretStr("")`).
- Add `LicenseFileRequest` Pydantic schema to `schemas.py` `{ hardware_id: str, file_content: str }`.

**Step 2 — Backend: activate-file endpoint** [G3 + G4 apply]
- Create `license_file_route.py` with `router = APIRouter(prefix="/api/v1/licenses", tags=["license-file"])`.
- `POST /activate-file`: auth-required (`get_current_user`), session dep, parse + HMAC validate + persist via `LicenseRepository`.
- **G3**: Use `datetime.now(timezone.utc)` for all expiry/`offline_until` comparisons — never naive `datetime.now()`.
- **G4**: `LicenseRepository.create()` must set `offline_until = datetime.now(timezone.utc) + timedelta(hours=settings.license_offline_grace_hours)` so offline gate checks work.
- Register in `main.py`.

**Step 3 — Backend: tests**
- Create `tests/test_license_file_import.py` covering: valid signature+expiry → 200 + DB row; bad HMAC → 403; expired → 403; HWID mismatch → 403; malformed JSON → 400; idempotent re-import; revoked status file → 403.

**Step 4 — Tauri: plugins + config** [G2 applies — capabilities are strict]
- Add `tauri-plugin-dialog` + `tauri-plugin-fs` to `Cargo.toml`.
- Wire `.plugin(tauri_plugin_dialog::init())` + `.plugin(tauri_plugin_fs::init())` in `lib.rs`.
- **G2**: Add `"dialog:allow-open"` + `"fs:allow-read"` + `fs:scope` allow-list (`$DOWNLOAD/*`, `$DESKTOP/*`, `$DOCUMENT/*`) to capabilities — Tauri silently blocks file reads from user directories without the scope.
- Update `tauri.conf.json` with env-var substitution for `productName` + `identifier`.
- Add `@tauri-apps/api` to `package.json` (v2, matching `@tauri-apps/cli` ^2).

**Step 5 — Frontend: contracts + API service**
- Add `LicenseFileResponse` + `LicenseFileRequest` types to `types/contracts.ts`.
- Add `importLicenseFile()` to `lib/api/license.ts`.
- Modify `useLicenseStore.validate()` to persist `license_key` to localStorage on success.

**Step 6 — Frontend: license gate**
- Create `hooks/useLicenseGate.ts`.
- Create `components/LicenseGate.tsx` + `components/LoadingSplash.tsx`.
- Wrap `{children}` in `<LicenseGate>` in `app/layout.tsx`.

**Step 7 — Frontend: file import button**
- Add "Import License File" button to `app/license/page.tsx` with Tauri dialog + fs API; non-Tauri fallback (hidden/disabled message).

**Step 8 — Env files + docs** [G1 applies — Next.js build-time inlining]
- Create `.env.test` template with `NEXT_PUBLIC_REQUIRE_LICENSE=false`.
- **G1**: When switching between Test (`false`) and Prod (`true`/unset) modes, clean the `.next/` cache (`rm -rf .next`) or run a fresh `next build` so the `NEXT_PUBLIC_REQUIRE_LICENSE` flag is re-inlined into the bundle. Running `tauri dev` with a new env var but a cached `.next` will use the stale inlined value.
- Update `.env.example` (root) + `backend_fastapi/.env.example` with new vars.
- Update `PROJECT_MAP.md` + `FLOW_LOGIC.md`.

**Step 9 — Validation** [G1 + G2 + G3 + G4 apply]
- Backend: `pytest tests/test_license_file_import.py -v` (all pass); `mypy app --strict` (0 errors).
- Frontend: `npx tsc --noEmit` (0 errors); `npx next build` (all pages). **G1**: if flag toggle didn't take effect, clean `.next/` first.
- Tauri config: validate `tauri.conf.json` is valid JSON; confirm env-var substitution syntax. **G2**: verify `dialog:allow-open`, `fs:allow-read`, AND `fs:scope` ($DOWNLOAD/*, $DESKTOP/*, $DOCUMENT/*) in capabilities — Tauri silently denies file reads from user directories without the scope.
- E2E manual: Start Test build with `NEXT_PUBLIC_REQUIRE_LICENSE=false` → `/dashboard` accessible without license; start Prod build → redirected to `/license`. **G1**: ensure `.next/` is clean between toggles.

---

## 7. Testing & Validation

### 7.1 Backend tests (`backend_fastapi/tests/test_license_file_import.py`)
Uses existing `client` + `session` fixtures (in-memory SQLite). Helper `_signed_license_file(payload_dict)` computes the HMAC using `settings.license_signing_secret`.

| Test | Assert |
|------|--------|
| `test_activate_file_valid` | 200, license row created in DB with correct hardware_id binding |
| `test_activate_file_bad_signature` | 403, `error.code == "license_signature_invalid"` |
| `test_activate_file_expired` | 403, `error.code == "license_expired"` |
| `test_activate_file_hwid_mismatch` | 403, `error.code == "hardware_mismatch"` |
| `test_activate_file_malformed_json` | 400, `validation_error` |
| `test_activate_file_idempotent` | Re-import same file → 200, no duplicate row |
| `test_activate_file_requires_auth` | No bearer token → 401 |

### 7.2 Frontend tests (`vitest`)
| Test file | Test | Assert |
|-----------|------|--------|
| `hooks/useLicenseGate.test.ts` | `test_bypass_when_require_license_false` | With flag "false", `licensed=true, loading=false` for `/dashboard` |
| `hooks/useLicenseGate.test.ts` | `test_enforce_redirects_without_key` | With flag "true" and no stored key, `licensed=false` |
| `lib/api/license.test.ts` (or inline) | `test_import_license_file_posts_correct_body` | Mock axios, verify POST to `/api/v1/licenses/activate-file` with `{hardware_id, file_content}` |

### 7.3 Build & type validation
```bash
# Frontend
cd "E:\my progam pharmacy"
npx tsc --noEmit          # 0 errors
npx next build            # all pages compile

# Backend
cd backend_fastapi
python -m mypy app --strict    # 0 errors
python -m pytest tests/test_license_file_import.py -v  # all pass

# Tauri config
python -c "import json; json.load(open('src-tauri/tauri.conf.json'))"  # valid JSON
```

---

## 8. Risks & Rollback

| Risk | Mitigation |
|------|-----------|
| `NEXT_PUBLIC_REQUIRE_LICENSE` is build-time inlined — changing it requires a rebuild | Document clearly: dev = set in `.env.local`; Tauri dev picks it up from `.env.local` automatically; Tauri build requires `next build` with the env set. |
| Tauri env-var substitution requires the vars at Tauri build/dev time, not just Next.js | The env vars serve **two** purposes: (a) Tauri identity (`TAURI_PRODUCT_NAME`, `TAURI_BUNDLE_IDENTIFIER`) — set in shell when running `tauri dev`/`tauri build`; (b) Next.js license bypass (`NEXT_PUBLIC_REQUIRE_LICENSE`) — set in `.env.local` for `npm run dev`. Document both. |
| `@tauri-apps/api` not currently in node_modules | Add to `package.json` deps; run `npm install`. Version must match `@tauri-apps/cli` ^2. |
| Plural prefix `/api/v1/licenses` vs singular `/api/v1/license` | Flagged in §3.5. Separate router avoids breaking existing routes. |
| License file HMAC secret must be kept secret | Generated at install via `secrets.token_urlsafe(48)` if not set; persisted to backend env. Empty default in dev → all imports fail (fail-closed). |
| `LicenseGate` wraps all routes in root layout | Component checks `usePathname()` and only gates `/dashboard` + `/pos`; other routes render children directly. |
| Tauri dialog only works in desktop build | Non-Tauri (web browser) → button hidden with explanatory message. |
| CSP blocks `@tauri-apps/api` internal communication | `@tauri-apps/api` uses a custom protocol (`tauri://`), not `connect-src`. The existing CSP `connect-src 'self' http://localhost:8000` is unchanged and does not block Tauri internal IPC. No CSP change needed. |

### Rollback
- Remove new files; revert `app/layout.tsx`, `licenseStore.ts`, `config.py`, `main.py`, `Cargo.toml`, `tauri.conf.json`, `capabilities/default.json`, `package.json`.
- Existing license flow (`/api/v1/license/validate`, `/checkout`) is untouched.

---

## 9. Open Questions (resolved / N/A)

- **Q: "Existing license check enforcement"** — Confirmed: **none exists** in the frontend. A new gate is being created from scratch.
- **Q: License file signing** — Resolved: HMAC-SHA256 with `LICENSE_SIGNING_SECRET`.
- **Q: Browser fallback for file dialog** — Resolved: button hidden + message in non-Tauri context.
- **Q: Auth on activate-file** — Resolved: requires `get_current_user` (JWT bearer), consistent with existing `/api/v1/license/*` routes.

---

## 10. Success Metrics (verifiable goals)

| # | Criterion | Verification |
|---|-----------|--------------|
| G1 | Test build uses distinct identity | `tauri dev` with `TAURI_PRODUCT_NAME="Pharmacy POS Test"` shows "Pharmacy POS Test" as window title; bundle identifier is `com.pharmacy.pos.test` |
| G2 | Bypass flag works | With `NEXT_PUBLIC_REQUIRE_LICENSE=false`, navigating to `/dashboard` renders the dashboard without redirect to `/license` |
| G3 | Enforcement works | With `NEXT_PUBLIC_REQUIRE_LICENSE=true` and no valid license in localStorage, navigating to `/dashboard` redirects to `/license` |
| G4 | File import end-to-end | Select a valid signed `.json` file in Tauri → backend returns 200, license row exists in SQLite, `pp_license_key` set in localStorage, redirect to `/dashboard` |
| G5 | Bad signature rejected | Tauri file dialog selects a tampered file → 403 `license_signature_invalid`, error shown in UI |
| G6 | Non-Tauri fallback | In a plain browser, the "Import License File" button is hidden and a message is shown |
| G7 | Backend tests | `pytest tests/test_license_file_import.py -v` → all pass |
| G8 | Frontend types | `npx tsc --noEmit` → 0 errors |
| G9 | Backend types | `mypy app --strict` → 0 errors |
| G10 | Tauri config valid | `tauri.conf.json` is valid JSON; env-substitution syntax is correct |

---

## 11. Rollout / Migration Path

1. **Phase 1 (backend)**: Deploy new `activate-file` endpoint + config field. No breaking changes to existing routes. Empty `LICENSE_SIGNING_SECRET` default = fail-closed (safe).
2. **Phase 2 (Tauri config)**: Update `tauri.conf.json` + `Cargo.toml` + `lib.rs`. Requires `cargo tauri dev` with env vars for Test, or plain `tauri dev` for Prod (defaults).
3. **Phase 3 (frontend)**: Add gate hook + component + layout wrapper + import button. Gate is a no-op when `NEXT_PUBLIC_REQUIRE_LICENSE` is unset/"true" AND no license_key is in localStorage (existing behavior preserved for authenticated users who have already activated).
4. **Phase 4 (env)**: Distribute `.env.test` template to dev team. Document Test vs Prod startup commands.

**Startup commands (documented in plan, not automated):**
```bash
# Test build (bypass license, distinct identity)
$env:NEXT_PUBLIC_REQUIRE_LICENSE="false"
$env:TAURI_PRODUCT_NAME="Pharmacy POS Test"
$env:TAURI_BUNDLE_IDENTIFIER="com.pharmacy.pos.test"
tauri dev

# Prod build (enforce license)
tauri dev   # or: tauri build
```

For `npm run dev` (web-only, no Tauri): set `NEXT_PUBLIC_REQUIRE_LICENSE=false` in `.env.local` to bypass during pure web dev.

---

## 12. Implementation Gotchas (critical — do not skip)

### G1. Next.js Build-Time Inlining (`NEXT_PUBLIC_*`)
`NEXT_PUBLIC_*` env vars are **baked into the JS bundle at build time**, not read from the environment at runtime. The flag `NEXT_PUBLIC_REQUIRE_LICENSE` is resolved during `next build` (the `beforeBuildCommand` in `tauri.conf.json`) or `next dev` (the `beforeDevCommand`).

**Practical impact:**
- Setting `$env:NEXT_PUBLIC_REQUIRE_LICENSE="false"` in PowerShell and then running `tauri dev` will **not** change the flag if `.next/` already has a cached build from a previous `NEXT_PUBLIC_REQUIRE_LICENSE=true` run.
- **Fix:** Always clean the Next.js cache before toggling the flag:
  ```powershell
  Remove-Item -Recurse -Force .next
  $env:NEXT_PUBLIC_REQUIRE_LICENSE="false"
  tauri dev
  ```
- For `npm run dev` (non-Tauri web), Next.js auto-loads `.env.local` on each dev-server start, so changes to `.env.local` take effect without a full clean — but the **first** `tauri build` for production must use the prod env.

### G2. Tauri v2 Strict Capabilities + Filesystem Scopes
Tauri 2.x enforces a **rigid capabilities-based security model**. The `src-tauri/capabilities/default.json` must explicitly grant every plugin permission **and** scope. If even one permission or scope line is missing, Tauri **silently blocks** the API call at runtime (no error in the JS console in some cases).

**The One Critical Concern — Filesystem Scopes:**
The plan's original G2 listed `fs:allow-read` as sufficient. That is **incorrect** for Tauri v2. Granting `fs:allow-read` only permits reading files within **app-specific directories** (`$APP`, `$APPDATA`). When a user selects a license file from their `Downloads`, `Desktop`, or `Documents` folder via the dialog, `readTextFile()` throws a `PermissionDenied` error because those folders fall outside the default filesystem scope.

**Required entries in `capabilities/default.json`:**
```jsonc
"permissions": [
  "core:default",
  "shell:allow-execute",
  "shell:allow-spawn",
  "shell:allow-stdin-write",
  "dialog:allow-open",     // ← REQUIRED for file picker
  "fs:allow-read",         // ← REQUIRED for readTextFile
  {
    "identifier": "fs:scope",   // ← REQUIRED: path scopes for user directories
    "allow": [
      "$DOWNLOAD/*",
      "$DESKTOP/*",
      "$DOCUMENT/*"
    ]
  }
]
```
Alternatively, grant `fs:read-all` (via `"fs:allow-read-all"` permission) for unrestricted file reading through the dialog — simpler but less secure; use only if the scope entries above prove insufficient during testing.

Additionally, `src-tauri/src/lib.rs` must register both plugins:
```rust
.plugin(tauri_plugin_dialog::init())
.plugin(tauri_plugin_fs::init())
```
**Check after build:** Attempt the file dialog → select a file from Downloads → if `readTextFile()` throws `PermissionDenied`, re-check both the `permissions` array AND the `fs:scope` allow list. The scope entries use Tauri 2.x path variables (`$DOWNLOAD`, `$DESKTOP`, `$DOCUMENT`) which resolve at runtime per-platform.

### G3. Timezone Awareness in Python (UTC enforcement)
The dev environment is Egypt (UTC+2). The signed license file uses `Z` (UTC) timestamps. If the backend compares `expires_at` against **naive local time** (`datetime.now()`), a license expiring at `2026-12-31T23:59:59Z` would be evaluated against local time and could trigger "expired" 2 hours early.

**Fix in `activate-file` handler:**
```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)  # ALWAYS timezone-aware UTC
expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
if expires < now:
    raise HTTPException(403, "License has expired")
```
**Apply consistently** in every timestamp comparison (expiry, `offline_until` grace).

### G4. Offline Grace Period (`offline_until`)
When a license is imported offline via `activate-file`, the backend must set `offline_until` so the device can continue operating without reaching an external license server. The existing `LICENSE_OFFLINE_GRACE_HOURS` setting (default 72, from `config.py:101`) controls this duration.

**Fix:**
- `LicenseRepository.create()` already sets `offline_until = now + grace_hours` (verified in `repositories.py:603-613`). The `activate-file` handler must use this same path or replicate it.
- The gate's license check (`validateLicense` → backend `/validate`) must respect `offline_until`: if the license row has `offline_until > now`, treat as valid even if the key's `expires_at` is past (grace period). This is already handled by the existing `/validate` logic on `license_route.py:39-47` (local DB check), but verify the `LicenseValidationResult` returned includes `offline_until` so the frontend can display a countdown.

