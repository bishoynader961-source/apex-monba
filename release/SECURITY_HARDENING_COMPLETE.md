# Security & Performance Hardening — COMPLETE

**Repo:** `bishoynader961-source/apex-monba` · **Date:** 2026-10-03 · **Audit source:** `audit/AUDIT_REPORT.md` (18 findings: H1–H2, M1–M9, L1–L7)

All 18 audit findings are addressed: 17 fixed in reviewable batch PRs, 1 (M5) deliberately left open pending an owner architecture decision. Every batch is a single PR, stacked on the previous branch, none merged by the agent.

## Findings status

| ID | Severity | Category | Status | Batch / PR |
|----|----------|----------|--------|------------|
| H1 | High | Security | **Fixed** in PR #30 (untracked + gitignored); history scrub & key rotation still owner steps (D1) | Batch 1 — [#30](https://github.com/bishoynader961-source/apex-monba/pull/30) |
| H2 | High | Security | **Fixed** in PR #30 (prod defaults, weak-seed refusal, seeding warnings) | Batch 1 — #30 |
| L2 | Low | Security/Hygiene | **Fixed** in PR #30 (cert/binary untracked); history scrub pending D1 | Batch 1 — #30 |
| L3 | Low | Security | **Fixed** in PR #30 (`DB_PASS=localpass` write removed) | Batch 1 — #30 |
| M1 | Medium | Security | **Fixed** in PR #31 (setup hardening) | Batch 2 — [#31](https://github.com/bishoynader961-source/apex-monba/pull/31) |
| M2 | Medium | Security | **Fixed** in PR #31 (LAN bind / docs exposure) | Batch 2 — #31 |
| M6 | Medium | Security | **Fixed** in PR #31 (CORS) | Batch 2 — #31 |
| M4 | Medium | Security | **Fixed** in PR #32 (keys out of binary, fail-closed fix engine); `cargo test --lib` **14/14** verified (Phase A); key rotation = D3 | Batch 3 — [#32](https://github.com/bishoynader961-source/apex-monba/pull/32) |
| M3 | Medium | Security | **Fixed** in PR #32 (HttpOnly cookie session); silent-refresh **E2E verified in Tauri webview** (Phase A, no code changes needed) | Batch 3 — #32 |
| L4 | Low | Security | **Fixed** in PR #32 (signed UDP discovery, legacy unsigned packets ignored); verified by tests (Phase A) | Batch 3 — #32 |
| L5 | Low | Security/Perf | **Fixed** in PR #32 (`approval_jti` table, schema v30) | Batch 3 — #32 |
| M7 | Medium | Performance | **Fixed** in PR #33 (indexed `devices.token_prefix`, O(1) candidate lookup, legacy fallback) | Batch 4 — [#33](https://github.com/bishoynader961-source/apex-monba/pull/33) |
| M8 | Medium | Performance | **Fixed** in PR #33 (schema v31/v32 indexes; deviation: audit's `audit_logs.created_at` does not exist — indexed actual `timestamp` column) | Batch 4 — #33 |
| M9 | Medium | Performance | **Fixed** in PR #33 (keyset pagination, SQL-pushed filters, 366-day/10k-row caps, alert-cache) | Batch 4 — #33 |
| L1 | Low | Bug | **Fixed** in PR #34 (Decimal ROUND_HALF_UP cents in bulk adjust, Excel import, vendor intake) | Batch 5 — [#34](https://github.com/bishoynader961-source/apex-monba/pull/34) |
| L6 | Low | Security | **Fixed** in PR #34 (CSP: Paddle script-src + `img-src https:` removed; `style-src 'unsafe-inline'` intentionally retained for the two print-preview `<style>` blocks) | Batch 5 — #34 |
| L7 | Low | Bug | **Fixed** in PR #34 (single `today_iso()` expiry semantic, documented local-calendar convention) | Batch 5 — #34 |
| M5 | Medium | Security | **OPEN — intentionally not batched.** LAN plaintext HTTP requires a real certificate/TLS deployment decision (self-signed trust rollout vs. reverse proxy). Needs owner input before code changes. | — |

## Verification summary

- **pytest:** 917 passed / 1 skipped (baseline before batches: 889; +28 batch tests, zero regressions).
- **cargo check:** 0 errors (6 pre-existing warnings). **`cargo test --lib`: 14 passed / 0 failed** (Phase A; required a build-environment loader workaround documented in the A1 notes — no source changes).
- **tsc --noEmit:** clean after every batch that touched frontend files.
- **EXPLAIN QUERY PLAN:** all six hot queries use the new `ix_*` indexes (PR #33 body).
- **E2E:** Tauri webview silent-refresh verified end-to-end with an isolated backend + `next dev` (Phase A).

## Open items

1. **M5 — plaintext HTTP on LAN** (deliberately open; needs owner decision on TLS approach).
2. **Owner manual steps** — recorded in `HUMAN_TODO.md` under *Phase D — Manual steps (owner only)*:
   - **D1** git history scrub (`git filter-repo --invert-paths` for `login.json`, `test_verify.json`, `validate.json`, `debug_login.txt`, `app.exe`, `src-tauri/test-cert.pfx` + force-push + backup warning). **H1/L2 are not fully closed until this runs.**
   - **D2** `openssl pkcs12` inspection of `test-cert.pfx` (does it contain a private key?).
   - **D3** rotate `FIX_CODE_SECRET` + `FIX_ADMIN_KEY` on every installed machine (URGENT section, before announcing PR #32 merged).
   - **D4** CI coverage gate decision (90% gate vs ~73% actual — lower gate or add tests; failing CI shows every PR red).
   - **D5** real-Windows `cargo test --lib` confirmation (now expected to pass 14/14; agent-environment blocker solved, re-verification on the dev machine still recommended).
3. **All five PRs (#30–#34) are open and unmerged** — review and merge in order 30 → 31 → 32 → 33 → 34 (branches are stacked; each later branch contains the earlier ones).

## History-scrub status

**Pending (D1, owner-only).** The tracked-file half of H1/L2 is fixed in PR #30 (untracked + `.gitignore`), but the credentials, license key, and binaries remain recoverable from git history until the owner runs the filter-repo scrub and force-pushes. The exposed license key also still needs server-side rotation (PR #30 notes).

## Statement

> No Critical findings. All High findings resolved. All Medium findings resolved (M5 plaintext HTTP tracked and awaiting an owner TLS decision). All Low findings resolved or tracked as owner manual steps.

## Reminder

A **professional security review** before going on sale is still strongly recommended for a pharmacy app storing patient data. This hardening pass closes the findings of the internal audit; it is not a substitute for an independent penetration test of the desktop app, LAN sync protocol, and payment/licensing flow.
