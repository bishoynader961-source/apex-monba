# MSIX / Microsoft Store Submission Checklist

Status legend: ☐ open · ☒ done · N/A not applicable

## 1. Signing & Identity

| Item | Status | Notes |
|---|---|---|
| EV code-signing certificate | ☐ | Required by Partner Center. `Publisher` CN in `src-tauri/package.appxmanifest` is a **PLACEHOLDER** — must equal the EV cert subject exactly. |
| Partner Center developer account | ☐ | Company account recommended (pharmacy = business software). |
| Final package identity | ☐ | `Identity Name` must match the Partner Center reservation. |

## 2. Package & Build

| Item | Status | Notes |
|---|---|---|
| MSIX bundle target | ☐ | **Tauri 2 has no native `msix` bundle target** (verified: config rejected `"msix"` as a `BundleTargetInner`). Path: keep `nsis`+`msi` builds, then repack the WiX `.msi` into MSIX with **MSIX Packaging Tool** (or `makeappx`) once signing is available. |
| Appx manifest | ☒ | `src-tauri/package.appxmanifest` prepared (Identity/DisplayName/Capabilities; placeholders marked). |
| App icons at MSIX sizes | ☐ | StoreLogo.png, 44x44, 150x150, 310x310, SplashScreen at the paths the manifest references. |
| Clean release build of the msix target | ☐ | `npx tauri build --bundles msix` once signing is available. |

## 3. Store Listing Assets

| Item | Status | Notes |
|---|---|---|
| Privacy policy URL | ☐ | In-app page exists (`/privacy`); a **public URL** is required by the Store — SystemSetting `privacy_policy_url` seeded empty, surfaces once set. |
| Age rating questionnaire | ☐ | Expected Everyone/3+ (placeholder comment in the manifest). |
| Screenshots (≥ 1 per device family) | ☐ | POS, inventory, receipt print are the strongest candidates. |
| App description + keywords | ☐ | Draft exists in the manifest `Description`. |
| Support contact (email/website) | ☒ | `pharmacypro.support@gmail.com` (in-app Support page). |

## 4. Technical Requirements

| Item | Status | Notes |
|---|---|---|
| App runs unpackaged on Win 10 19041+ | ☒ | Current NSIS install target. |
| No elevated permissions at runtime | ☒ | App writes only to `%APPDATA%\PharmacySuite`. |
| Crash handling | ☒ | Panic hook + recovery app (Phase 2). |
| Auto-updater | ☒ (stub) | Plugin wired; check is silent until `update_endpoint_url` is set (Sprint 4B). Store builds must disable the self-updater path (Store handles updates). |
| Accessibility review | ☐ | Automated pass: 0 Critical/Serious on the 3 most-used pages (Sprint 3D); manual screen-reader pass still open. |
| Windows Defender / SmartScreen scan | ☐ | Run after signing. |

## 5. Content & Compliance

| Item | Status | Notes |
|---|---|---|
| In-app privacy policy | ☒ | `/privacy` page + Support page link. |
| Terms of use acceptance | ☐ | Not implemented (audit M-tier; planned). |
| Data collection disclosure | ☐ | Diagnostic report content is user-initiated and local-only — document in listing. |

## Estimated remaining effort (excluding cert purchase + Partner Center review time)

- EV certificate + account setup: 2–4 h (procurement dominates)
- Icons at Store sizes: 2 h
- Final MSIX build + signing + local install test: 3 h
- Store listing assets + submission: 4 h
- Manual accessibility pass: 4 h
