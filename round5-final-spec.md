# Round 5 — Final Pre-Launch Fix Spec

**Purpose:** This is the final round before the app goes to market. Every item here must be resolved completely. The agent must examine actual running behavior, not just code, before claiming anything is fixed.

**Non-negotiable rules for this round:**
- Find actual root causes with file + line evidence before writing any fix.
- Nothing is "done" without curl output or a screenshot confirming real behavior.
- Do NOT build until every section in this file is confirmed fixed with evidence.
- ONE build at the end, in `E:\my progam pharmacy`, using `npm run tauri build`.
- Do not announce a build as complete while any item still shows "pending" or "in progress."

---

## Section 1 — CRITICAL: Systemic "Method Not Allowed" (405) Error

This is the highest priority item. Two separate actions throw 405:
- Roles → Set Lock Password
- Roles → Add Permission

Both were previously claimed fixed. Both still fail. This is now clearly a systemic routing problem, not a per-component issue.

### Stage 1.1 — Find the actual cause (do this before touching any code)
1. Add temporary `console.debug` logging to `lib/api.ts` that logs the FULL request URL (baseURL + path + method) immediately before every request fires. This must be in the build — not just read from code — so the log actually appears.
2. Since devtools can't be opened in the packaged app, find another way to capture this: either run the dev server (`npm run dev`) with both backends running and use a browser at `http://localhost:3000` to open DevTools and see the actual network requests, OR add the debug logging and rebuild so it appears in the Tauri app's stdout/stderr.
3. Report the EXACT URL and method being used when "Set Lock Password" and "Add Permission" are clicked. Do not guess — show the actual logged output.

### Stage 1.2 — Fix
Once the actual URL is confirmed, fix whatever is wrong:
- If the URL is wrong (hitting port 3000 instead of 8000): fix the interceptor so ALL requests go to `http://127.0.0.1:8000` by default, regardless of localStorage state. The app is a packaged desktop app — the backend always runs on 127.0.0.1:8000. Remove any conditional logic that could route to the wrong host.
- If the method is wrong (GET instead of POST): fix the frontend call.
- If the endpoint is registered wrong in FastAPI: fix the router.
- Whatever the actual cause is, fix that specific thing — not a guess at what might be wrong.

### Stage 1.3 — Verify
Curl the two endpoints directly on port 8000 with valid auth tokens and confirm they return JSON responses, not 405 errors. Show both curl results.

---

## Section 2 — Roles Tab: Add Permission UX (dropdown-only, no typing)

**Current state:** Add Permission modal has a free-text "Feature Key" field that users must type in `module.action` format manually. This is error-prone.

**Required change:** Replace the Feature Key text input with two dropdowns:
1. **Module** dropdown (already exists — keep as-is)
2. **Action** dropdown: populated based on the selected module, with predefined common actions: `view`, `create`, `edit`, `delete`, `export`, `print`, `manage` — plus an "Other (type manually)" option at the bottom that reveals a text input only when selected.
3. The Feature Key field becomes read-only, auto-populated as `{module}.{action}` from the two dropdowns — users never type it manually unless they chose "Other."
4. Description field remains as free text.

No backend changes needed — the feature_key format stays the same, just the UI input method changes.

---

## Section 3 — Patients Tab: Three Gaps

### Gap 3A — Insurance field missing from "New Patient" modal
The Patients table shows an "Insurance" column but the New Patient modal has no insurance field (only Full Name, Date of Birth, Phone, Email). Add an Insurance field to the modal — a text input for insurance provider name, matching whatever field the backend already stores for this.

### Gap 3B — No "Back" / navigation button on Patient detail view
When a patient is selected/opened, there is no way to navigate back to the patient list without using browser history or a workaround. Add a clear "← Back to Patients" button at the top of the patient detail view.

### Gap 3C — No way to add custom fields to a patient record
Add an "Add Field" button in the patient detail view that allows the user to add custom key-value fields to a patient record (e.g. "Emergency Contact: Jane Doe", "Notes: Allergic to penicillin"). These should be stored in a `custom_fields` JSON column on the patient record (add if not already present). The fields should appear in the patient detail view and be editable/deletable. No special backend model needed beyond the JSON column.

---

## Section 4 — Label Engine: Remaining Non-Working Buttons

The following buttons have been reported broken multiple times and not yet confirmed working in the actual packaged app. This time, trace each one in code from click → handler → output, state what the code does, and confirm or find the actual failure point.

### Button 4A — Print
- Confirmed fix in code: `ShellExecuteW` with `print` verb replacing deprecated `rundll32`.
- What's still needed: actual confirmation this fires in the packaged app. If it still silently fails, capture why — check if the temp image file is being written correctly before `ShellExecuteW` is called, and whether `ShellExecuteW` returns an error code that's being silently swallowed.
- Add error logging to the Rust `print_label` handler that captures and returns the `ShellExecuteW` return value so failures are visible rather than silent.

### Button 4B — Open Standalone
- The URL fix (`WebviewUrl::External`) was applied. Still reported not working.
- Check: does the Tauri window creation succeed? Does the `label-engine-preview` page exist at the correct route? Is the Tauri event (`label-preview-state`) being emitted before or after the window is ready to receive it (timing issue)?
- Add error handling that surfaces window-creation failures rather than silently doing nothing.

### Button 4C — Export PNG
- Trace the `handleExportPNG` function: does it call `canvas.toDataURL()`? Does the download trigger? Is there a missing canvas ref or a timing issue where the canvas isn't ready?
- Confirm or find the failure point.

### Button 4D — Save Template (Save Tpl)
- Trace: does clicking Save Tpl call the backend `POST /api/v1/label-templates`? Is there a 405/404/auth error? Is the template name field required but empty by default?
- Confirm or find the failure point. Curl the endpoint directly to confirm it exists and accepts the expected payload.

For each of 4A–4D: state the actual finding (works / specific error found) with evidence before fixing.

---

## Section 5 — Comprehensive App Audit Before Launch

Before the final build, the agent must do a thorough pass of the entire app to catch anything remaining. This is not optional — the app is going to market after this round.

### Stage 5.1 — Button/action audit
Go through every tab in the sidebar and for each one:
- List every button/action on that tab
- For any that calls a backend endpoint, curl that endpoint and confirm it returns a valid response (not 404/405/500)
- Flag anything that can't be verified by curl (UI-only interactions) and note it for manual confirmation

### Stage 5.2 — i18n audit
Search the entire codebase for any remaining raw translation key usage patterns (strings matching `[a-z]+\.[a-zA-Z]+` used as display text in components). List every missing key found and add them all to the locale files in one pass.

### Stage 5.3 — Console error audit
Run the dev server (`npm run dev`) with both backends running and open the browser at `http://localhost:3000`. Navigate to every tab and capture any console errors or failed network requests. Fix any that are found.

### Stage 5.4 — DataTable contrast final check
Confirm all 10 migrated tables use CSS variables for text and background colors. List each one with the specific CSS variable used for text color — not just "uses DataTable" but specifically what color the text renders as in light mode.

---

## Final Build

After ALL sections above are confirmed with evidence:

```
cd "E:\my progam pharmacy"
npm run tauri build
```

Output must be at: `E:\my progam pharmacy\src-tauri\target\release\bundle\nsis\`

After the build, provide a list of everything that still requires manual visual confirmation (things the agent cannot verify without clicking through the GUI) so the final manual pass is focused and complete.
