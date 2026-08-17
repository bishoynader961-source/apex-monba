# Phase 14: Deployment Architecture Plan

> **Status**: Planning — Implementation-Ready
> **Scope**: Package the pharmacy application into a standalone Windows `.exe` via PyInstaller
> **Entry Point**: `archive/main_app.py`
> **Application Root**: `archive/` (all source, configs, and assets reside here)

---

## 1. Context Discovery

Per `AGENTS.md` Protocol VI, this plan is grounded in the following sources:
- `PROJECT_MAP.md` §8 (Tech Stack), §9 (System Flow), §10 (Dependencies), §6 (Source File Reference)
- `FLOW_LOGIC.md` §7–9 (Template system, Rx build & packaging flow)
- `archive/path_utils.py` — MEIPASS-aware `get_resource_path()` + `ensure_runtime_directories()`
- `archive/main_app.py` — Entry point; already uses `get_resource_path` for `_LABEL_ENGINE`
- `archive/build_exe.py` — Existing build automation (`--onedir`, `--noconsole`, comprehensive hidden imports)
- `archive/PharmacyPro_Enterprise.spec` — Prior production spec (machine-specific hardcoded paths)
- `archive/barcode_logic.py` — Contains `open_label_engine()` called by UI; uses `__file__`-based path (NOT MEIPASS-aware)
- `archive/label_engine/export.py` — Module-level constants `TEMPLATE_PATH` and `LABELS_DIR` use `__file__`-based path (NOT MEIPASS-aware)
- `archive/exhaustive_verify.py` §9 (lines 1025–1069) — Tests `get_resource_path()` including MEIPASS simulation

---

## 2. Asset Inventory & Bundle Mapping

### 2.1 Read-Only Assets (must be bundled via `--add-data`)

| Source (relative to `archive/`) | Bundle Destination (`_MEIPRESS/`) | Accessed By | Notes |
|---|---|---|---|
| `config.json` | `./` | `barcode_logic.py:L13`, `db.py:L48` | Used via `get_resource_path("config.json")` |
| `pharmacy.db` | `./` | `db.py:L63`, `database.py` | SQLite DB; writable at runtime, but seed DB bundled |
| `licenses.db` | `./` | `license_gate.py` | License storage |
| `label_template.json` | `./` | `label_engine/export.py:L21` (`TEMPLATE_PATH`) | Resolved as `../label_template.json` from `label_engine/` via `__file__` |
| `locales/` | `locales/` | `i18n.py` | 6 locale files: ar, de, en, es, fr, pt |

### 2.2 Writable Runtime Directories (must exist or be created at runtime)

| Directory (when frozen) | Creator | Purpose |
|---|---|---|
| `_MEIPRESS/labels/` | `barcode_logic.init_labels_dir()` + `ensure_runtime_directories()` | Generated label PNG output |
| `_MEIPRESS/receipts/` | `ensure_runtime_directories()` | Receipt `.txt` files |
| `_MEIPRESS/backups/` | `ensure_runtime_directories()` | DB backup copies |
| `_MEIPRESS/label_engine/data/labels/` | `export._ensure_labels_dir()` | Saved label templates by product ID |

> **Key insight**: With `--onedir` mode, `_MEIPRESS` equals the dist directory (e.g., `dist/PharmacyPro_Enterprise/`), which is writable on the target machine. This avoids the read-only temp-dir problem of `--onefile`. **Recommendation: use `--onedir` mode** (consistent with existing `build_exe.py`).

### 2.3 Python Package: `label_engine/`

| File | Purpose | On-Disk Requirement |
|---|---|---|
| `label_engine/__init__.py` | Package marker | Auto-bundled by PyInstaller as imported |
| `label_engine/main.py` | Subprocess entry point | **Must be a real file on disk** for `subprocess.Popen` |
| `label_engine/canvas_core.py` | Core rendering engine | Imported by `ui.py`, `ui_modals.py` |
| `label_engine/export.py` | I/O + path constants | Imported by `ui.py`, `ui_modals.py`; `TEMPLATE_PATH` evaluated at import |
| `label_engine/properties_panel.py` | Property editor sidebar | Imported by `label_engine/main.py` |
| `label_engine/data/labels/` | Saved label templates | Auto-created by `_ensure_labels_dir()` |

