# Phase 0 — DISCOVERY (release engineering, Phases 0–3)

Date: 2026-10-03 · Branch: `release/launch-prep` · Method: code inspection only; every claim cites `file:line`.

> **Playbook source note:** `SELL_PHARMACY_APP_PLAYBOOK.md` was **not found** anywhere in the repo
> (root + full-tree case-insensitive search). Phases 0–3 are being executed from the playbook text
> supplied in the task prompt. If a separate playbook file with extra detail exists, hand it over and
> it will be reconciled before Phase 1.

---

## 1. Tech stack — CONFIRMED

| Layer | Technology | Evidence |
|---|---|---|
| Desktop shell | **Tauri v2** — Rust `tauri 2.11.3`, plugins: updater/fs/dialog/process/shell/log; recovery sidecar binary | `src-tauri/Cargo.toml` (L24–L44) |
| UI | **Next.js ^16.3.3** (React 19), Tailwind 4, Zustand, TanStack Query, react-hook-form + zod | `package.json` |
| API | **FastAPI** (Python ≥3.12, SQLAlchemy 2 async, Pydantic v2, structlog, slowapi rate-limit) | `backend_fastapi/pyproject.toml` |
| Database | **SQLite** via `aiosqlite`; migrations = `PRAGMA user_version` blocks, **SCHEMA_VERSION 32** (not Alembic) | `backend_fastapi/app/core/database.py` |
| Packaging | PyInstaller-built backend + node as Tauri `externalBin` sidecars; NSIS + MSI targets; updater → GitHub `pharmacysuite` releases | `src-tauri/tauri.conf.json` |
| Ancillary | OCR: tesseract.js + pytesseract + paddleocr; QR/barcode: qrcode, jsbarcode; licensing: Paddle (server-side only) | `package.json`, `pyproject.toml`, `lib/license.ts` |

App identity: `productName: "Pharmacy Suite"`, `version: 1.0.0`, `identifier: com.pharmacysuite.app` (`src-tauri/tauri.conf.json` L3–L5).

## 2. App type — Windows desktop, offline-capable

- **Type:** Windows desktop app (Tauri v2; NSIS + MSI bundle targets; `tauri.conf.json` L39).
- **Offline:** YES for core operation — UI is Next standalone served locally, API is a local FastAPI sidecar, data is local SQLite. Network used only for: updates (GitHub releases updater), Paddle webhook licensing, LAN multi-terminal sync (signed UDP discovery, `mdns-sd`), optional Redis-backed license server.
- **Recovery:** standalone `pharmacysuite-recovery` binary works without WebView2/sidecars when the main app can't start (`src-tauri/Cargo.toml` L11–L16).

## 3. Patient data — YES, extensive PHI; ⚠️ plaintext at rest in live DB

- `Patient` model holds rich PHI: name, DOB, address, 3 phone fields, email, insurance provider/policy/group/plan, allergies, emergency contacts, ethnicity/race, prescriptions via `EPCSPrescription` (`backend_fastapi/app/core/models.py` L382–L430).
- **Storage:** local SQLite DB file. **Not encrypted at rest** — no SQLCipher / `PRAGMA key` anywhere.
- **DPAPI encryption exists but is NOT wired:** `phi_encrypt`/`phi_decrypt` (machine-bound DPAPI, B5) are defined in `backend_fastapi/app/shared/security.py` L338–L348 and **called from nowhere**. Only the PIN pepper and integration API keys use DPAPI/Fernet today.
- **Backups ARE encrypted:** AES-256-GCM (`.backup.enc`), key held by admin, plaintext intermediate deleted (`backend_fastapi/app/core/backup_crypto.py`; endpoints `POST /admin/backup/encrypted`, `POST /admin/restore/encrypted` in `app/api/routers/admin_route.py` L66, L162).
- **Pre-sale note (not a hardening re-do):** "PHI encrypted at rest" must NOT be claimed in marketing copy until B5 wiring ships. Copy should say "encrypted AES-256-GCM backups; data stays on your machine".

## 4. Login / users / roles / branches / languages

- **Auth:** bcrypt password hashing + JWT (pyjwt), HttpOnly cookie sessions (hardening Batch 3) — `backend_fastapi/app/shared/security.py`, `app/api/deps.py`.
- **First-run:** `GET /api/v1/setup/status` returns `setup_required` when 0 users; `POST /api/v1/setup/complete` (fresh DB only, rate-limited 5/min, server-side complexity check ≥12 chars mixed case+digit+symbol) creates the admin (role_id=1) + pharmacy profile. **No default admin password exists — owner creates their own** (`backend_fastapi/app/api/routers/setup_route.py`).
- **Setup gate:** every non-exempt API route returns 503 until `setup_complete` SystemSetting is flipped by an admin (`backend_fastapi/main.py` L442–L512).
- **RBAC:** `Role` + `RolePermission` tables; `_ALL_PERMISSIONS` seeded; `RolePermission` join (`backend_fastapi/app/core/models.py` L148–L165, `app/services/seed_service.py` L30).
- **Multi-branch:** NO — no branch/warehouse model found in `models.py`. Single-pharmacy per install. (LAN multi-terminal = multiple POS devices on one DB, not branches.)
- **Languages:** 6 UI locales — `ar, de, en, es, fr, pt` (`lib/i18n/locales/`). **Arabic RTL implemented** (`rtlLocales: ["ar"]`, `lib/i18n/config.ts` L17; applied in `app/layout.tsx` + `components/I18nProvider.tsx`).

