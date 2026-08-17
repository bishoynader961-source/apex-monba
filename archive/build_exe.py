"""PyInstaller build automation for Pharmacy Management System.

Usage:
    python build_exe.py              # Production build (no console)
    python build_exe.py --debug      # Debug build (with console)
    python build_exe.py --icon path/to/logo.ico  # Custom icon
"""
import subprocess
import sys
import os
import shutil
import argparse
import glob as _glob


ICON_SEARCH_NAMES = ["logo.ico", "app.ico", "pharmacy.ico", "icon.ico"]


def _find_icon(archive_dir: str, user_icon: str | None = None) -> str | None:
    """Locate a valid .ico file for the application.

    Search order:
      1. User-specified path (--icon flag)
      2. assets/logo.ico (or other known names) next to archive/
      3. Any .ico file inside archive/ or archive/assets/

    Returns the absolute path to the .ico file, or None if not found.
    """
    if user_icon:
        if os.path.isfile(user_icon):
            return os.path.abspath(user_icon)
        print(f"[WARN] --icon path not found: {user_icon}")
        return None

    # Check assets/ directory next to archive/
    parent_dir = os.path.dirname(archive_dir)
    assets_dir = os.path.join(parent_dir, "assets")
    if not os.path.isdir(assets_dir):
        assets_dir = os.path.join(archive_dir, "assets")

    for name in ICON_SEARCH_NAMES:
        candidate = os.path.join(assets_dir, name)
        if os.path.isfile(candidate):
            return candidate
        candidate = os.path.join(archive_dir, name)
        if os.path.isfile(candidate):
            return candidate

    # Fallback: any .ico in assets/
    if os.path.isdir(assets_dir):
        matches = _glob.glob(os.path.join(assets_dir, "*.ico"))
        if matches:
            return matches[0]

    return None


def _find_pyinstaller() -> str:
    """Locate the pyinstaller executable, preferring the project venv."""
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "venv", "Scripts", "pyinstaller.exe"),
        os.path.join(base, "venv", "Scripts", "pyinstaller"),
        os.path.join(os.path.dirname(base), "venv", "Scripts", "pyinstaller.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "pyinstaller"


def _collect_customtkinter_data() -> list[str]:
    """Return PyInstaller --add-data entries for CustomTkinter assets."""
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        assets_path = os.path.join(ctk_path, "assets")
        data_args = []
        if os.path.isdir(assets_path):
            dest = os.path.join("customtkinter", "assets")
            if sys.platform == "win32":
                sep = ";"
            else:
                sep = ":"
            data_args.append(f"--add-data={assets_path}{sep}{dest}")
        return data_args
    except ImportError:
        print("[WARN] customtkinter not installed — skipping asset bundle.")
        return []


def build(debug: bool = False, icon_path: str | None = None):
    """Run PyInstaller with the correct configuration."""
    archive_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(archive_dir, "main_app.py")
    output_name = "PharmacyPro_Enterprise"
    pyinstaller = _find_pyinstaller()

    if not os.path.isfile(entry_point):
        print(f"[ERROR] Entry point not found: {entry_point}")
        sys.exit(1)

    cmd = [
        pyinstaller,
        entry_point,
        "--onedir",
        "--name", output_name,
        "--distpath", os.path.join(archive_dir, "dist"),
        "--workpath", os.path.join(archive_dir, "build"),
        "--specpath", archive_dir,
        "--noconfirm",
    ]

    if not debug:
        cmd.append("--noconsole")
    else:
        print("[BUILD] Debug mode — console window will be visible.")

    # Custom application icon
    resolved_icon = _find_icon(archive_dir, icon_path)
    if resolved_icon:
        cmd.extend(["--icon", resolved_icon])
        print(f"[BUILD] Using icon: {resolved_icon}")
    else:
        print("[BUILD] No custom .ico found — using default PyInstaller icon.")

    # Collect CustomTkinter assets
    ctk_data = _collect_customtkinter_data()
    cmd.extend(ctk_data)

    # Hidden imports required by the app
    hidden = [
        "customtkinter",
        "requests",
        "urllib3",
        "ssl",
        "http.client",
        "database",
        "barcode_logic",
        "audit_log",
        "backup",
        "alert_engine",
        "license_gate",
        "updater",
        "receipt_engine",
        "path_utils",
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
        "ui_patients_tab",
        "excel_handler",
        "pos_engine",
        "receipt_template",
        "smart_parser",
        "auto_extract",
        "i18n",
        "db",
        "barcode_listener",
        "crypto_utils",
        "async_ui",
        "design_system",
        "ocr_cascade",
        "ocr_engine",
        "hw_client",
        "native_accel",
    ]
    for h in hidden:
        cmd.extend(["--hidden-import", h])

    # Data files
    data_files = []
    for fname in ("config.json", "pharmacy.db", "licenses.db"):
        fpath = os.path.join(archive_dir, fname)
        if os.path.isfile(fpath):
            if sys.platform == "win32":
                sep = ";"
            else:
                sep = ":"
            data_files.append(f"--add-data={fpath}{sep}.")

    # Bundle i18n locale files
    locales_dir = os.path.join(archive_dir, "locales")
    if os.path.isdir(locales_dir):
        if sys.platform == "win32":
            sep = ";"
        else:
            sep = ":"
        data_files.append(f"--add-data={locales_dir}{sep}locales")

    # Bundle compiled Rust extension binaries (.pyd files)
    for ext_name in ("rust_crypto.pyd", "hw_client.pyd", "barcode_gen.pyd"):
        ext_path = os.path.join(archive_dir, ext_name)
        if os.path.isfile(ext_path):
            if sys.platform == "win32":
                sep = ";"
            else:
                sep = ":"
            data_files.append(f"--add-binary={ext_path}{sep}.")

    cmd.extend(data_files)

    print(f"[BUILD] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=archive_dir)

    if result.returncode == 0:
        # --onedir puts the exe in a subdirectory: dist/<name>/<name>.exe
        onedir_exe = os.path.join(archive_dir, "dist", output_name, output_name + ".exe")
        if os.path.isfile(onedir_exe):
            print(f"\n[BUILD] Success! Output: {onedir_exe}")
            exe_size = os.path.getsize(onedir_exe)
            print(f"[BUILD] Executable: {onedir_exe} ({exe_size:,} bytes)")
        else:
            print(f"\n[BUILD] Success! Output: {os.path.join(archive_dir, 'dist')}")
    else:
        print(f"\n[BUILD] Failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Build Pharmacy Management System executable")
    parser.add_argument("--debug", action="store_true",
                        help="Build with console window for debugging")
    parser.add_argument("--icon", type=str, default=None,
                        help="Path to a custom .ico file for the application icon")
    args = parser.parse_args()
    build(debug=args.debug, icon_path=args.icon)


if __name__ == "__main__":
    main()