> **Critical**: `label_engine/` is imported as a Python package by `ui.py` (lines 21–22). PyInstaller will auto-detect and bundle it in the PYZ archive. **However, `label_engine/main.py` must be accessible as a real file** because `barcode_logic.open_label_engine()` passes its path to `subprocess.Popen`. With `noarchive=False` (default), the `.py` file lives inside the `.pyz` zip and is not a real file path — **the subprocess launch will fail**.

---

## 3. PyInstaller .spec Configuration

### 3.1 Build Mode Decision

| Option | Pros | Cons |
|---|---|---|
| `--onedir` (recommended) | Files on disk = `__file__` resolves correctly; writable dist dir; matches existing `build_exe.py` | Multiple files in dist/; larger footprint |
| `--onefile` | Single portable .exe | `_MEIPRESS` is a read-only temp dir; writable dirs fail; `__file__`-based paths in subprocess are fragile |

**Decision**: `--onedir` — aligns with existing `build_exe.py` infrastructure and avoids the read-only `_MEIPRESS` problem for writable directories (`labels/`, `receipts/`, `backups/`).

### 3.2 `noarchive` Setting

| Setting | Behavior | Subprocess Impact |
|---|---|---|
| `noarchive=False` (default) | Pure Python modules bundled into `.pyz` zip; `__file__` points inside zip | `label_engine/main.py` NOT accessible as real file → subprocess fails |
| `noarchive=True` | All `.py` files extracted to disk; `__file__` = real filesystem path | `label_engine/main.py` accessible at `_MEIPRESS/label_engine/main.py` → subprocess works |

**Decision**: Set `noarchive=True` in the spec. This is the single change that resolves the core MEIPASS/subprocess file-access problem. Trade-off: slightly larger dist directory and marginally slower startup (negligible for `--onedir`).

### 3.3 Data File Bundling (`datas` list)

The spec's `Analysis.datas` list must include:

```python
datas=[
    # Config + data files → bundle root (.)
    (r'archive\config.json', '.'),
    (r'archive\pharmacy.db', '.'),
    (r'archive\licenses.db', '.'),
    (r'archive\label_template.json', '.'),

    # Directory bundles → preserve directory structure
    (r'archive\locales', 'locales'),
    (r'archive\labels', 'labels'),

    # label_engine/ as data → needed by subprocess (noarchive=True makes these real files,
    # but explicit --add-data ensures they're treated as data, not pure code)
    (r'archive\label_engine', 'label_engine'),
]
```

> **Why bundle `label_engine/` as both a package import AND data?** PyInstaller auto-includes it as a Python package (from the `ui.py` import). Adding it as a data directory ensures the files exist at the expected filesystem paths for the subprocess. With `noarchive=True`, PyInstaller already writes `.py` files to disk, so the explicit `--add-data` is belt-and-suspenders. **Recommendation**: Include it for robustness; PyInstaller dedupes.

### 3.4 Binary Dependencies (`binaries` list)

Check for compiled extensions. The `PharmacyPro_Enterprise.spec` references `rust_crypto.pyd` and `hw_client.pyd`, but these do NOT exist in `archive/` (confirmed via file listing). Only include them if present:

```python
binaries = []
for ext in ("rust_crypto.pyd", "hw_client.pyd"):
    if os.path.isfile(os.path.join(archive_dir, ext)):
        binaries.append((os.path.join(archive_dir, ext), '.'))
```

### 3.5 CustomTkinter Assets

The `archive/build_exe.py` already handles this via `_collect_customtkinter_data()`:

```python
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)
assets_path = os.path.join(ctk_path, "assets")
# → --add-data=<assets_path>;customtkinter\assets
```

**Include** this in the spec or as a runtime hook.

### 3.6 Spec File Structure (Template)

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    [r'archive\main_app.py'],
    pathex=[r'archive'],
    binaries=[...],
    datas=[...],           # Section 3.3
    hiddenimports=[...],   # Section 4
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[...],        # Section 5
    noarchive=True,        # Section 3.2 — CRITICAL
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PharmacyPro_Enterprise',
    debug=False,
    strip=False,
    upx=True,
    console=False,          # Section 6 — Silent execution
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

