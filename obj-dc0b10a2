# Plan: Fix `barcode_logic.py` `create_label` NameError

## Context

During the architectural audit, a runtime bug was found in `archive/barcode_logic.py`:

- **File:** `archive/barcode_logic.py`
- **Function:** `create_label(price: float, internal_barcode: str) -> str` (module-level, line 219)
- **Bug:** Lines 240 and 253 reference `self.app.currency.fmt(price)`, but `self` is not defined in this module-level function scope. This raises `NameError` whenever `create_label` is called with `include_price=True` (the default).
- **Root cause:** Code was apparently copied from a class method (where `self` is the main app instance) but the function was written as a standalone module-level function.

The sibling function `generate_preview_image` (line 267) already demonstrates the correct pattern — it formats the price as a plain string `"$0.00"` from an `overrides` dict, with no dependency on `self` or the app instance.

## Goal

Fix the `NameError` in `create_label` so that label generation works in production without crashing.

## Scope

**In scope:**
1. Replace `self.app.currency.fmt(price)` at lines 240 and 253 with a simple, dependency-free currency formatter.
2. Add a test that calls `create_label` end-to-end and verifies a PNG file is produced (TDD: write test first, confirm it fails, then fix).
3. Run the existing `archive/test_phase9_final_validation.py` to confirm no regression.
4. Update `PROJECT_MAP.md` / `FLOW_LOGIC.md` if applicable.

**Out of scope:**
- Refactoring the entire label-generation pipeline.
- Changing `generate_preview_image` or any other function.
- Any database, UI, or backend changes.

## Affected Files

| File | Change |
|------|--------|
| `archive/barcode_logic.py` | Fix lines 240 and 253 (replace `self.app.currency.fmt(price)`) |
| `archive/test_barcode_label_fix.py` | New test file (created as part of TDD) |
| `archive/test_phase9_final_validation.py` | Run only (no edits) |

## Proposed Fix

In `archive/barcode_logic.py`, add a small standalone helper at module level (after the imports, before `create_label`):

```python
def _format_price(price: float) -> str:
    return f"${price:.2f}"
```

Then replace:
- Line 240: `self.app.currency.fmt(price)` → `_format_price(price)`
- Line 253: `self.app.currency.fmt(price)` → `_format_price(price)`

## Test Plan (TDD)

1. **Write:** Create `archive/test_barcode_label_fix.py` that:
   - Sets `PHARMACY_DB_PATH` to a temp file for isolation.
   - Calls `create_label(price=19.99, internal_barcode="TEST-001")`.
   - Asserts the returned path exists and is a valid PNG file > 0 bytes.
   - Cleans up the temp file.
2. **Confirm failure:** Run the test before the fix — it should fail with `NameError: name 'self' is not defined`.
3. **Apply fix:** Edit `barcode_logic.py` lines 240 and 253.
4. **Confirm pass:** Run the test again — it should pass.
5. **Regression:** Run `python -m pytest archive/test_phase9_final_validation.py -x -q` or `python archive/test_phase9_final_validation.py` to verify existing tests still pass.

## Risks

- The fix changes price formatting from whatever `self.app.currency.fmt` produced to `"$19.99"`. This is acceptable because `generate_preview_image` already uses plain string price formatting, and the function is module-level (the app instance is not available).
- No database or UI components are touched, so regression risk is minimal.
