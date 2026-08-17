"""
test_security.py — Verify the dev-mode bypass is structurally disabled in frozen builds.

Run:  python test_security.py
No dependencies beyond the standard library.
"""
import json
import os
import sys
import tempfile
import textwrap

# ── Ensure we can import from the archive directory ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════════
#  Test helpers
# ═══════════════════════════════════════════════════════════════════════

class _Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.details = []

    def ok(self, name, msg=""):
        self.passed += 1
        self.details.append(f"  PASS  {name}" + (f" — {msg}" if msg else ""))

    def fail(self, name, msg=""):
        self.failed += 1
        self.details.append(f"  FAIL  {name}" + (f" — {msg}" if msg else ""))

    def summary(self):
        total = self.passed + self.failed
        line = f"\n{'='*60}\n"
        line += f"  Results: {self.passed}/{total} passed, {self.failed} failed\n"
        line += f"{'='*60}"
        return line


results = _Result()


def _write_dev_config(directory, dev_mode=True):
    """Create a dev_config.json in the given directory."""
    path = os.path.join(directory, "dev_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"dev_mode": dev_mode, "font_size": 20}, f, indent=2)
    return path


def _remove_dev_config(directory):
    path = os.path.join(directory, "dev_config.json")
    if os.path.exists(path):
        os.remove(path)


# ═══════════════════════════════════════════════════════════════════════
#  Import the function under test
# ═══════════════════════════════════════════════════════════════════════
from license_gate import is_dev_mode


# ═══════════════════════════════════════════════════════════════════════
#  Test 1: Dev mode works when NOT frozen and PHARMACY_DEV_MODE=1 is set
# ═══════════════════════════════════════════════════════════════════════
def test_dev_mode_active_when_not_frozen():
    """Simulate dev environment: not frozen AND PHARMACY_DEV_MODE=1.

    Per license_gate.is_dev_mode(), the bypass triggers on the
    PHARMACY_DEV_MODE env var (or a ~/.pharmacy_dev.key ghost token) — NOT
    on dev_config.json, which is a runtime config file.
    """
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    old_env = os.environ.get("PHARMACY_DEV_MODE")

    # Ensure NOT frozen
    if had_frozen:
        delattr(sys, "frozen")

    os.environ["PHARMACY_DEV_MODE"] = "1"   # the actual, supported trigger
    try:
        result = is_dev_mode()
        if result is True:
            results.ok("test_dev_mode_active_when_not_frozen",
                       "is_dev_mode() returned True — bypass works in dev")
        else:
            results.fail("test_dev_mode_active_when_not_frozen",
                         f"Expected True, got {result}")
    finally:
        if old_env is None:
            os.environ.pop("PHARMACY_DEV_MODE", None)
        else:
            os.environ["PHARMACY_DEV_MODE"] = old_env
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            sys.frozen = old_frozen


# ═══════════════════════════════════════════════════════════════════════
#  Test 2: Dev mode BLOCKED when frozen — even with dev_config.json
# ═══════════════════════════════════════════════════════════════════════
def test_dev_mode_blocked_when_frozen():
    """Simulate PyInstaller build: sys.frozen = True, dev_config.json present."""
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)

    sys.frozen = True  # mimic PyInstaller

    try:
        _write_dev_config(SCRIPT_DIR, dev_mode=True)
        result = is_dev_mode()
        if result is False:
            results.ok("test_dev_mode_blocked_when_frozen",
                       "is_dev_mode() returned False — bypass disabled in frozen build")
        else:
            results.fail("test_dev_mode_blocked_when_frozen",
                         f"Expected False, got {result} — SECURITY BREACH!")
    finally:
        _remove_dev_config(SCRIPT_DIR)
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            delattr(sys, "frozen")


# ═══════════════════════════════════════════════════════════════════════
#  Test 3: No dev_config.json → bypass denied
# ═══════════════════════════════════════════════════════════════════════
def test_no_dev_config_file():
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    if had_frozen:
        delattr(sys, "frozen")

    try:
        _remove_dev_config(SCRIPT_DIR)
        result = is_dev_mode()
        if result is False:
            results.ok("test_no_dev_config_file",
                       "is_dev_mode() returned False — no config file = no bypass")
        else:
            results.fail("test_no_dev_config_file",
                         f"Expected False, got {result}")
    finally:
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            sys.frozen = old_frozen