> **Note**: With `--onedir` + `noarchive=True`, the `EXE` block bundles `a.binaries` and `a.datas` directly into the exe (no `COLLECT` needed). Alternatively, use the `COLLECT` pattern for onedir. The existing `PharmacyPro_Rx.spec` uses `COLLECT`; the `PharmacyPro_Enterprise.spec` does NOT use `COLLECT` (bundles directly into EXE). Both work; `COLLECT` is the more standard onedir approach.

---

## 4. Dependency Management — Hidden Imports

### 4.1 Problem Statement

PyInstaller performs static analysis to find imports. Some packages use dynamic imports, lazy loading, or conditional imports that escape static analysis. The following packages are confirmed missing from the existing `PharmacyPro_Enterprise.spec`:

### 4.2 Required Hidden Imports

| Module | Source File(s) | Why Needed |
|---|---|---|
| `customtkinter` | ui.py, main.py, label_engine/main.py | Dynamic theme loading — already in existing spec ✓ |
| `PIL` | ui.py:8, barcode_logic.py:10, canvas_core.py:11 | Plugin-based image format loading; PIL imports submodules dynamically |
| `PIL.ImageTk` | canvas_core.py:11 | Tkinter image bridge — separate from PIL core |
| `PIL.ImageDraw` | barcode_logic.py:10, canvas_core.py:11 | Drawing operations |
| `PIL.ImageFont` | barcode_logic.py:10, canvas_core.py:11 | Font rendering |
| `barcode` | barcode_logic.py:8, canvas_core.py:8 | python-barcode — dynamically selects writer classes |
| `barcode.writer` | barcode_logic.py:9, canvas_core.py:9 | ImageWriter subclass — dynamically loaded |
| `qrcode` | canvas_core.py:10 | QR code generation — plugin-based constants |
| `qrcode.constants` | canvas_core.py:10 | ERROR_CORRECT_H constant — accessed via `qrcode.constants` |
| `sqlalchemy` | db.py:26 | ORM engine creation |
| `sqlalchemy.orm` | db.py:29 | `declarative_base`, `sessionmaker` |
| `sqlalchemy.ext.declarative` | (potential) | Declarative base support |

### 4.3 Additional Hidden Imports (Application Modules)

All application modules that are imported dynamically or via `import X` at runtime:

```
label_engine, label_engine.canvas_core, label_engine.export,
label_engine.main, label_engine.properties_panel,
i12n, db, database, ui, ui_helpers, ui_modals, ui_add_tab,
ui_inventory_tab, ui_expiring_tab, ui_dashboard_tab, ui_report_tab,
ui_receive_tab, ui_checkout_tab, ui_templates_tab, ui_settings_tab,
ui_patients_tab, excel_handler, barcode_listener, crypto_utils,
async_ui, design_system, ocr_cascade, ocr_engine, audit_log,
backup, alert_engine, license_gate, updater, receipt_engine,
receipt_template, pos_engine, smart_parser, auto_extract,
```

### 4.4 Hidden Import Strategy

For third-party packages, use PyInstaller's `collect_all()` or `collect_submodules()` hooks in the spec:

```python
from PyInstaller.utils.hooks import collect_all

datas_ctk, binaries_ctk, hidden_ctk = collect_all('customtkinter')
datas_pil, binaries_pil, hidden_pil = collect_all('PIL')
datas_barcode, binaries_barcode, hidden_barc = collect_all('barcode')
datas_qrcode, binaries_qrcode, hidden_qr = collect_all('qrcode')
datas_sqla, binaries_sqla, hidden_sqla = collect_all('sqlalchemy')
```

These hooks automatically collect data files, binaries, and hidden imports. Merge results into the spec's `datas`, `binaries`, and `hiddenimports` lists respectively.

> **Alternative** (simpler CLI approach): Use `--collect-all` for each problematic package instead of manual `--hidden-import` entries:
> ```
> --collect-all customtkinter --collect-all PIL --collect-all barcode
> --collect-all qrcode --collect-all sqlalchemy
> ```

---

## 5. Subprocess Resilience — The MEIPASS Problem

### 5.1 Problem Analysis

