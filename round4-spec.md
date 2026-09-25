# Round 4 — Bug Fixes & New Features Spec

**Ground rules for the agent:**
- Read this file fully before writing any code.
- Work through Parts 1–4 in order. Do not start a part until the previous one is verified.
- For every bug fix: find the actual root cause in code (file + line), state it explicitly, then fix it. Do not guess.
- For every new feature: complete each numbered stage before moving to the next stage within that part.
- Nothing is marked "done" without real evidence — either a curl result, a code reference with file+line, or a screenshot from the running app.
- Rebuild the .exe only once, after ALL four parts are complete.

---

## Part 1 — Fix: Roles Tab "Confirm Permission Change" Error

### What was observed
When trying to update a permission (e.g. "inventory.read") for a role, the Confirm Update Permission modal shows:
`Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

This means the API call returned an HTML page (likely a 404 or 500 error page) instead of JSON — the response body starts with `<!DOCTYPE` which is HTML, not a valid JSON response.

### Stage 1.1 — Root cause
1. Find the frontend code that fires when "Confirm Update Permission" is clicked — locate the exact API call being made (URL, method, body).
2. Check whether that endpoint exists in the FastAPI router and is correctly registered in `main.py`.
3. Check whether the endpoint requires auth and whether the request includes the correct auth token/header.
4. Check whether the endpoint expects the current password in the request body and whether it's being sent correctly.
5. Check whether there is a mismatch between what the frontend sends and what the backend expects (field names, types, structure).
6. State the exact root cause with file and line number before writing any fix.

### Stage 1.2 — Fix
- Fix the mismatch found in Stage 1.1.
- If the endpoint is missing, create it.
- If it's a routing/registration issue, fix the registration.
- Do not change the UI behavior or modal design — only fix the underlying API call.

### Stage 1.3 — Verify
- Curl the endpoint directly with a valid auth token and a test payload to confirm it returns JSON, not HTML.
- Confirm the exact same curl with a wrong password returns a proper JSON error (e.g. 401/403 with `{"detail": "..."}`) rather than HTML.
- Report both curl results with file+line of the fix.

---

## Part 2 — Fix + Enhancement: Label Engine Buttons (Print, Open Standalone, Barcode)

### Part 2A — Print button

### Stage 2A.1 — Root cause
- Check the Tauri IPC handler for `print_label` in `src-tauri/src/lib.rs` — confirm the command is registered in `tauri::generate_handler![]`.
- Check the frontend `invoke("print_label", ...)` call — confirm the argument names exactly match the Rust function parameter names (snake_case on both sides — Tauri v2 does NOT auto-convert camelCase).
- Check the Windows print command used in the Rust handler — `rundll32.exe shimgvw.dll,ImageView_PrintTo` is deprecated/removed in newer Windows versions. Confirm what Windows version this app targets and whether this command actually works there.
- State the exact root cause with file and line before fixing.

### Stage 2A.2 — Fix
- Fix the argument name mismatch if present.
- If the Windows print command is broken, replace it with a working alternative (e.g. `ShellExecuteW` with the `print` verb, or write the image to a temp file and open it with the default print handler). Do not just wrap the same broken command in error handling.
- Confirm the fix compiles (Rust) without errors.

### Stage 2A.3 — Verify
- Trace the full call path in code from button click → `invoke()` → Rust handler → OS print command and confirm each step is wired correctly.
- Report file + line for every step in the chain.

---

### Part 2B — Open Standalone button + Preview window

### Stage 2B.1 — Root cause (existing bug)
- Check `WebviewUrl` in `src-tauri/src/lib.rs` for the `open_label_window` command — confirm it uses `WebviewUrl::External("http://127.0.0.1:3000/dashboard/label-engine")` and NOT `WebviewUrl::App(...)` which loads from bundled assets (wrong when the app runs against a live Next.js server).
- Confirm the window config in `tauri.conf.json` allows creating additional windows.
- State the exact root cause if it differs from the above.

### Stage 2B.2 — Redesign: standalone window as print-preview
The standalone window should NOT just duplicate the Label Engine page. It should open as a **print preview window** with the following behavior:

1. Receives the current canvas state (all elements, positions, sizes) from the main Label Engine window — either via Tauri event passing or via a shared state URL param.
2. Shows a rendered preview of the label exactly as it will print.
3. Allows the user to specify: **single item** (print once) OR **apply to inventory items** (select from a list of items in the database to assign this label to, with quantity — e.g. "apply to 50 units of Medicine X").
4. When "Apply to inventory" is chosen: saves the label assignment to the database (which item, how many, the label template used) before printing — this becomes the stored record used by Bulk Label Print later.
5. Has a Print button that triggers the actual OS print dialog for the previewed label.
6. Has a Cancel button that closes the preview window without printing or saving.

### Stage 2B.3 — Backend for preview/save
- Add/verify a backend endpoint to save a label assignment: `POST /api/v1/label-assignments` with fields: `medicine_id`, `quantity`, `label_template_id` (or the raw canvas JSON if no template was saved yet), `created_at`.
- Add a `GET /api/v1/label-assignments` endpoint to retrieve stored assignments (used by Bulk Label Print to know what to print for which items).
- Verify these endpoints are registered in `main.py`.

### Stage 2B.4 — Verify (code-level)
- Confirm the window opens at the correct URL.
- Confirm canvas state is passed to the preview window correctly.
- Confirm the save-to-database flow wires to the backend endpoint.
- Curl the `POST /api/v1/label-assignments` endpoint with a test payload to confirm it stores and returns the record.

---

### Part 2C — Barcode: Pattern Generation Feature

**Goal:** Replace manual barcode data entry with a configurable pattern generator, while keeping manual entry as an option.

### Stage 2C.1 — UI changes (Properties panel in Label Engine)
When a barcode element is selected, the Properties panel currently shows a "Data" text field. Change this to:
1. A toggle: **Manual** | **Auto-generate**
2. When **Auto-generate** is selected, show:
   - **Prefix** field: free text the user types (e.g. pharmacy name, department code) — or leave blank for no prefix.
   - **Separator** field: character between prefix and number (default: `-`) — or leave blank.
   - **Number type**: dropdown with options: **Sequential** (default) | **Random**
   - **Scope**: dropdown: **Unique per item** (default) | **Shared per batch/group**
   - **Preview**: a read-only field showing what the generated barcode data will look like (e.g. `PHARMA-000042`) — updates live as the user types the prefix/separator.
   - **Generate** button: applies the pattern and generates the barcode data value(s).
3. When **Batch generate** is needed (multiple items): a **Quantity** field appears, and clicking Generate produces that many unique barcodes in sequence, not just one.
4. Generated values must be checked against existing barcodes in the database to avoid collision before being applied.

### Stage 2C.2 — Sequential number backend
- Add/verify a backend endpoint `GET /api/v1/barcodes/next-sequence?prefix=PHARMA-` that returns the next sequential number for a given prefix, based on existing barcodes in the database with that prefix. This ensures sequence continuity across sessions.
- Sequence counting: global per prefix (not restarting per item group).
- Add `POST /api/v1/barcodes/validate` to check whether a given barcode value already exists in the database.

### Stage 2C.3 — Verify (code-level)
- Curl `GET /api/v1/barcodes/next-sequence?prefix=TEST-` and confirm it returns a number (e.g. `{"next": 1}` on first call, `{"next": 2}` after one is stored).
- Curl `POST /api/v1/barcodes/validate` with a value that exists and one that doesn't — confirm correct responses.
- Confirm the Properties panel toggle/fields exist in the frontend code and wire to these endpoints.

---

## Part 3 — New Feature: Receipt History Tab

**Goal:** A dedicated tab where all receipts (POS transactions, prescription sales, etc.) are stored in the database and displayed in the UI, with configurable retention and manual deletion.

### Stage 3.1 — Data model
- Define a `Receipt` model with fields: `id`, `receipt_number` (auto-generated, human-readable), `type` (pos_sale | prescription | adjustment), `total_amount`, `items` (JSON array of line items), `user_id` (who processed it), `created_at`, `expires_at` (null = keep forever).
- `expires_at` is computed from `created_at` + the configured retention period (see Stage 3.3).
- Write this model before any code, and confirm it against Stage 3.2 requirements.

### Stage 3.2 — Backend endpoints
- `GET /api/v1/receipts` — paginated list, filterable by date range, type, user. Returns summary fields (not full item JSON) for the list view.
- `GET /api/v1/receipts/{id}` — full receipt detail including line items.
- `DELETE /api/v1/receipts/{id}` — manual deletion by admin.
- `DELETE /api/v1/receipts/expired` — bulk delete all receipts past their `expires_at` (called by a background job or manually by admin).
- `GET /api/v1/receipts/settings` — returns current retention period setting.
- `PUT /api/v1/receipts/settings` — sets retention period (admin only). Accepts: `{"retention_days": 90}` or `{"retention_days": null}` for keep-forever.
- Register all endpoints in `main.py`.
- Ensure every POS sale and prescription dispensing event that already exists in the codebase ALSO writes a receipt record — find those existing write points and add the receipt creation call there.

### Stage 3.3 — Frontend: Receipt History tab
- Add a new tab "Receipt History" (or "Receipts") in the sidebar under the appropriate section (Operations or Insights — propose which fits better and confirm before building).
- Tab shows a table: Receipt #, Date/Time, Type, Total, Processed By, Actions (View, Delete).
- Clicking View opens a detail modal showing full line items, amounts, and a Print button for reprinting.
- Above the table: date-range filter, type filter, search by receipt number.
- In Settings (or within the tab, if that makes more sense): a **Retention Period** control — dropdown or number input (e.g. 30 days / 60 days / 90 days / 1 year / Keep forever). Admin only. Changing this updates the setting via `PUT /api/v1/receipts/settings` and recalculates `expires_at` for all existing receipts going forward (does NOT retroactively delete already-stored records immediately — just stops new ones from being kept longer than the new setting).
- A **Clear Expired** button (admin only) that manually triggers `DELETE /api/v1/receipts/expired` to purge records past their retention date. Does NOT auto-delete without explicit action.

### Stage 3.4 — Verify (code-level)
- Curl `POST` to whatever endpoint creates a receipt (show the exact curl) and confirm it stores the record.
- Curl `GET /api/v1/receipts` and confirm the stored record appears.
- Curl `PUT /api/v1/receipts/settings` with `{"retention_days": 30}` and confirm it persists.
- Curl `DELETE /api/v1/receipts/expired` after manually setting `expires_at` on a test record to the past — confirm it's removed.
- Confirm the frontend tab exists in the sidebar and the route is registered.

---

## Part 4 — Fix: Section I (Table Text Contrast — Recurring Bug)

This bug has appeared in Users, Patients, Prescribers, and is suspected in other tables. The previous narrow, per-component patches did not hold. This time, fix at the shared root cause.

### Stage 4.1 — Find the actual shared root cause
- Identify what all affected tables have in common — is it a shared table component? A shared CSS class? A theme variable that isn't being inherited correctly in certain wrapper contexts?
- Specifically find: what is setting the text color to black/dark in affected tables when the table background is ALSO dark (or vice versa), making text invisible?
- State the exact root cause with file + line references. Do not proceed to Stage 4.2 until this is stated clearly.

### Stage 4.2 — Fix at the shared level
- Create a shared `DataTable` component if one doesn't exist, OR fix the existing shared component/CSS variable that all tables should use.
- The fix must use CSS variables (`var(--text-main)`, `var(--bg-secondary)`) tied to the active theme, NOT hardcoded color values — hardcoded colors are what caused the repeated failures.
- Migrate every affected table to use this fix: Inventory, Users, Roles, Patients, Prescribers, Vendors, Purchase Orders, Receiving Log, WC Claims, Analytics tables.

### Stage 4.3 — Verify (code-level)
- For each migrated table, confirm in code that text color and background color come from the same theme variable source and will always contrast correctly regardless of light/dark mode.
- List every table checked and its file reference.

---

## Rebuild & Final Test

Once all four parts are complete and code-level verified:

1. Rebuild the backend sidecar: `pyinstaller build_backend.spec` → copy to `src-tauri/binaries/`
2. Rebuild the Tauri app: `npm run tauri build`
3. Confirm installer output path.
4. List explicitly what still requires manual visual confirmation (the agent cannot click through the GUI) so the user knows exactly what to look at in one final pass.
