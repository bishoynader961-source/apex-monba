# Round 3 — New Bugs, Recurring Bugs, and Barcode Pattern Feature

**Context:** Manual testing of the rebuilt `.exe` found real, reproducible bugs that the automated Playwright suite reported as passing. Going forward, nothing in this file is "done" without a screenshot or the exact console/error text from the packaged app — restating a fix without that evidence will not be accepted as verification, given the track record so far.

---

## Section F — NEW BUG: Bulk Label Print & Bulk Import Tabs Throw Errors

Both tabs show a red "Unexpected error" banner immediately on open, plus two duplicate toast error popups ("Error — Unexpected error") in the bottom-right corner.

1. **Reproduce** — Open Bulk Label Print, open Bulk Import, capture the actual browser/Tauri console error and network request that's failing (likely a missing/broken API call fired on page load).
2. **Check for duplication** — The same error toast appears twice; find out why it fires twice (likely the effect/fetch running twice, e.g. React StrictMode double-invoke, or two components both triggering the same failing call).
3. **Audit other tabs for the same pattern** — Given this exists on two tabs already, check every tab that loads data on mount for the same class of bug rather than assuming it's isolated to these two.
4. **Fix and verify** — Confirm both tabs load cleanly with product data (or an appropriate empty state, not an error banner) and no console errors.

## Section G — Inventory Tab: Import Wizard & Export Excel Non-Functional

1. **Reproduce** — Click Import Wizard: does nothing happen, does it silently fail, or throw a console error? Same for Export Excel.
2. **Root-cause** — Check whether these hit the backend endpoints referenced earlier (`/api/v1/excel/export/inventory`, `/api/v1/excel/import/inventory`) and whether those endpoints actually exist/respond correctly in the packaged build.
3. **Fix and verify** — Click both again in the packaged `.exe` and confirm actual file output (a real downloaded `.xlsx`, a wizard that actually opens and steps through).

## Section H — Label Engine: Print & Open Standalone (repeat finding — treat as unresolved, not regressed)

This has been reported multiple times and marked "fixed" at least once without holding. Do not repeat the previous approach of assuming the Tauri IPC registration is correct because it's present in `lib.rs` — evidently something is still wrong at runtime.

1. **Reproduce with actual console output** — Click Print, click Open Standalone, capture the exact error (or lack of any response) from the Tauri devtools console in the packaged app specifically.
2. **Root-cause** — Check whether the IPC command names match exactly between the frontend `invoke()` calls and the Rust `#[tauri::command]` registrations, and whether the commands are correctly listed in the `tauri::generate_handler![]` macro. A mismatch here would explain silent failure with no visible error.
3. **Also re-test the remaining 9 Label Engine buttons** (+Text, +Shape, +Barcode, +QR, Delete, Export PNG, Save/Load Template, Save/Load Product Label) individually — don't assume they're fine because they weren't singled out this time.
4. **Fix and verify** — Click every Label Engine button in the packaged `.exe` and report pass/fail with evidence for each. For Print and Open Standalone specifically, explain what the actual root cause was — not just "fixed," since it's failed silently through prior fix claims already.

## Section I — Users Tab: Black-on-Black Table Text (confirmed recurrence, 3rd location)

This is the same underlying contrast bug reported earlier for Patients and Prescribers, now found in a third place (Users). This strongly suggests the earlier "fix" patched specific components rather than the actual shared cause.

1. **Find the actual shared root cause** — Since this keeps appearing in different tables across different tabs, look for what these tables have in common (a shared table component, a shared CSS class, a theme variable that isn't being applied) rather than patching Users individually as a fourth one-off fix.
2. **Fix at that shared point**, not per-table.
3. **Verify comprehensively** — Check every table in the app (Inventory, Users, Roles, Patients, Prescribers, Vendors, Purchase Orders, Receiving Log, WC Claims, and any others) for the same issue, since a shared root cause means it could be silently present anywhere a table is rendered.

---

## Section J — New Feature: Configurable Barcode Data Pattern

**Goal:** Let the user control how barcode data is generated, instead of only manual entry, with a pattern like: `[optional prefix]` + `[auto-generated number]`.

### Stage J.1 — Requirements clarification (confirm before building)
- Prefix options: user-entered custom text (e.g. pharmacy name), or none.
- Number generation: random or sequential — confirm which the user wants; propose sequential as more useful for tracking unless random is specifically needed for a stated reason.
- Scope of uniqueness: does each individual item get its own unique number, or can a group of items (e.g. a batch) share one code? Support both, controlled by a user choice at generation time.

### Stage J.2 — Data model
- Decide where the pattern setting lives: a per-user or per-pharmacy setting (Settings tab) versus a one-off choice made each time in the Label Engine. Recommend: a default pattern configurable in Settings, with the option to override per label/batch in the Label Engine itself.
- If barcodes need to stay unique and persist across sessions (e.g. tied to a real product), this can't be purely client-side random generation in the Label Engine — it needs to check against existing codes in the database to avoid collisions.

### Stage J.3 — UI
- Add pattern configuration fields near the existing barcode "Data" field in the Properties panel (seen in the current Label Engine): a prefix input, a toggle for "auto-generate" vs manual entry, and (when generating for multiple items) a choice between "unique per item" and "shared per group."
- Show the generated value before it's applied, so the user can confirm/regenerate if they don't like it.

### Stage J.4 — Backend/generation logic
- Implement the generator: prefix + separator + number, with collision checking against existing barcodes if uniqueness is required.
- Support batch generation for multiple selected items at once (ties into the existing Bulk Label Print flow — worth checking whether it makes sense to build this there instead of only in the single-item Label Engine, since bulk printing is the more likely place a pattern would be used across many items).

### Stage J.5 — Verify
- Generate barcodes for a single item and for a group, with and without a prefix, and confirm the resulting data matches the expected pattern and stays unique where required.

---

## Reporting format

For Sections F–I: pass/fail per item, with screenshot or exact error text. For anything previously claimed fixed and found broken again (Print, Open Standalone, contrast), explicitly state the actual root cause found this time — not just that it's "fixed."
For Section J: confirm Stage J.1 answers with the user before building J.2 onward.