The application launches the Label Design Engine (`label_engine/main.py`) as a **subprocess** via `barcode_logic.open_label_engine()` (called from `ui_inventory_tab.py:337` and `ui_modals.py:182,828`). Two path-resolution issues exist:

#### Issue A: `barcode_logic.py` — subprocess path resolution (lines 47–109)

```python
engine_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_engine", "main.py")
```

When frozen with `noarchive=False`, `__file__` points inside the `.pyz` archive (e.g., `_MEIPRESS/pyz.pyz/barcode_logic.py`). The resolved `engine_path` is `_MEIPASS/pyz.pyz/label_engine/main.py` — **not a real file** — causing `subprocess.Popen` to fail with `FileNotFoundError`.

When frozen with `noarchive=True`, `__file__` resolves to the real file `_MEIPRESS/barcode_logic.py`, so `engine_path` = `_MEIPRESS/label_engine/main.py` — **a real file** (because `noarchive=True` extracts all `.py` files to disk). ✓

**Fix applied by `noarchive=True`**: No code change needed. The `noarchive=True` setting alone resolves this.

> **Future hardening**: Replace `__file__`-based path with `get_resource_path(os.path.join("label_engine", "main.py"))` for explicit MEIPASS awareness. This is already done in `main_app.py:L9` (`_LABEL_ENGINE = get_resource_path(...)`), but `barcode_logic.py` (the one actually called by the UI) does not use it. Recommendation: update `barcode_logic.py` to use `get_resource_path` in Phase 14 implementation.

#### Issue B: `label_engine/export.py` — module-level constants (lines 20–21)

```python
LABELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "labels")
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "label_template.json")
```

These constants are evaluated at **import time** (when `ui.py:22` imports `TEMPLATE_PATH` from `label_engine.export`). With `noarchive=False`, `__file__` is inside the `.pyz` → paths point into the zip → `os.path.exists(TEMPLATE_PATH)` returns False → template loading silently fails.

With `noarchive=True`, `__file__` = `_MEIPRESS/label_engine/export.py` → `TEMPLATE_PATH` = `_MEIPRESS/label_template.json` → **real file** (bundled via `--add-data`). ✓

**Fix applied by `noarchive=True` + `--add-data` for `label_template.json`**: No code change needed.

> **Future hardening**: Replace `__file__`-based constants with `get_resource_path("label_template.json")` and `get_resource_path("label_engine/data/labels")`. This makes the module explicitly MEIPASS-aware rather than relying on `noarchive=True` behavior.

### 5.2 Subprocess Python Interpreter

`barcode_logic.py:_find_python_executable()` (lines 17–43):
1. Checks `archive/venv/Scripts/python.exe` → **does not exist** in dist
2. Checks `archive/../venv/Scripts/python.exe` → **does not exist** in dist
3. Checks `archive/.venv/Scripts/python.exe` → **does not exist** in dist
4. If `sys.frozen`: searches `PATH` for `python`, `python3`, `python.exe`, `python3.exe`
5. Falls back to `sys.executable` (the `.exe` bootloader — **cannot run .py scripts**)

**Requirement**: The target Windows machine must have Python 3.12+ installed and on `PATH`. This is a **hard dependency** for the Label Design Engine subprocess.

**Mitigation strategy** (documented, not implemented in Phase 14):
- Ship a `REDIST_PYTHON.md` notice documenting the Python requirement
- The frozen main app can check for Python availability at startup and warn the user if the label engine cannot launch

### 5.3 Writable Directory Strategy (onedir)

With `--onedir`, `_MEIPRESS` = the dist directory (writable). The following directories are created at runtime:
- `labels/` — created by `barcode_logic.init_labels_dir()` (called in `main.py:54`)
- `receipts/`, `backups/` — created by `path_utils.ensure_runtime_directories()` (called in `main.py:20`)
- `label_engine/data/labels/` — created by `export._ensure_labels_dir()` (called inside label engine)

**No additional bundling needed** for these writable directories. They will be auto-created in the dist directory on first run.

### 5.4 Path Resolution Summary (Frozen, `--onedir`, `noarchive=True`)

