# Pre-Sale Audit — Phase 1 (release/launch-prep, 2026-10-03)

Security-hardening items H1–H2, M1–M9, L1–L7 (PRs #30–#34) are out of scope here — see `release/SECURITY_HARDENING_COMPLETE.md`.

## BLOCKERS

**None found.** One pre-sale **manual gate** (cannot be executed in this environment) is tracked in HUMAN_TODO.md:

- **L3 — Clean-machine install test** (no Node/Python/Rust on the target machine). Must pass before shipping the installer. Details + steps: HUMAN_TODO.md §L3.

## Checklist results

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Full pytest suite ≥917 passing, 0 new failures | ✅ PASS | `917 passed, 1 skipped` in 270s (exit 0); unchanged from post-#34 baseline |
| 2 | `cargo check` 0 errors | ✅ PASS | 0 errors; 6 pre-existing warnings (known baseline, `cargo fix` suggestions only) |
| 3 | `tsc --noEmit` clean | ✅ PASS | exit 0, no output |
| 4 | Frontend unit tests (supporting) | ✅ PASS | vitest: **54/54** across 13 files |
| 5 | Arabic / RTL present & wired | ✅ PASS (code level) | `rtlLocales = ["ar"]` (`lib/i18n/config.ts` L17); `dir=rtl` applied **pre-paint** (`app/layout.tsx` L50) and on locale switch (`components/I18nProvider.tsx` L33/L41); 6 locales with **key-parity test** across all of them (`lib/i18n/i18n.test.ts`). Visual RTL confirmation folds into the screenshot task (HUMAN_TODO §L4) — capture at least 2 Arabic-RTL screens. |
| 6 | Hardcoded locale/timezone beyond L7 | ✅ PASS | No `datetime.utcnow`/`utcnow()` in app code; no `ZoneInfo`/`pytz`/fixed-offset zones. UI dates via `toLocaleDateString/TimeString` (viewer-local) and `Intl.DateTimeFormat(locale, …)` (`lib/formatting.ts`) — locale-aware, no assumptions found. |
| 7 | Hardcoded user paths (`C:\Users\…`, `/home/…`) | ✅ PASS | grep over `*.py *.ts *.tsx *.rs` in app code: **0 hits** |
| 8 | First-run wizard forces owner-created admin password | ✅ PASS (code level) | `POST /api/v1/setup/complete` only works when user count is 0; server-side password complexity (≥12 chars, mixed case, digit, symbol); rate-limited 5/min; no default credentials (`backend_fastapi/app/api/routers/setup_route.py`). All non-exempt routes return 503 until setup completes (`main.py` L442–L512). Real-machine confirmation folds into HUMAN_TODO §L3. |
| 9 | Backup → restore E2E | ✅ PASS | (a) Automated: `test_encrypted_backup_route_and_restore` (backup 201 → restore 200 → wrong key 400) — included in the 917. (b) File-level round-trip on the demo dataset (this session): `vacuum_backup` → AES-256-GCM `.backup.enc` (17,004 B) → `decrypt_to_gzip_bytes` → `gunzip_to_db_bytes` → fresh DB → **identical** counts (20 products / 5 patients / 10 receipts / 21 items / 2 suppliers / 1 user), identical receipt total (2445.90), identical content. **MATCH: True.** Restore path mirrors `admin_route.restore_encrypted_backup` exactly. |
| 10 | Dependency licenses | ✅ PASS | See `release/THIRD_PARTY_LICENSES.md` — no GPL/AGPL blockers; LGPL libvips via sharp = notice + replaceability only. |

## Demo dataset (1.3) — delivered

- `release/demo/seed_demo.json` — 20 fake drugs (expiry offsets, categories, EGP prices), 5 fake patients (`(demo)`-suffixed, placeholder phones), 2 fake suppliers, 10 receipts (21 line items, mixed Cash/Card/InstaPay). No real names, phones, or prescriptions.
- `release/demo/load_demo.py` — loads into a **fresh** SQLite DB via the backend's own lifespan logic (`init_engine` → `create_schema` → `seed_*` → demo rows → `setup_complete=true`, admin `demo`). Verified: exit 0, counts 20/5/10/2, all 10 receipt totals consistent with items, `--clean` idempotent reload produces identical counts.
- Verified DB: `release/demo/pharmacy-demo.db` (regenerable; safe to delete).

## Observations (non-blocking)

1. `app/core/backup.py` imports `_engine` **by value** (`from app.core.database import _engine`), so its module-level copy stays `None` after `init_engine()`; `_engine_or_init()` then falls back to `init_engine()` (default URL). Benign in the packaged app (default URL == configured URL) and tests patch it explicitly, but it is a latent trap for any future embedder. Suggested 1-line fix in Phase 4: reference `app.core.database._engine` via the module.
2. `phi_encrypt`/`phi_decrypt` remain defined-but-unwired (B5) — marketing copy must not claim at-rest PHI encryption (see DISCOVERY.md §3).
3. Cosmetic: `pyproject.toml` lacks a `license` classifier for `pharmacy-fastapi`; `src-tauri/Cargo.toml` lacks `license = "LicenseRef-Proprietary"`.

## HUMAN_TODO additions from this phase

- §L3 clean-machine install test (pre-sale gate).
- §L4 Arabic-RTL screenshot confirmation (folds into Phase 3.2 capture task).
