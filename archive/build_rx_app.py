"""
build_rx_app.py — PyInstaller build automation for the Rx Workflow standalone executable.

Builds a standalone executable that includes:
  - All archive/ Python modules (rx_config, rx_db, rx_database, rx_strategies, ui_rx_workflow, etc.)
  - Hidden imports: cryptography, cryptography.fernet, sqlalchemy, customtkinter
  - Data: config.json, locales/, labels/
  - Output: dist/PharmacyPro_Rx/PharmacyPro_Rx.exe

Usage:
    python archive/build_rx_app.py [--debug] [--onefile]

The built executable can be verified with:
    python archive/verify_build.py
"""
import os
import sys
import subprocess
import argparse
import platform

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ARCHIVE_DIR)

APP_ENTRY = os.path.join(ARCHIVE_DIR, "main_app.py")

HIDDEN_IMPORTS = [
    "customtkinter",
    "cryptography",
    "cryptography.fernet",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext.declarative",
    "barcode_logic",
    "database",
    "db",
    "rx_config",
    "rx_database",
    "rx_db",
    "rx_strategies",
    "rx_integration_settings",
    "ui_rx_workflow",
    "ui_patients_tab",
    "ui_navigation",
    "audit_log",
    "path_utils",
    "async_ui",
    "design_system",
    "i18n",
    "crypto_utils",
    "receipt_engine",
    "excel_handler",
    "barcode_listener",
    "ui",
    "ui_helpers",
    "ui_modals",
    "ui_add_tab",
    "ui_inventory_tab",
    "ui_expiring_tab",
    "ui_dashboard_tab",
    "ui_report_tab",
    "ui_receive_tab",
    "ui_checkout_tab",
    "ui_templates_tab",
    "ui_settings_tab",
]

DATA_DIRS = [
    ("config.json", "."),
    ("pharmacy.db", "."),
    ("rx_config.json", "."),
    ("locales", "locales"),
    ("labels", "labels"),
]

BINARY_ASSETS = []


def build_spec_content(debug=False, onefile=False):
    app_entry = APP_ENTRY.replace(os.sep, '/')
    archive_dir = ARCHIVE_DIR.replace(os.sep, '/')
    project_root = PROJECT_ROOT.replace(os.sep, '/')

    lines = [
        "# -*- mode: python ; coding: utf-8 -*-",
        "",
    ]

    if onefile:
        lines.append(f"A = Analysis(['{app_entry}'],")
    else:
        lines.append(f"a = Analysis(['{app_entry}'],")
    lines.append(f"    pathex=['{archive_dir}', '{project_root}'],")
    lines.append(f"    binaries={BINARY_ASSETS},")
    lines.append("    datas=[")

    for src, dst in DATA_DIRS:
        src_path = os.path.join(PROJECT_ROOT, src)
        if os.path.exists(src_path):
            src_path_norm = src_path.replace(os.sep, '/')
            lines.append(f"        (r'{src_path_norm}', '{dst}'),")

    lines.append("    ],")
    lines.append("    hiddenimports=[")
    for imp in HIDDEN_IMPORTS:
        lines.append(f"        '{imp}',")
    lines.append("    ],")
    lines.append("    hookspath=[],")
    lines.append("    hooksconfig={},")
    lines.append("    runtime_hooks=[],")
    lines.append("    excludes=[],")
    lines.append("    noarchive=False,")
    lines.append("    optimize=0,")
    lines.append(")")

    lines.append("pyz = PYZ(")
    if onefile:
        lines.append("    A.pure,")
    else:
        lines.append("    a.pure,")
    lines.append(")")

    lines.append("")
    if onefile:
        lines.append("exe = EXE(")
        lines.append("    pyz,")
        lines.append("    A.scripts,")
        lines.append("    A.binaries,")
        lines.append("    A.datas,")
        lines.append("    [],")
        lines.append("    name='PharmacyPro_Rx',")
        lines.append(f"    debug={'True' if debug else 'False'},")
        lines.append("    bootloader_ignore_signals=False,")
        lines.append("    strip=False,")
        lines.append("    upx=True,")
        lines.append("    upx_exclude=[],")
        lines.append("    runtime_tmpdir=None,")
        lines.append("    console=" + ("True" if debug else "False") + ",")
        lines.append("    disable_windowed_traceback=False,")
        lines.append("    argv_emulation=False,")
        lines.append("    target_arch=None,")
        lines.append("    codesign_identity=None,")
        lines.append("    entitlements_file=None,")
        lines.append(")")
    else:
        lines.append("exe = EXE(")
        lines.append("    pyz,")
        lines.append("    a.scripts,")
        lines.append("    [],")
        lines.append("    exclude_binaries=True,")
        lines.append("    name='PharmacyPro_Rx',")
        lines.append(f"    debug={'True' if debug else 'False'},")
        lines.append("    bootloader_ignore_signals=False,")
        lines.append("    strip=False,")
        lines.append("    upx=True,")
        lines.append("    upx_exclude=[],")
        lines.append("    runtime_tmpdir=None,")
        lines.append("    console=False,")
        lines.append("    disable_windowed_traceback=False,")
        lines.append("    argv_emulation=False,")
        lines.append("    target_arch=None,")
        lines.append("    codesign_identity=None,")
        lines.append("    entitlements_file=None,")
        lines.append(")")
        lines.append("coll = COLLECT(")
        lines.append("    exe,")
        lines.append("    a.binaries,")
        lines.append("    a.datas,")
        lines.append("    strip=False,")
        lines.append("    upx=True,")
        lines.append("    upx_exclude=[],")
        lines.append("    name='PharmacyPro_Rx',")
        lines.append(")")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Build PharmacyPro Rx standalone executable")
    parser.add_argument("--debug", action="store_true", help="Enable debug console")
    parser.add_argument("--onefile", action="store_true",
                        help="Bundle into a single .exe (default: onedir)")
    args = parser.parse_args()

    if not os.path.exists(APP_ENTRY):
        print(f"ERROR: Entry point not found: {APP_ENTRY}")
        print("Expected main_app.py in the archive/ directory.")
        sys.exit(1)

    spec_content = build_spec_content(debug=args.debug, onefile=args.onefile)
    spec_path = os.path.join(ARCHIVE_DIR, "PharmacyPro_Rx.spec")

    with open(spec_path, "w") as f:
        f.write(spec_content)

    print(f"Generated spec: {spec_path}")
    print(f"Entry point: {APP_ENTRY}")
    print(f"Debug mode: {args.debug}")
    print(f"Build mode: {'onefile' if args.onefile else 'onedir'}")
    print(f"Hidden imports: {len(HIDDEN_IMPORTS)}")
    print()

    cmd = [sys.executable, "-m", "PyInstaller", spec_path]
    if args.debug:
        cmd.append("--debug=all")

    print("Running PyInstaller...")
    result = subprocess.run(cmd, cwd=ARCHIVE_DIR)

    if result.returncode == 0:
        if args.onefile:
            exe_path = os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx.exe")
        else:
            exe_path = os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx", "PharmacyPro_Rx.exe")
        print(f"\nBuild successful: {exe_path}")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
