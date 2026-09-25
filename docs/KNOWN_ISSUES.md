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
