# HUMAN TODO — actions only the owner can take

Items here are deliberately **not** automated: they are irreversible, or they
require credentials/systems the agent does not have. Each item names the audit
finding it closes.

## URGENT — Do before announcing PR #32 is merged

The old FIX_CODE_SECRET shipped inside the compiled binary and is in git
history. Rotate it now:
1. Generate a new secret: python -c "import secrets; print(secrets.token_hex(32))"
2. Update FIX_CODE_SECRET in the .env file on every installed machine
   (yours + any customer installs).
3. Restart the FastAPI sidecar on each machine.
4. Old fix codes signed with the old key will stop working — this is correct.
5. Update your support tool that generates fix codes to use the new key.
6. Also rotate FIX_ADMIN_KEY by the same process.

## Batch 3 — Secrets & trust (M4, M3, L4, L5)

### 1. Rotate FIX_CODE_SECRET on every production install (audit M4) — REQUIRED

**Rotate FIX_CODE_SECRET in production .env files on all installs, since the old
key shipped in the binary.** (`src-tauri/src/fix_key.txt`, compiled via
`include_str!`, was extractable from `app.exe`; treat it as compromised.) The
desktop no longer embeds any key; verification now happens online against the
backend.

Per install (each main device):

1. Generate a new secret: `openssl rand -hex 32`.
2. In that install's backend `.env` (the sidecar's working directory, e.g.
   `%APPDATA%\PharmacySuite\.env` when present, or `backend_fastapi/.env` for a
   dev/QA checkout) set the value:
   `FIX_CODE_SECRET=<new value>`
3. Add the admin key used together with fix codes (the desktop no longer
   embeds it either):
   `FIX_ADMIN_KEY=<openssl rand -hex 24>`
   Support tooling must sign/issue fix codes with the same values.
4. Restart the app so the sidecar re-reads `.env`.
5. Old fix codes are rejected (fail closed) after rotation — regenerate any
   outstanding ones with the new secret.

Operational note: applying a fix code now requires the local backend to be
running (the recovery engine fails closed with `VERIFY_UNAVAILABLE` when it
cannot reach `127.0.0.1:8000`). Support instructions should say: start Pharmacy
Suite once, then retry the fix.

### 2. Delete local key copies (audit M4) — RECOMMENDED

`src-tauri/src/fix_key.txt` and `src-tauri/src/fix_admin_key.txt` are already
gitignored and are no longer compiled in. Delete them from developer machines so
they cannot accidentally be copied into a build or reused after rotation.

### 3. Clear legacy localStorage tokens on existing installs (audit M3) — OPTIONAL

Devices that ran an older version may still hold `access_token` /
`refresh_token` entries in the webview's localStorage. The new frontend never
reads them, so they are inert; clearing them would need a one-time cleanup pass
(DevTools → Application → Local Storage). If any of those machines ever ran an
untrusted extension, rotate the affected admin passwords as the safe follow-up.

### 4. L4 / L5 need no manual step (audit L4, L5) — NO ACTION

- Signed UDP discovery self-migrates: the next broadcast from an updated main
  device carries the signature; legacy unsigned packets are ignored. Manual IP
  entry remains available for mixed-version networks.
- The `approval_jti` table is additive (schema v30) and self-prunes rows older
  than 120 s; no data migration or cleanup is required.

## Phase D — Manual steps (owner only)

### D1 — Git history scrub (H1 + L2)

The following files were committed to git history and must be scrubbed:
login.json, test_verify.json, validate.json, debug_login.txt, app.exe,
src-tauri/test-cert.pfx, and the venv/ directory (commit 1ee047a).
Steps (do this on a private machine, coordinate with any collaborators first):
1. Install git-filter-repo: pip install git-filter-repo
2. Run: git filter-repo --invert-paths
     --path login.json
     --path test_verify.json
     --path validate.json
     --path debug_login.txt
     --path app.exe
     --path src-tauri/test-cert.pfx
   This rewrites all history. Every collaborator must re-clone afterwards.
3. Force-push: git push origin --force --all && git push origin --force --tags
4. Ask GitHub support to clear their caches for the repo (optional but thorough).
5. Verify: git log --all --full-history -- login.json should return nothing.

Note: this is irreversible. Take a full backup of the repo before starting.

### D2 — test-cert.pfx inspection