| Component | Path Resolution | Frozen Result | Correct? |
|---|---|---|---|
| `barcode_logic.CONFIG_FILE` | `get_resource_path("config.json")` | `_MEIPRESS/config.json` | ✓ |
| `barcode_logic.LABELS_DIR` | `get_resource_path("labels")` | `_MEIPRESS/labels/` | ✓ |
| `barcode_logic.engine_path` | `os.path.dirname(__file__)` + `"label_engine/main.py"` | `_MEIPRESS/label_engine/main.py` | ✓ (with noarchive=True) |
| `db.py` DB path | `get_resource_path("pharmacy.db")` | `_MEIPRESS/pharmacy.db` | ✓ |
| `label_engine.export.TEMPLATE_PATH` | `os.path.dirname(__file__)` + `"../label_template.json"` | `_MEIPRESS/label_template.json` | ✓ |
| `label_engine.export.LABELS_DIR` | `os.path.dirname(__file__)` + `"data/labels"` | `_MEIPRESS/label_engine/data/labels/` | ✓ |

---

## 6. Silent Execution — Windowed Mode

### 6.1 Main Application

- Set `console=False` (or `--noconsole` in CLI) in the PyInstaller spec/EXE block.
- The existing `main.spec` and `PharmacyPro_Enterprise.spec` already have `console=False`. ✓
- The existing `build_exe.py` conditionally appends `--noconsole` for production builds (line 115). ✓

### 6.2 Subprocess (Label Engine)

`barcode_logic.open_label_engine()` launches the label engine with:
```python
creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
```
This uses the Windows `CREATE_NO_WINDOW` flag to suppress the console window for the subprocess. ✓

**No changes needed** — this is already handled.

### 6.3 Crash Reporter

`main.py:18` calls `install_crash_reporter()` before anything else. When `console=False`, the crash reporter should write to a file rather than stderr. Verify that `crash_reporter.py` uses file-based logging, not console output. (This is an existing component; no Phase 14 changes required unless the crash reporter relies on console output.)

---

## 7. Exact PyInstaller Command-Line Arguments

### 7.1 CLI Build Command (using `build_exe.py` approach)

```bat
pyinstaller ^
  archive\main_app.py ^
  --onedir ^
  --name PharmacyPro_Enterprise ^
  --noconsole ^
  --noconfirm ^
  --noarchive ^
  --distpath archive\dist ^
  --workpath archive\build ^
  --specpath archive ^
  --pathex archive ^
  --collect-all customtkinter ^
  --collect-all PIL ^
  --collect-all barcode ^
  --collect-all qrcode ^
  --collect-all sqlalchemy ^
  --add-data "archive\config.json;." ^
  --add-data "archive\pharmacy.db;." ^
  --add-data "archive\licenses.db;." ^
  --add-data "archive\label_template.json;." ^
  --add-data "archive\locales;locales" ^
  --add-data "archive\labels;labels" ^
  --add-data "archive\label_engine;label_engine" ^
  --add-data "archive\receipts;receipts" ^
  --add-data "archive\backups;backups"
```

### 7.2 Spec File Generation

Alternatively, generate a spec file and run `pyinstaller <spec>`:

```python
# Spec: archive/PharmacyPro_Enterprise.spec
# Generated by: python archive/build_exe.py
# Key differences from existing spec:
#   - noarchive=True (critical for subprocess file access)
#   - collect_all() for customtkinter, PIL, barcode, qrcode, sqlalchemy
#   - label_engine/ added as data directory
#   - label_template.json added as data file
#   - labels/ added as data directory
```

### 7.3 Build Automation Updates

Update `archive/build_exe.py` to:
1. Add `--noarchive` flag
2. Add `label_template.json` to data files
3. Add `labels/` directory to data files
4. Add `label_engine/` directory to data files
5. Add `receipts/` and `backups/` directories to data files (if they exist)
6. Replace individual `--hidden-import` entries for third-party packages with `--collect-all`

---

## 8. Verification Plan

### 8.1 Pre-Build Checks

| Check | Method | Expected |
|---|---|---|
| Entry point exists | `os.path.isfile(archive/main_app.py)` | True |
| All asset files present | Loop through asset inventory in §2.1 | All present |
| PyInstaller installed | `pip show pyinstaller` | v6.x+ |
| Python 3.12+ available | `python --version` | ≥3.12 |
| All modules compile | `python -m py_compile archive/*.py archive/label_engine/*.py` | No errors |

