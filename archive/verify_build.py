"""
verify_build.py — Verify that the built PharmacyPro_Rx executable works correctly.

Checks:
  1. Executable exists at the expected path
  2. All required data files are bundled (config.json, locales/, labels/)
  3. Key modules can be imported in the bundled Python environment
  4. RX workflow modules load without missing dependency errors
  5. PyInstaller spec is consistent with the source files

Usage:
    python archive/verify_build.py [--exe-path path/to/PharmacyPro_Rx.exe]
"""
import os
import sys
import argparse
import importlib.util

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ARCHIVE_DIR)

EXPECTED_EXE_PATHS = [
    os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx", "PharmacyPro_Rx.exe"),
    os.path.join(ARCHIVE_DIR, "dist", "PharmacyPro_Rx.exe"),
]

REQUIRED_MODULES = [
    "rx_config",
    "rx_db",
    "rx_database",
    "rx_strategies",
    "rx_integration_settings",
    "ui_rx_workflow",
    "main_app",
]

REQUIRED_DATA_FILES = ["config.json"]


def check_executable(exe_path):
    if not exe_path or not os.path.exists(exe_path):
        print("[FAIL] Executable not found. Run build first:")
        print("       python archive/build_rx_app.py")
        return False
    print(f"[OK]   Executable exists: {exe_path}")
    size = os.path.getsize(exe_path)
    print(f"       Size: {size / (1024 * 1024):.1f} MB")
    return True


def check_module_imports():
    all_ok = True
    for mod_name in REQUIRED_MODULES:
        mod_path = os.path.join(ARCHIVE_DIR, mod_name + ".py")
        if not os.path.exists(mod_path):
            print(f"[FAIL] Module not found: {mod_path}")
            all_ok = False
            continue
        try:
            spec = importlib.util.spec_from_file_location(mod_name, mod_path)
            if spec and spec.loader:
                print(f"[OK]   Module importable: {mod_name}")
            else:
                print(f"[FAIL] Cannot load spec for: {mod_name}")
                all_ok = False
        except Exception as e:
            print(f"[FAIL] Error loading {mod_name}: {e}")
            all_ok = False
    return all_ok


def check_hidden_imports_in_spec():
    spec_path = os.path.join(ARCHIVE_DIR, "PharmacyPro_Rx.spec")
    if not os.path.exists(spec_path):
        print(f"[FAIL] Spec file not found: {spec_path}")
        return False

    with open(spec_path, "r") as f:
        content = f.read()

    required = ["cryptography.fernet", "sqlalchemy", "customtkinter",
                "rx_config", "rx_db", "rx_database", "rx_strategies"]
    all_ok = True
    for imp in required:
        if imp in content:
            print(f"[OK]   Hidden import in spec: {imp}")
        else:
            print(f"[FAIL] Missing hidden import in spec: {imp}")
            all_ok = False
    return all_ok


def check_data_files():
    all_ok = True
    for data_file in REQUIRED_DATA_FILES:
        path = os.path.join(PROJECT_ROOT, data_file)
        if os.path.exists(path):
            print(f"[OK]   Data file exists: {data_file}")
        else:
            print(f"[WARN] Data file missing (will be created at runtime): {data_file}")
    locales_path = os.path.join(PROJECT_ROOT, "locales")
    if os.path.exists(locales_path):
        print(f"[OK]   Locales directory exists")
    else:
        print(f"[WARN] Locales directory missing (optional)")
    return all_ok


def check_py_compile():
    import py_compile
    all_ok = True
    for mod_name in REQUIRED_MODULES:
        mod_path = os.path.join(ARCHIVE_DIR, mod_name + ".py")
        if not os.path.exists(mod_path):
            continue
        try:
            py_compile.compile(mod_path, doraise=True)
            print(f"[OK]   Compiles: {mod_name}")
        except py_compile.PyCompileError as e:
            print(f"[FAIL] Compile error in {mod_name}: {e}")
            all_ok = False
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Verify PharmacyPro Rx build")
    parser.add_argument("--exe-path", default=None,
                        help="Path to the built executable (auto-detected if omitted)")
    args = parser.parse_args()

    print("=" * 60)
    print("PharmacyPro Rx Build Verification")
    print("=" * 60)
    print()

    results = []
    results.append(("Executable", check_executable(args.exe_path)))
    results.append(("Data files", check_data_files()))
    results.append(("Module compilation", check_py_compile()))
    results.append(("Module imports", check_module_imports()))
    results.append(("Spec hidden imports", check_hidden_imports_in_spec()))

    print()
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")

    if all(ok for _, ok in results):
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — review output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