Before scrubbing history, inspect the certificate:
Run: openssl pkcs12 -in src-tauri/test-cert.pfx -info -noout
If it contains a private key (you will see 'MAC verified OK' and key material):
- That private key is compromised if the repo was ever public or shared.
- Do not use it for any signing purpose.
- Generate a new local test cert: the src-tauri/*.bat scripts show the command.
If it contains no private key: it is a certificate-only file and lower risk.

### D3 — FIX_CODE_SECRET and FIX_ADMIN_KEY rotation

Rotate both secrets on every installed machine before announcing
PR #32 is merged. Instructions are already in HUMAN_TODO.md under
the URGENT heading added in Phase A.

### D4 — Coverage gate

The CI coverage gate requires 90% but the suite is at ~73%.
This is pre-existing and not caused by any batch fix.
Two options:
Option A (recommended): lower the --cov-fail-under threshold in
  .github/workflows/ci.yml to match the real current coverage (73%)
  and raise it incrementally as you add tests.
Option B: write enough new tests to reach 90% before the next release.
Pick one and action it before the app goes on sale, because a failing
CI gate means every PR shows red.

### D5 — Cargo test on a real Windows machine

Status update: the Rust test binary could not execute in the agent's build
environment (STATUS_ENTRYPOINT_NOT_FOUND), but that environment blocker has
since been solved — `cargo test --lib` passes here: **14 passed / 0 failed**
(7 udp_discovery L4 tests + 7 fix_engine M4 tests). The loader workaround used
to run them in this environment is build-only and does not affect source code.
Real-machine verification is still recommended before merging PR #32:
Run on your Windows dev machine:
    cargo test --lib
All 14 tests in the udp_discovery and fix_engine modules must pass.
Report any failures before merging PR #32.

---

## LAUNCH PREP — Phase 0 follow-ups (owner, added 2026-10-03, branch release/launch-prep)

### L1 — Support email inbox — RESOLVED 2026-10-03
Owner chose **pharmacypro.support@gmail.com** (recorded in release/DECISIONS.md).
Remaining: enable 2FA on that inbox before it goes on any public listing.

### L2 — App logo 512×512 PNG
Needed for the Freemius product icon, store listing, and installer branding.
1. Export the app logo as a square PNG, exactly 512×512, transparent or solid background is fine (Freemius accepts PNG).
2. Also keep a 1024×1024 master if available.
3. Save as `release/branding/logo-512.png` (create the folder) or reply where it lives.

### L3 — Clean-machine install test (PRE-SALE GATE, from Phase 1 audit)
Cannot be automated here. Do this on a Windows 10/11 machine with NO Node, Python, or Rust installed:
1. Build the installer: `npm run tauri build` (on your dev machine) and take the NSIS `.exe` from `src-tauri/target/release/bundle/nsis/`.
2. Copy ONLY the installer to a clean machine (or a fresh Windows VM).
3. Run the installer → app must start with no errors.
4. First-run wizard must appear; create the owner admin account (password rules: ≥12 chars, upper+lower+digit+symbol).
5. Log in, add one product, make one sale, then quit and relaunch — data must persist.
6. Check Settings → Backup: create an encrypted backup and confirm the `.backup.enc` file exists.
7. Report pass/fail back (any failure blocks the release).
Why: the security audit verified code-level first-run behavior, but only a clean machine proves the shipped sidecars/updater work without dev tools.

### L4 — Arabic/RTL visual confirmation (folds into Phase 3.2 screenshots)
When capturing the 8 store screenshots, capture at least 2 with the UI language set to Arabic:
1. Settings → Language → العربية.
2. Confirm the layout flips to right-to-left and no text is cut off in the POS and Inventory screens.
3. Keep those as 2 of the 8 screenshots (Arabic-speaking buyers need to see RTL support).

### P1 — Create your Freemius account and product (Phase 3.3 — owner-only: KYC, identity, payout details)
Prerequisites: logo ready (§L2), support inbox 2FA (§L1), screenshots captured (§L4).
Platform facts verified 2026-10-03 from official pages (cited in release/REPORT.md):
  • Egypt IS on the supported payout countries list → https://freemius.com/help/documentation/selling-with-freemius/supported-countries.md
  • Desktop downloadable software is an allowed product; pharmacy management is not prohibited → https://freemius.com/help/documentation/selling-with-freemius/allowed-prohibited-products.md
  • Fee: 4.7% revenue share + ~3.5% avg gateway fee; no setup/monthly/payout fees → https://freemius.com/help/documentation/getting-started/our-pricing.md
Steps:
 1. Go to https://freemius.com and click "Get Started" (top-right) → https://freemius.com/pricing/
 2. Choose the "SaaS & Software" plan (NOT "WordPress & Templates" — Pharmacy Suite is a desktop app; 4.7% applies).
 3. Sign up with pharmacypro.support@gmail.com (or your preferred email). Verify your email.
 4. Enable 2FA on the Freemius account: https://freemius.com/help/documentation/security/two-factor-authentication-2fa.md
 5. Complete identity/business verification to sell in production (government ID / documents): https://freemius.com/help/documentation/selling-with-freemius/verification.md
 6. Set up your payout method (My Profile → Payout Methods). Recommended for Egypt: Payoneer or Wise (PayPal MassPay also available). Have the Payoneer/Wise account ready BEFORE this step. Payouts run on the 10th monthly with a $100 minimum and ~2-month first-payout delay: https://freemius.com/help/documentation/selling-with-freemius/your-earnings.md
 7. Create a new product: Dashboard → "Create Product" → type "App / Desktop" (SaaS & Software). Use the copy in release/store-copy/freemius_listing.md for name, tagline, description, FAQ, keywords.
 8. Set pricing exactly per release/DECISIONS.md: one-time $149 (1 license unit per computer), optional $59/yr renewal plan, 14-day free trial. Configure the 14-day refund policy in the product settings.
 9. In Sandbox mode, run one test checkout end-to-end before going live: https://freemius.com/help/documentation/checkout/integration/testing.md
10. Copy from the Developer Dashboard → My Products → [Pharmacy Suite] → Keys: Product ID, Public Key, Secret Key, and the Webhook URL secret. Put them in a LOCAL .env (never commit). Reply with "P1 done + product ID" (never paste the secret key into chat).
11. Hand the Product ID + keys to the Phase 4 license integration work (plan already written: release/LICENSE_INTEGRATION_PLAN.md).