### 8.2 Post-Build Checks

| Check | Method | Expected |
|---|---|---|
| Executable exists | `os.path.isfile(archive/dist/PharmacyPro_Enterprise/PharmacyPro_Enterprise.exe)` | True |
| Config bundled | `os.path.exists(_MEIPRESS/config.json)` | True |
| Label template bundled | `os.path.exists(_MEIPRESS/label_template.json)` | True |
| Locales bundled | `os.path.isdir(_MEIPRESS/locales)` | True |
| label_engine on disk | `os.path.isfile(_MEIPRESS/label_engine/main.py)` | True |
| No console window | Launch exe — verify no terminal appears | ✓ |

### 8.3 Runtime Checks

| Check | Method | Expected |
|---|---|---|
| App launches | Double-click exe | Window opens, no crash |
| Config loads | `get_resource_path("config.json")` resolves | File readable |
| Label engine subprocess | Click "Open Label Designer" button | New window opens |
| Template loads | Label engine opens with existing template | Template elements visible |
| Label save/load | Save a template, close, reopen | Template persists |

### 8.4 Reuse Existing Test Infrastructure

`archive/exhaustive_verify.py` Category 9 (lines 1025–1069) already tests:
- Import of `path_utils`
- `get_resource_path("x")` returns valid path
- MEIPASS simulation: sets `sys._MEIPASS = "/tmp/test_meipass"`, verifies `get_resource_path("test.txt")` returns path containing the MEIPASS prefix
- `ensure_runtime_directories()` creates expected directories

**Run**: `python archive/exhaustive_verify.py` and verify Category 9 passes.

---

## 9. Execution Roadmap (Verifiable Goals)

| # | Milestone | Verifiable Goal | Status |
|---|---|---|---|
| P14.1 | Update `build_exe.py` | Script includes `--noarchive`, `label_template.json`, `labels/`, `label_engine/` in data files; uses `--collect-all` for 3rd-party packages | ⬜ |
| P14.2 | Harden `barcode_logic.py` path resolution | `open_label_engine()` uses `get_resource_path()` instead of `__file__`-based path | ⬜ |
| P14.3 | Harden `label_engine/export.py` path resolution | `TEMPLATE_PATH` and `LABELS_DIR` use `get_resource_path()` instead of `__file__`-based paths | ⬜ |
| P14.4 | Generate spec file | PyInstaller spec generated with `noarchive=True`, all data files, all hidden imports | ⬜ |
| P14.5 | Build executable | `pyinstaller` exits with code 0; `dist/PharmacyPro_Enterprise.exe` exists | ⬜ |
| P14.6 | Silent execution verification | No console window spawns on launch | ⬜ |
| P14.7 | Subprocess resilience verification | Clicking "Open Label Designer" launches the engine without path errors | ⬜ |
| P14.8 | Template I/O verification | Label template loads and saves correctly in frozen exe | ⬜ |
| P14.9 | Full smoke test | Add product, save, open label designer, export PNG, complete checkout, generate receipt — all operational in frozen exe | ⬜ |

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `noarchive=True` not set → subprocess can't find `label_engine/main.py` | Critical — label design engine completely broken | Set `noarchive=True` in spec; verify `dist/.../label_engine/main.py` exists |
| `label_template.json` not bundled → templates silently don't load | High — label designer opens empty | Add `--add-data` for `label_template.json`; verify file exists in dist |
| `qrcode`/`barcode` not in hidden imports → ImportError at runtime | Critical — barcode rendering fails | Use `--collect-all qrcode --collect-all barcode` |
| Python not on target PATH → label engine subprocess fails to launch | High — label design engine unavailable | Document Python 3.12+ requirement; add startup check in `barcode_logic._find_python_executable()` |
| `pharmacy.db` bundled as read-only → writes fail | High — no inventory/sales persistence | Bundle seed DB but allow writes via SQLite file I/O; verify DB is writable in dist directory |
| CustomTkinter assets not bundled → theme breaks | Medium — UI renders without styling | Use `collect_all('customtkinter')` for assets |
| `--onedir` dist directory too large → slow first launch | Low — UX friction only | Acceptable trade-off for subprocess file access and writable directories |
