# Changelog

## v1.0.0-rc1 — 2026-09-28

**Tag:** `v1.0.0-rc1` (tagged at `a6680c9`, "docs: PROJECT_MAP Sprint 4 status sync")
**Gates at tag:** backend pytest **851 passed / 1 skipped / 0 failed** · desktop `tsc --noEmit` **0 errors** · mobile tsc **0 errors** · `cargo check` **0 errors** (6 pre-existing warnings) · `cargo build --release` OK
**Audit trajectory:** 6.8/10 → **7.9/10** across all 9 domains (see `AUDIT_REPORT_2026-09-27.md` baseline; final scores in the blueprint completion report / `PROJECT_MAP.md`).

### Phase 0–5 groundwork (pre-sprint, blueprint execution start)
- **Audit:** full 9-domain re-audit with severity/effort tables (`AUDIT_REPORT_2026-09-27.md`, `58b6a23`).
- **Critical fixes:** expired stock can no longer be sold at checkout (`feba3c0`); patient-fields router authenticated with RBAC (`c0fe87b`).
- **Blueprint error fixes:** 403/500 toast handling in `lib/api.ts`; role `"*"` → explicit permission mapping; sessionStore union-safety.
- **WC Claims modal hardening + Support page UX** (`8abc77a`): patient autocomplete, real-time total == insurance + patient validation with save gate, cancel-confirm on dirty form.
- **Demo mode + onboarding** (`2e37f20`): idempotent demo seeder, admin seed/reset/clear routes, amber DEMO banner, first-run onboarding modal.
- **Mobile companion (Phases 1–4):** secure mobile auth — SecureStore, session timeout, biometric unlock (`0ff2e34`); byte-identical shared contracts + CI parity gate (`51bb566`); mobile access mode with mode-aware API bind host (`6e4c7a8`); mobile patient search (`3f57957`); QR gateway, device model, mobile pairing (`d63abcb`); mDNS desktop advertisement (`8798d78`); mobile ConnectScreen + QR pairing (`03ab02b`); offline queue with sync-on-reconnect (`3a1445d`).
- **Desktop resilience:** Broken-App Recovery System (`afc4639`); Mobile Diagnostic & Recovery System (`1c8c7cd`); fix-code engine template (`6147eb2`); money-safety, mobile token storage, CSP, privacy policy fixes (`9b33211`); WC claim money-field validation (`9f8d6ea`).

### Sprint 1 — Security & correctness quick wins
- JWT access-token TTL 480 → **15 minutes** with refresh rotation (`cf1d9a4`).
- **Auth-event audit logging:** login / logout / failed-login / PIN-change now written to the hash-chained audit log (`4c3c9bf`).
- Checkout hardening: expired-stock rejection (`feba3c0`) plus server-side WC claim totals validation and cents-based money handling on hot paths.
- Unauthenticated patient-data router closed (`c0fe87b`).

### Sprint 2 — Data safety, performance, setup flow
- **Encrypted backup/restore** (`09cbf52`): AES-256-GCM, fresh 256-bit key per backup shown once, `.backup.enc` format, restore with tamper detection.
- **N+1 query fixes** (`b5eecf9`): receipt items 1+N → 2 queries (measured); low-stock → single grouped aggregate; EPCS list constant-time name prefetch.
- **First-run setup gate** (`57a6576`): `setup_complete` SystemSetting gates 54 routers until completed.
- **Concurrent checkout race test** (`ac5f45d`): mobile + desktop racing the last unit — exactly one 201, stock correct, one receipt.
- GZip response middleware on the API.

### Sprint 3 — UX, accessibility, i18n
- **Onboarding wired to `setup_complete`** (`d5d5ba8`): admin "Get Started" completes setup; non-admins get navigate-only path.
- **Accessibility** (`e2840a6`): jsx-a11y Critical/Serious violations fixed on POS / inventory / RX (0 remaining in those scopes).
- **Arabic RTL** (`c0ef237`): direction-locked physical utilities → logical properties; pre-paint dir switching verified; `ar.json` confirmed 100% complete (1076/1076 keys).
- **Bundle analysis:** 0 chunks > 300 KB gzip; virtualization skipped with evidence (all large lists server-paginated).

### Sprint 4 — Microsoft Store readiness
- **4A Window state persistence + sleep recovery** (`c5d015f`): position/size saved to `AppData\PharmacySuite\config\window_state.json`, restored on start with off-screen validation, sidecars restarted after 3 consecutive /health failures post-resume.
- **4B Auto-updater stub** (`70814ba`): `tauri-plugin-updater`, native update dialog, endpoint from `update_endpoint_url` SystemSetting (empty → silent skip).
- **4C MSIX packaging preparation** (`b0908d6`): MSIX bundle target, `src-tauri/package.appxmanifest` with Identity/Publisher/Capabilities + age-rating placeholder, `MSIX_SUBMISSION_CHECKLIST.md`, `privacy_policy_url` setting.
- **4D Backup reminder** (`a187dca`): `last_backup_at` stamped on both backup endpoints; `backup_reminder` / `backup_days_ago` on dashboard metrics; session-dismissable amber banner linking to the backup page; regression test covering empty / 8-day / fresh / re-stamp flows.
- **4E Release readiness** (`5209055`): `RELEASE_READINESS.md` — overall status, 12-row Store checklist, 7 known limitations, 16-item pharmacist walkthrough, ~22 h remaining estimate. Status sync in `a6680c9`.

### Notes (disclosures)
- Latent pre-existing bug fixed in 4D: `GET /api/v1/dashboard/metrics` was returning 500 for all callers (SQL referenced nonexistent columns); rewritten to the real schema.
- Owner deviation: the backup-reminder flag lives on `/api/v1/dashboard/metrics` (the actual dashboard endpoint), not `/api/v1/dashboard` as originally specced.
- Simplification: `expiring_soon` rows report `quantity_on_hand = 0` (cosmetic; low-stock and expiry flows function).
- Remaining backlog and Store-submission requirements are tracked in `RELEASE_READINESS.md` and `MSIX_SUBMISSION_CHECKLIST.md` — nothing critical remains in code.
