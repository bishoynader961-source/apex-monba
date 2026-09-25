# Microsoft Store Readiness Assessment (Win32 + Tauri + sidecars)

Assessment date: 2026-09-24 · App version: 1.0.0 · Verdict: **distribution-ready
architecture; 4 pre-submission blockers, none architectural.**

## Architecture vs the Store's Win32 expectations

The app is a **desktop bridge (Win32) app**: Tauri (WebView2) host process +
two packaged sidecars (PyInstaller `backend.exe`, Node `node.exe` serving the
Next standalone build). The Store accepts full-trust desktop apps in MSIX
packages — sidecars are permitted, but they change which checks matter.

## WACK (Windows App Certification Kit) area-by-area

| WACK test area | Status | Evidence / notes |
|---|---|---|
| Clean install/uninstall | ✅ likely | Per-user install, no services/drivers; MSI/NSIS uninstalls verified in SPEC 04. Must re-verify from the **MSIX** package (different install path). |
| File-system writes | ✅ | All writes under `%APPDATA%\PharmacySuite` (user profile). No writes to Program Files/registry pollution. `get_app_data_dir()` is the single source of truth. |
| Zombie processes (crash resilience) | ✅ **verified** | Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` per sidecar (`src-tauri/src/lib.rs::assign_child_to_job`), handles deliberately leaked so the kernel kills sidecars on any parent exit — graceful, crash, or Task-Manager force-kill. Empirically confirmed in desktop verification runs (`tasklist` clean after kill). |
| Graceful close path | ✅ | `CloseRequested` → `kill_sidecars()` + logs; `Destroyed` covers abnormal window loss. |
| Crash resistance | ✅ | Frontend ErrorBoundary → `/api/v1/crash-report`; seed/migration failures never block startup; uniform error contract. |
| Use of supported APIs only | ⚠️ verify | Raw `windows-sys` usage (Job Objects, UDP broadcast) is fine for full-trust; must confirm no deprecated API flags in WACK run. |
| Private code signing | 🔴 blocker | Store submission requires the package signed by a **trusted certificate**; dev/test cert used today. EV code-signing cert needed (also required for Partner Center ingestion). |
| App version/digits | ✅ | `1.0.0` / wix `1.0.0.0` (4-part) already set. |
| Age rating / listing / privacy policy | ⚠️ admin steps | Privacy policy exists (`docs/privacy-policy.md`); listing assets drafted (`docs/store-listing.md`). Age questionnaire + screenshots remain. |

## Sidecar-specific Store risks (checked)

1. **Executables inside the package must launch from the package path.** Both
   sidecars are declared `externalBin` and resolve correctly when installed —
   verified for MSI. MSIX install path differs (`C:\Program Files\WindowsApps\…`,
   read-only): **must confirm the standalone Node server + PyInstaller backend
   extract nothing to disk at startup.** Node standalone (`server.js`) runs
   in-place ✅; PyInstaller extracts to `%TEMP%` at first run — works, but adds
   first-launch latency and is WACK-adjacent worth measuring.
2. **Read-only install dir.** The app already treats its install dir as
   read-only (data in `%APPDATA%`) ✅ — this is the single biggest WACK win of
   the current design.
3. **Loopback networking.** The sidecar binds `127.0.0.1:8000`. MSIX apps with
   `runFullTrust` may use loopback freely ✅; if the manifest ever declares
   partial-trust, loopback *client* connections would need
   `checkNetIsolation LoopbackExempt`. With full trust: no action.
4. **Job Objects survive MSIX** ✅ — kernel-level, unrelated to packaging.

## MSIX packaging path (recommended order)

1. **Keep Tauri MSI as the direct-distribution channel** (already works).
2. For the Store: `MSIX from existing MSI` via **MakeAppx** (the SPEC 04 flow:
   `PharmacySuite_1.0.0.0_x64.msix` was already produced this way) — acceptable
   for ingestion testing, but **not** Store-updatable without signing with the
   Store-issued cert.
3. **Preferred long-term:** enable Tauri's native `msix`/`appx` bundle target
   (Tauri v2 supports it) so `tauri build` emits a proper package manifest
   (identity, capabilities) rather than wrapping an MSI. Declare
   `runFullTrust` capability for the sidecars; declare `internetClient` only
   if Terminal Mode/LAN is advertised in that listing.
4. Sign with the Store cert (`SignTool sign /fd sha256 /tr …`), run **WACK on
   the signed MSIX** (`appcert.exe reset/test`), attach to Partner Center.

## Blockers before submission (none architectural)

| # | Blocker | Owner | Notes |
|---|---|---|---|
| 1 | EV/OV code-signing cert + Partner Center account ($19 individual) | admin | Store-issued cert re-signs the package at ingestion |
| 2 | WACK run on the signed MSIX (fix whatever it flags) | eng | Expect: icon sizes, metadata, possibly PyInstaller TEMP extraction |
| 3 | Age rating questionnaire + final listing screenshots | admin | Drafts exist in `docs/store-listing.md` |
| 4 | MSIX identity alignment: package identity vs `com.pharmacysuite.app` | eng | Keep identifier stable so updates map to the same product |

## Update channel interplay (with the new Tauri updater)

Store-distributed builds **must disable the in-app Tauri updater** (Store
controls updates). Gate `UpdateChecker` on a build-time flag
(e.g. `NEXT_PUBLIC_CHANNEL=store`) when the MSIX becomes the shipping channel —
non-Store builds keep self-update. Tracked as the one follow-up when the Store
listing goes live.
