# Round 2 — Remaining Bugs & Roles/Permissions Refinement

**Context:** Sections 1–5 from the original spec were marked complete, but a real installer walkthrough surfaced issues the earlier automated checks missed. This file covers what's still broken and proposes refinements to the Users & Roles feature now that it's visible and working end-to-end.

**Ground rule for the agent:** Fix in the order below. Do not mark anything "done" without a screenshot or explicit confirmation from a running instance — the previous round showed that "build passes" and "tests pass" are not reliable proxies for "the button/text actually works."

---

## Section A — Label Engine: Remaining Broken Buttons

1. **Re-inventory** — The earlier claim that "all 11 toolbar buttons work" did not hold up. Re-test every Label Engine button individually in the actual built `.exe` (not dev server), one at a time, and log pass/fail with the exact behavior observed (nothing happens / wrong action / console error — capture the error text).
2. **Root-cause** — Group failures by cause before fixing. Pay particular attention to whether this is a Tauri IPC issue (handler not registered/wired correctly in the packaged build vs. dev mode) since packaged-app behavior can differ from `npm run dev`.
3. **Fix** — Resolve each, starting with the most common root cause.
4. **Verify** — Re-test every button in the packaged `.exe` and report a pass/fail table. Do not report "verified" without actually clicking each one this time.

## Section B — Inventory Tab: Broken Buttons

1. **Inventory** — List every button on the Inventory tab (including the batch-expire / batch-price-adjust / CSV export actions added earlier).
2. **Reproduce** — Click each one in the running app; log actual behavior and any console/network errors.
3. **Root-cause & fix** — Same pattern as Section A.
4. **Verify** — Re-test every button and report pass/fail.

## Section C — Headline / Tab-Title Text Still Invisible on Some Tabs

1. **Identify which specific tabs still show white/invisible headline text** — the earlier CSS fix (`app/globals.css` lines 93–124) evidently didn't reach every heading element. Go tab by tab and list exactly which headers are still affected.
2. **Root-cause** — Likely a CSS specificity issue: some heading elements may have a more specific selector, inline style, or component-level class that overrides the global contrast rule. Check for these rather than just adding another `!important` on top.
3. **Fix** — Apply a fix that reaches all headline elements consistently — prefer fixing the root cause (why the global rule isn't matching) over patching each tab individually with one-off overrides, since that's how this gap happened the first time.
4. **Verify** — Screenshot every tab's header in light mode (the default) and confirm dark, legible text on all of them.

## Section D — NEW BUG: Untranslated / Raw i18n Keys in Roles UI

**Found via screenshots.** The "Add Permission" modal and the "Set Lock Password" modal are displaying raw translation keys instead of actual text — e.g. `roles.fieldModule`, `roles.selectModule`, `roles.fieldFeatureKey`, `roles.featureKeyHint`, `roles.lockPasswordTitle`, `roles.lockPassNew`, `common.next`. This means the English locale file is missing entries for these specific keys, even though the "New Role" and "New User" modals render correctly.

1. **Locate the locale/translation file(s)** the app uses (likely a JSON/locale resource keyed by strings like `roles.*` and `common.*`).
2. **Diff** — Find every key referenced in the Add Permission and Lock Password components that has no corresponding entry in the locale file.
3. **Add the missing entries** with real text, e.g.:
   - `roles.fieldModule` → "Module"
   - `roles.selectModule` → "Select a module"
   - `roles.fieldFeatureKey` → "Feature Key"
   - `roles.featureKeyHint` → "e.g., reports.view"
   - `roles.lockPasswordTitle` → "Set Lock Password"
   - `roles.lockPassNew` → "New Lock Password"
   - `common.next` → "Next"
   (Use the actual intended copy — the above are best guesses from context; confirm against any design/copy doc if one exists.)
4. **Audit for more of the same** — Since two separate modals had this gap, check whether other newly-built Roles/Permissions components have the same issue rather than assuming it's isolated to these two.
5. **Verify** — Reopen both modals and confirm every label renders as real text, in both English and any other configured language.

---

## Section E — Roles & Permissions: Refinement Notes (review, not urgent bugs)

Based on the screenshots, the core feature works structurally. A few things worth confirming or considering — propose back before implementing any of these, don't just build them:

1. **Confirm (don't assume) that a newly added permission appears in the matrix immediately**, without a manual page refresh.
2. **Confirm feature-key format validation** is actually enforced before submit (the `^[a-z]+\.[a-z]+$` pattern discussed earlier) — the modal doesn't show validation state in the screenshot, so this needs an explicit test with a bad value (e.g. `Reports View` or `reports`).
3. **Duplicate feature-key handling** — if an owner types a feature key that already exists, what happens? Should show a clear error, not a silent failure or a duplicate row.
4. **Minor UX suggestion, optional:** after creating a new role via "New Role," consider taking the owner directly into that role's permission matrix, rather than leaving them to find it in the list afterward. Propose this back rather than just adding it — it's a nice-to-have, not something that was asked for.
5. **Confirm role_id=1 guard still holds** in this build specifically — re-run the Stage 5.6 safety-rail tests against the packaged `.exe`, not just the dev/test environment, since Section A/B showed packaged-build behavior can differ from dev.

---

## Reporting format

For Sections A–D: pass/fail table per item, with a screenshot or exact error text for anything still broken. No item gets marked "done" without one of those two forms of evidence.
For Section E: written answers to items 1–3 and 5, and a simple yes/no + one-line rationale on whether to build item 4.