## 5. Dependency license scan (preliminary — full report in Phase 1.1)

**BLOCKERS: none found.** Verification items: 2 below.

| Ecosystem | Result | Detail |
|---|---|---|
| npm (`license-checker --summary`) | ✅ No GPL / AGPL | `(MIT OR GPL-3.0-or-later)` ×1 → dual-licensed, MIT side usable. `Apache-2.0 AND LGPL-3.0-or-later(AND MIT)` ×2 → **identify packages in Phase 1.1** (LGPL in JS bundle = aggregation, normally fine for commercial sale; must allow relinking). |
| Python (`pip-licenses`) | ✅ No GPL/AGPL runtime deps | `pyinstaller` = **GPLv2 WITH bootloader exception** → explicitly permits distributing bundled commercial apps; build-time tool only, not shipped as library. `pyinstaller-hooks-contrib` = Apache-2.0 + GPLv2 (same exception context). `pharmacy-fastapi UNKNOWN` = our own package (add a license field). |
| Rust (Cargo.toml direct deps) | ✅ All permissive | tauri, tokio, serde, chrono, uuid, sha2/hmac, base64, http, sqlite, mdns-sd, windows-sys — MIT / Apache-2.0 dual or permissive. **Full transitive scan via `cargo-license` in Phase 1.1.** |

## 6. Pricing model — 2 options (CHOOSE ONE before Phase 2)

### Option A — One-time perpetual license ⭐ recommended for this market
**Shape:** $149 one-time per device · all updates + email support included for 12 months · optional $59/yr renewal to keep getting updates/support · the app itself never expires. 14-day free trial still possible on Freemius.
- **Pros:** matches how pharmacies in Egypt/Arab world prefer to buy (own it, no recurring card); easiest sale against "cracked" alternatives; revenue up front; zero churn anxiety; works even if buyer's card fails later.
- **Cons:** no recurring baseline; renewals need active marketing; 3-year LTV lower than a healthy subscription; underpricing risk.

### Option B — Subscription
**Shape:** 14-day free trial → $9/month or $89/year (~2 months free) · updates + support while active · if payment lapses: read-only access + data export (never locked out).
- **Pros:** recurring revenue; low entry point; predictable MRR; Freemius handles trials/dunning natively.
- **Cons:** recurring-card friction and distrust in Egypt; monthly cancellations; harder sell for an unknown publisher; churn in price-sensitive market.

**Agent recommendation:** Option A now; add an optional subscription tier later once there are paying customers. Final choice, plan names, and prices are the owner's call.

## 7. Target market + currency — NEEDS OWNER ANSWER

Options: (a) Egypt only, (b) Egypt + Arab world (Gulf incl. KSA/UAE — higher willingness to pay), (c) global.
Currency: Freemius sells in USD natively (local display + VAT handled by Freemius checkout; verify fees/URLs in Phase 3). EGP-only display would constrain checkout.

## 8. Branding — NEEDS OWNER ANSWER

Needed before Phase 2/3: app display name (current internal: "Pharmacy Suite" / "PharmacyPro" appears in code & license keys `PPRO-…`), publisher/legal name, support email, logo 512×512 PNG (Windows icon + store listing). Asked via structured questions; gaps become HUMAN_TODO items.

---

## 9. Existing licensing system (context for Phase 3.4)

- Server-side Paddle: `lib/license.ts` (Redis/Upstash-backed license records, key format `PPRO-XXXX-XXXX-XXXX`, device binding via `activated_device_id`), webhook `app/api/webhooks/paddle/route.ts`. No client-side Paddle script (CSP-clean after L6).
- `@paddle/paddle-js` + `@paddle/paddle-node-sdk` still in `package.json` dependencies; `paddle-js` import found only in `app/dashboard/invoice-parse/page.tsx` (naming overlap with PaddleOCR — re-verify before removing).
- Freemius integration plan (Phase 3.4) must define migration/coexistence for these.

## 10. Open questions → owner (Phase 0 gate)

1. Pricing: Option A or B (§6)?
2. Target market (§7)? 3. Buyer currency (§7)?
4. App display name? 5. Publisher name? 6. Support email? 7. Logo 512×512 ready?

**Phase 0 status: COMPLETE. Waiting for owner answers before Phase 1.**
