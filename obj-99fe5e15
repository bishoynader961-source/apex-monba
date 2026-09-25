# KNOWN ISSUES — Pharmacy Suite 1.0.0

Deferred items recorded at launch-readiness review (SPEC-09 Stage 4.3). Each entry
notes the current state and when it should be revisited. Nothing here blocks 1.0.

## 1. ESLint warnings (327)

Non-error warnings, dominated by `react-hooks/exhaustive-deps`, unused imports, and
minor type looseness. Builds and tests pass with them present.

**Plan:** dedicated cleanup pass before the 1.1 release; split into auto-fixable
(`eslint --fix`) items and manual ones, then tighten the lint config so new
warnings fail CI.

## 2. Gmail DMARC not possible on gmail.com

The support address `pharmacypro.support@gmail.com` cannot publish a DMARC policy —
DMARC requires control of the sending domain, and gmail.com is Google's.

**Current controls (documented in `docs/SUPPORT_EMAIL_SECURITY.md`):** 2FA enabled on
the support account, login alerts on, anti-phishing notice shown in the Support tab.

**Plan:** when a custom domain (e.g. `pharmacysuite.app`) is acquired, migrate the
support mailbox to it and publish `SPF v=spf1 include:_spf.google.com ~all`, DKIM via
Google Workspace, and `DMARC p=reject` per SPEC-09 Stage 3.3.3.

## 3. SQLite database unencrypted at rest

`%APPDATA%\PharmacySuite\pharmacy.db` stores patient data in a plain SQLite file.
Documented in `docs/SECURITY_HARDENING.md` with a BitLocker recommendation for users.

**Plan:** evaluate SQLCipher for v2 (requires recompiling SQLAlchemy bindings and a
key-management story — the key cannot live next to the DB file).

## 4. Duplicate patients route files

`app/patients/page.tsx` and `app/dashboard/patients/page.tsx` both exist. Verified
during SPEC-09: the active route is the one NAV_SECTIONS links to, and it is wrapped
in `DashboardLayout`. The duplicate was left in place rather than deleted during a
launch-review change to keep the diff surgical.

**Plan:** confirm the inactive copy, delete it, and add a redirect if any links
point at it. Do this in a low-risk window right after 1.0 ships.

## 5. Mobile app (`mobile/`) checkout contract drift

The React Native app in `mobile/` is a separate codebase excluded from this release.
The checkout contract drift fixed in the desktop backend/frontend has **not** been
mirrored there; the mobile client may still serialize money fields differently.

**Plan:** apply the same contract alignment (string-typed Decimal money fields, no
float parsing) to `mobile/` in its next work cycle, before any mobile release.

## 6. `tauri-build-target/` committed to git

Roughly 2,900 Rust build artifacts are tracked in git. Removal has been staged via
`git rm -r --cached tauri-build-target/` with a matching `.gitignore` entry; the
untracked copy on disk is untouched. If this file says "still present" in a later
review, re-run:

```
git rm -r --cached tauri-build-target/
git commit -m "chore: untrack tauri-build-target build artifacts"
```

**Plan:** land the untracking commit before the 1.1 branch point.

## 7. Frontend/backend contract drift — RESOLVED (2026-09-25)

The drift had grown to 25 schemas (18 initially visible + 7 below the fold:
ChangePasswordRequest, CreemCheckoutRequest/Response, DrugDictionaryRead,
DrugEvaluateRequest/Response, IntegrationCreate). All 25 now have field-for-field
mirrors in the new `types/contracts-parity.ts` (Vendor*, SyncLock*, Mobile*,
License*, Integration*, Creem*, Drug*, PaymentSplitIn, PurchaseHistoryRead,
PurchaseOrderReceiveItem, ReceiveShipmentPayload, VerifyPasswordRequest) —
including the legacy vendor module's JSON-number money and SQLite int-bool flags.
They live in a separate file because `types/contracts.ts` (56 KB) is past the
editor tool's save limit; `scripts/check-contracts.mjs` now scans both files, so
a new backend schema still fails the gate until mirrored.
`node scripts/check-contracts.mjs` exits 0 (0 gaps).

**CI:** already wired — `.github/workflows/ci.yml` has a dedicated
`contract-check` job running `npm run check:contracts` (previously red on every
push), so new drift blocks the build automatically.

## 8. Contract check is name-level only

`scripts/check-contracts.mjs` verifies that a TypeScript name exists for every
backend schema — not that its fields match. A backend field rename or type
change passes the gate while drifting the actual wire contract (the exact
422-bomb scenario the check exists to prevent).

**Plan:** extend the script to parse Pydantic fields (name, required/optional,
type) and compare them against the TS interface body. Money fields must map to
`Money` (string), SQLite int-bools to `number`, `Optional` to `| null`.

## 9. Oversized files: types/contracts.ts and FLOW_LOGIC.md

Both exceed the editor tool's save limit (~20k tokens / 56 KB). Contracts are
already split (`types/contracts-parity.ts`); FLOW_LOGIC.md keeps growing and
will hit the same wall.

**Plan:** for FLOW_LOGIC.md, archive completed spec sections into
`docs/archive/` (or split per-spec flow docs) and keep the main file to
currently-active flows only. For contracts, evaluate splitting
`contracts-parity.ts` by feature area when it grows.

## 10. check-contracts not in the local pre-build gate

The parity gate runs in CI (`contract-check` job) but a developer building
locally gets no warning before pushing.

**Plan:** add `node scripts/check-contracts.mjs` to the `prebuild` npm hook
(or the build script itself) so drift surfaces at build time, not at push time.

## 11. FIX_CODE_SECRET rotation runbook undocumented

Rotating the fix-code signing secret currently lives only in tribal memory.
Wrong-order rotation silently bricks the Technician Fix feature for users
mid-update (they'd paste codes that 403 with no visible reason).

**Plan:** document in docs/SUPPORT_EMAIL_SECURITY.md: (1) generate the new
secret, (2) deploy backend with the new secret FIRST (all old codes 403 —
acceptable, fail-closed by design), (3) invalidate any outstanding codes sent
to users, (4) update the operator CLI's env. Note the versioned-secret
alternative (`kid` field in the envelope) if zero-downtime rotation is ever
needed.
