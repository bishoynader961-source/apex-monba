# Third-Party Licenses — commercial-sale audit

Date: 2026-10-03 · Branch: `release/launch-prep` · Distributed artifact: Windows desktop app (Tauri + Next standalone + PyInstaller FastAPI sidecar).

## Verdict

**BLOCKERS: NONE.** No GPL or AGPL license exists in any shipped dependency across npm, Python, or Rust. Two LGPL-containing npm binaries require only standard notice + replaceability (see §1). PyInstaller's GPLv2 carries the bootloader exception that explicitly allows commercial closed-source bundling (see §2).

Distribution obligations before shipping (add to final release checklist):
1. Ship a `LICENSES.txt`/About screen listing third-party components (auto-generated per §5 commands).
2. Keep the libvips binaries (via sharp) unmodified and replaceable — do not statically link or patch them.

---

## 1. npm dependencies (UI) — `license-checker`

Scan: `npx license-checker --summary --excludePrivatePackages` → **547 packages**.
Distribution: `MIT: 456 · Apache-2.0: 32 · ISC: 26 · BSD-2/3: 10 · MPL-2.0: 5 · dual MIT/Apache: 7 · misc permissive (Python-2.0, CC-BY-4.0, CC0, BlueOak-1.0.0, WTFPL OR MIT, MIT AND Zlib, 0BSD, MIT*): 8` + 3 items below.

| Package | Version | License | Blocker? | Analysis |
|---|---|---|---|---|
| `jszip` | 3.10.1 | `(MIT OR GPL-3.0-or-later)` | **No** | Dual-licensed — we consume the **MIT** side. Notice only. |
| `@img/sharp-win32-x64` | 0.35.4 | `Apache-2.0 AND LGPL-3.0-or-later` | **No** | Bundles **libvips** as a *separately loaded* native binary (`.node`/DLL), not linked into our code. LGPL-3.0 obligations: include license notice + keep the library replaceable. Satisfied by shipping it as-is. |
| `@img/sharp-wasm32` | 0.35.4 | `Apache-2.0 AND LGPL-3.0-or-later AND MIT` | **No** | Same libvips WASM variant; same obligations. Verify at packaging whether either sharp binary is actually included in the shipped bundle (Next.js optional dep); if absent, obligation is moot. |

No unknown/unlicensed packages found.

## 2. Python dependencies (FastAPI sidecar) — `pip-licenses`

Scan: `python -m piplicenses --format=markdown` (71 packages incl. transitive). Full table reproducible via §5.

**Only copyleft hits — both build-time, not shipped as libraries:**

| Package | Version | License | Blocker? | Analysis |
|---|---|---|---|---|
| `pyinstaller` | 6.22.2 | GPLv2 **with bootloader exception** | **No** | The exception in `PyInstaller/bootloader/` explicitly grants the right to distribute applications bundled with the PyInstaller bootloader without those apps falling under the GPL. Used only to build the sidecar `.exe`; no PyInstaller code ships as a library. |
| `pyinstaller-hooks-contrib` | 2026.7 | Apache-2.0 + GPLv2 | **No** | Hooks run at build time only. |
| `pharmacy-fastapi` (ours) | 1.0.0 | UNKNOWN | **No** | Our own package missing a classifier — cosmetic; set `license` in `pyproject.toml` for tidiness. |

Everything else: MIT / BSD / Apache-2.0. Runtime stack (fastapi, sqlalchemy, aiosqlite, pydantic, bcrypt, pyjwt, structlog, cryptography, pillow, pytesseract, paddleocr, psutil, platformdirs, uvicorn, httpx, slowapi, limits, python-dotenv) — all permissive.

## 3. Rust dependencies (Tauri shell) — `cargo-license`

Scan: `cargo-license --tsv` → **510 crates** (511 lines incl. our `app` crate). 484 match MIT/Apache/BSD/ISC patterns; remainder are MIT/Apache-2.0 dual or other permissive (Unicode-3.0, Zlib, MPL-2.0, CC0, Unlicense, 0BSD).

| Package | Version | License | Blocker? | Analysis |
|---|---|---|---|---|
| `webpki-root-certs` | 1.0.9 | CDLA-Permissive-2.0 | **No** | Permissive (redistribution allowed; not copyleft). Notice only. |
| `app` (ours) | 1.0.0 | *(unset)* | **No** | Set `license = "LicenseRef-Proprietary"` in `Cargo.toml` for tidiness. |

Direct deps (tauri 2.11.3, tokio, serde, chrono, sha2/hmac, sqlite, mdns-sd, windows-sys, tauri-plugin-*) — all MIT/Apache-2.0.

## 4. Summary for the store listing

- Third-party license count: ~1,120 components total (547 npm + 71 Python + 510 Rust), all commercially distributable.
- Required notices: libvips (LGPL-3.0) via sharp binaries; jszip (MIT); webpki-root-certs (CDLA-Permissive-2.0); standard MIT/Apache/BSD attributions.

## 5. Reproduce

```bash
# npm
npx license-checker --summary --excludePrivatePackages
# Python (backend_fastapi venv)
python -m piplicenses --format=markdown
# Rust (src-tauri; one-time: cargo install cargo-license)
cargo-license --tsv
```