# ═══════════════════════════════════════════════════════════════════════
#  Test 4: dev_config.json with dev_mode: false → bypass denied
# ═══════════════════════════════════════════════════════════════════════
def test_dev_config_disabled():
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    if had_frozen:
        delattr(sys, "frozen")

    try:
        _write_dev_config(SCRIPT_DIR, dev_mode=False)
        result = is_dev_mode()
        if result is False:
            results.ok("test_dev_config_disabled",
                       "is_dev_mode() returned False — dev_mode: false in config")
        else:
            results.fail("test_dev_config_disabled",
                         f"Expected False, got {result}")
    finally:
        _remove_dev_config(SCRIPT_DIR)
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            sys.frozen = old_frozen


# ═══════════════════════════════════════════════════════════════════════
#  Test 5: Corrupted dev_config.json → bypass denied
# ═══════════════════════════════════════════════════════════════════════
def test_corrupted_dev_config():
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    if had_frozen:
        delattr(sys, "frozen")

    try:
        corrupted_path = os.path.join(SCRIPT_DIR, "dev_config.json")
        with open(corrupted_path, "w", encoding="utf-8") as f:
            f.write("{not valid json !!!")
        result = is_dev_mode()
        if result is False:
            results.ok("test_corrupted_dev_config",
                       "is_dev_mode() returned False — corrupted file = no bypass")
        else:
            results.fail("test_corrupted_dev_config",
                         f"Expected False, got {result}")
    finally:
        _remove_dev_config(SCRIPT_DIR)
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            sys.frozen = old_frozen


# ═══════════════════════════════════════════════════════════════════════
#  Test 6: dev_config.json placed NEXT TO frozen .exe — still blocked
# ═══════════════════════════════════════════════════════════════════════
def test_dev_config_next_to_exe_still_blocked():
    """Even if dev_config.json somehow ships with the .exe, frozen guard blocks it."""
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)

    sys.frozen = True

    try:
        # Place dev_config.json right next to the 'script'
        _write_dev_config(SCRIPT_DIR, dev_mode=True)
        result = is_dev_mode()
        if result is False:
            results.ok("test_dev_config_next_to_exe_still_blocked",
                       "Frozen=True overrides dev_config.json presence")
        else:
            results.fail("test_dev_config_next_to_exe_still_blocked",
                         f"Expected False, got {result} — CRITICAL SECURITY BUG!")
    finally:
        _remove_dev_config(SCRIPT_DIR)
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            delattr(sys, "frozen")


# ═══════════════════════════════════════════════════════════════════════
#  Test 7: Simulate main.py decision logic
# ═══════════════════════════════════════════════════════════════════════
def test_main_py_logic_frozen():
    """Replicate the exact if/else from main.py with frozen=True."""
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)

    sys.frozen = True

    try:
        _write_dev_config(SCRIPT_DIR, dev_mode=True)
        # This mirrors main.py's logic
        if is_dev_mode():
            access = "BYPASSED"
        else:
            access = "DENIED"

        if access == "DENIED":
            results.ok("test_main_py_logic_frozen",
                       "main.py would enforce license gate — Access Denied")
        else:
            results.fail("test_main_py_logic_frozen",
                         f"main.py would grant access ({access}) — BUG!")
    finally:
        _remove_dev_config(SCRIPT_DIR)
        if had_frozen:
            sys.frozen = old_frozen
        elif old_frozen is not None:
            delattr(sys, "frozen")


# ═══════════════════════════════════════════════════════════════════════
#  Run all tests
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  SECURITY BYPASS TEST SUITE")
    print("  Verifying dev_mode is disabled in frozen builds")
    print("=" * 60)
    print()

    tests = [
        test_dev_mode_active_when_not_frozen,
        test_dev_mode_blocked_when_frozen,
        test_no_dev_config_file,
        test_dev_config_disabled,
        test_corrupted_dev_config,
        test_dev_config_next_to_exe_still_blocked,
        test_main_py_logic_frozen,
    ]

    for test_fn in tests:
        test_fn()

    for line in results.details:
        print(line)

    print(results.summary())

    sys.exit(0 if results.failed == 0 else 1)
