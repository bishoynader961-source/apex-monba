# Fix: `test_dev_mode_active_when_not_frozen` vs `is_dev_mode()` mismatch

**File under test:** `archive/license_gate.py` (`is_dev_mode`, lines 63–87)
**Test:** `archive/test_security.py` (`test_dev_mode_active_when_not_frozen`, lines 71–94)
**Mode:** Plan only — implementation left to an execution-capable agent. Do NOT edit
`license_gate.py` production logic (it is security-critical and correct).

---

## 1. Root-cause analysis (the discrepancy)

`is_dev_mode()` permits the license bypass **only** when ALL hold:
1. `sys.frozen` is falsy (not a PyInstaller build), AND
2. **either** `os.environ["PHARMACY_DEV_MODE"] == "1"` **or** the ghost-token file
   `~/.pharmacy_dev.key` exists.

It does **not** read `dev_config.json` anywhere in the body. Evidence:
- `license_gate.py:78` → env var check.
- `license_gate.py:81-83` → `~/.pharmacy_dev.key` check.
- `license_gate.py:54` → `DEV_CONFIG_FILE = "dev_config.json"` is **defined but never used**
  in `is_dev_mode()` (dead constant).
- The docstring at `license_gate.py:68` *claims* `dev_config.json` triggers dev mode —
  this stale docstring is what misled the test author. `dev_config.json` is in fact a
  runtime **config** file (carries `font_size`, `database_url`, etc.) and legitimately
  ships in the repo; it must never be a bypass trigger.

The test (`test_security.py:48-53`, `:81`) creates `dev_config.json` (via
`_write_dev_config`) and expects `is_dev_mode()` to return `True`. Because the function
ignores that file, it returns `False` → the test fails. This is a **test defect**, not a
production bug. The implementation is the intended behavior (frozen builds are
structurally blocked; bypass requires an explicit env var or a developer-only ghost key).

## 2. Decision: align the TEST, not the implementation

Changing `is_dev_mode()` to honor `dev_config.json` would accidentally re-enable the
bypass for any machine that already has the shipped config file present — a security
regression. The correct fix is to make the test trigger the **real** mechanism.

Two valid triggers:
- **A.** Set `os.environ["PHARMACY_DEV_MODE"] = "1"` for the test duration (cleanest,
  deterministic, no filesystem side effects). **Recommended.**
- B. Create `~/.pharmacy_dev.key` (the ghost-token) and remove it in cleanup. Works but
  touches the user home dir and is less isolated.

Use **A**. Also remove the now-misleading `dev_config.json` helpers from this test's
setup (or keep them unused) and drop the dead `DEV_CONFIG_FILE` import if it is only
used by this test.

## 3. Affected files
- `archive/test_security.py` — modify `test_dev_mode_active_when_not_frozen` (and its
  `_write_dev_config`/`_remove_dev_config` usage within that test) to use the env var.
  No change to `license_gate.py`.

## 4. Corrected test code (drop-in replacement for `test_dev_mode_active_when_not_frozen`)

```python
def test_dev_mode_active_when_not_frozen():
    """Simulate dev environment: not frozen AND PHARMACY_DEV_MODE=1.

    Per license_gate.is_dev_mode(), the bypass triggers on the
    PHARMACY_DEV_MODE env var (or a ~/.pharmacy_dev.key ghost token) — NOT
    on dev_config.json, which is a runtime config file.
    """
    had_frozen = hasattr(sys, "frozen")
    old_frozen = getattr(sys, "frozen", None)
    old_env = os.environ.get("PHARMACY_DEV_MODE")

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
```

Notes for the executor:
- If the test module imports `DEV_CONFIG_FILE` solely for this test, remove that import
  (it is unused by `is_dev_mode`).
- The existing `_write_dev_config`/`_remove_dev_config` helpers may be left in place if
  other tests use them; this test no longer calls them.

## 5. Verification
- Run `python archive/test_security.py` → `test_dev_mode_active_when_not_frozen` now
  reports `PASS`; the suite should reach `7/7 passed`.
- Regression check: `test_dev_mode_blocked_when_frozen` (frozen=True) still returns
  `False` (security posture intact). `test_no_dev_config_file` and
  `test_dev_config_disabled` still return `False`.
- Confirm `archive/license_gate.py` is byte-for-byte unchanged (no production edit).

## 6. Open question (out of scope, flag only)
The docstring at `license_gate.py:68` still falsely documents `dev_config.json` as a
trigger. Optional follow-up (separate plan): correct the docstring to match the env-var /
ghost-token reality. Do **not** implement as part of this fix unless explicitly requested.
