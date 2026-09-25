# SPEC 05 — App-Wide Refinement & Polish

**Apply after Specs 01–03.** This spec covers every area of the app that needs refinement to be market-ready: UX consistency, remaining i18n gaps, session timeout UI, error handling polish, and per-tab improvements.

**Architecture reference:** All files in APP_BLUEPRINT.md Section 2.

---

## Part 1 — Session Timeout Settings UI

**Files:** `app/dashboard/settings/page.tsx`, `stores/sessionStore.ts`, `hooks/useSessionTimer.tsx`

### 1.1 — Add Session & Security section to Settings tab

In `app/dashboard/settings/page.tsx`, add a new collapsible section visible only to role_id=1:

**Section heading:** "Session & Security"

**Fields:**
- **Session Timeout** — dropdown:
  - 15 minutes (default)
  - 30 minutes
  - 1 hour
  - 4 hours
  - 8 hours
  - Never ⚠️
  
  When "Never" is selected, show inline warning: "Sessions that never expire are less secure. Only use this on private, single-user devices."

- **Absolute Session Limit** — separate dropdown (max time regardless of activity):
  - 4 hours
  - 8 hours (default)
  - 24 hours
  - Never

On change: call `PUT /api/v1/settings/session_idle_minutes` and `PUT /api/v1/settings/session_absolute_minutes` respectively. Show success toast on save.

### 1.2 — Fix SessionStore type safety (from Bug 5 in Spec 01)

After the Spec 01 fix, the sessionStore uses `null` for "never". Update the Settings UI to convert:
- "Never" dropdown selection → send `"never"` string to backend → backend stores as string
- On load: if stored value is `"never"` → show "Never" in dropdown and set `null` in store

### 1.3 — Session timeout warning modal

30 seconds before auto-logout, show `components/SessionTimeoutModal.tsx`:
- "Your session will expire in 30 seconds due to inactivity."
- "Stay logged in" button — resets the idle timer
- "Log out now" button — triggers immediate logout

This component likely exists already per blueprint — verify it's wired to `useSessionTimer`.

---

## Part 2 — Patients Tab: Three Remaining Gaps

**Files:** `app/patients/page.tsx`

### 2.1 — Insurance field in New Patient modal
The Patients table has an "Insurance" column but the New Patient creation form doesn't have an insurance field. Add `insurance_provider` text input to the create form, matching the field name in `PatientRead` schema in `backend_fastapi/app/shared/schemas.py`.

### 2.2 — Back button on Patient detail view
When a patient record is open (detail view), there is no visible way to return to the patient list. Add a "← Back to Patients" button at the top-left of the detail view. This is a simple `router.back()` or state reset, not a navigation change.

### 2.3 — Custom fields on patient records
Add an "Add Custom Field" button in the patient detail view:
- Click reveals a key/value input pair: [Field Name] [Value]
- "Add Another Field" button adds more pairs
- Saved to a `custom_fields` JSON column on the `Patient` model
- Displayed as a read-only list in the detail view with edit/delete per field

Backend: Confirm `Patient` model has `custom_fields: JSON` column. If not, add it and create a simple migration.

---

## Part 3 — Users & Roles Tab Polish

**Files:** `app/dashboard/users/page.tsx`, `app/dashboard/roles/page.tsx`

### 3.1 — Role name instead of Role ID in Users table
The Users table shows "Role 1" in the Role column. It should show the role name (e.g. "Administrator"). Fetch the roles list on page load and join role name by role_id when rendering the table.

### 3.2 — Deactivate button in Users table
Add a Deactivate / Reactivate action per user row (hidden for role_id=1). On click: confirmation dialog → `PATCH /api/v1/users/{id}/status` → row updates to show "Inactive" badge. Deactivated users see a "Your account has been deactivated" message on login attempt.

### 3.3 — Roles tab loading fix (covered in Spec 01 Bug 2)
Confirm Roles tab loads after the wildcard permission fix.

### 3.4 — Roles tab: show user count per role
In the Roles tab, beside each role name, show how many users have that role: "Administrator (1 user)", "Staff (3 users)". This is a simple count query.

### 3.5 — Add Permission: Action dropdown (not free text)
The Add Permission modal currently has a free-text Feature Key field. Replace with:
- Module dropdown (existing)
- Action dropdown: view / create / edit / delete / export / print / manage / other
- Feature Key auto-populates as `{module}.{action}` and is read-only (unless "other" selected)

---

## Part 4 — i18n Audit (Remove All Raw Key Leakage)

**Files:** All `.tsx` files, all locale files in `lib/i18n/locales/`

Run this search across the entire frontend codebase:
```bash
grep -rn "t(\"[a-z].*\.[a-z]" app/ components/ --include="*.tsx" | head -100
```

For every `t("some.key")` call found, verify the key exists in `lib/i18n/locales/en.json`. Any missing key should be added with appropriate English text.

Known gaps from testing (add all of these if not already present):
- `rx.queue.*` — Rx Queue table columns and tabs (21 keys)
- `nav.receiptHistory` — Receipt History sidebar label
- Any remaining `roles.*` keys
- Any remaining `common.*` keys used in modals

Also audit Arabic (`ar.json`) and other locales — add English text as fallback for any missing keys in non-English locales.

---

## Part 5 — Receipt History Tab

**Files:** `app/dashboard/receipt-history/page.tsx` (new), `backend_fastapi/app/api/routers/receipt_route.py`

### 5.1 — Verify backend receipt endpoints exist and work
```bash
curl http://127.0.0.1:8000/api/v1/receipts -H "Authorization: Bearer ADMIN_TOKEN"
curl http://127.0.0.1:8000/api/v1/receipts/settings -H "Authorization: Bearer ADMIN_TOKEN"
```

If they return errors or 404, implement them per the earlier spec.

### 5.2 — Verify POS checkout creates receipts
After a POS sale completes, a `Receipt` row must be created. Confirm in `backend_fastapi/app/services/pos_service.py` `process_checkout` that it writes to the `Receipt` table.

### 5.3 — Receipt History tab UI
The tab should show:
- Filterable table: Receipt #, Date/Time, Type, Total, Processed By, Actions
- Date range picker at the top
- Type filter: All / POS Sale / Prescription / Adjustment
- Search by receipt number
- Row click → detail modal with line items and "Reprint" button
- Retention period setting (admin only) — visible at top of tab

---

## Part 6 — Dashboard Homepage Improvements

**Files:** `app/dashboard/page.tsx`, `components/rx/RxQueueDashboard.tsx`

### 6.1 — KPI cards: show real data
The dashboard KPI cards (Total Inventory Value, Today's Sales, Total Products, Low Stock Items, Active Patients, Pending RX) all show "—". These should fetch from the backend dashboard endpoint.

Confirm `GET /api/v1/dashboard/summary` exists and returns these values. If it does but the frontend isn't wired to it, wire it. If it doesn't exist, add the endpoint.

### 6.2 — Quick Access cards: verify navigation
All Quick Access cards (Point of Sale, Inventory, Patients, etc.) should navigate to their respective tabs on click. Verify each one's `href` is correct.

### 6.3 — Recent Activity section
Currently shows "No recent activity." This should fetch recent events: last 5 sales, last 5 inventory changes, last 5 prescription actions. Connect to `GET /api/v1/dashboard/activity` or the audit log.

---

## Part 7 — POS Tab Refinements (from screenshot)

**Files:** `app/pos/page.tsx`, `stores/posStore.ts`

The POS tab (Image 3 in screenshots) looks clean and functional. Verify these work:
1. Barcode scan / medicine search → product appears in cart
2. Quantity adjustment in cart (+ / -)
3. Cash / Card / Transfer / Split payment methods all trigger correct flows
4. Amount Tendered field calculates change correctly
5. Checkout button processes the sale and creates a receipt
6. "Add items to checkout (F12)" keyboard shortcut works

---

## Part 8 — Contact/Support Tab

**Files:** `components/DashboardLayout.tsx` (sidebar), new `app/dashboard/support/page.tsx`

Add a "Support" tab at the bottom of the sidebar (after Settings):

**Page content:**
- Pharmacy Suite logo
- "Need help or want to request a feature?"
- Admin's configured support email (from `SystemSetting` key `support_email`)
- Admin's configured support name (from `SystemSetting` key `support_name`)
- Optional: custom support message from `SystemSetting` key `support_message`
- If support settings not configured: show "Contact your system administrator"

**Settings integration:**
In Settings tab (admin only), add "Support Contact" section:
- Support Name field
- Support Email field
- Custom Message field (optional)
- Save button → `PUT /api/v1/settings` for each key

---

## Part 9 — Error Boundaries on Every Route

**Files:** `app/layout.tsx`, `components/ErrorBoundary.tsx`

Confirm `ErrorBoundary` wraps every route in `app/layout.tsx`. The current error card (the "Something went wrong / Try Again" card seen in screenshots) should:
1. Show a more helpful message: not just "Cannot read properties of undefined" (raw JS error) but a friendly "Something went wrong. Try refreshing or contact support."
2. Log the raw error to `POST /api/v1/crash-report` (already exists per blueprint)
3. Show a "Copy error details" button that copies the stack trace to clipboard for bug reporting
4. Show a "Return to Dashboard" button, not just "Try Again"

---

## Part 10 — Performance Cleanup

**Files:** All `.tsx` and `.ts` files

Search and remove:
```bash
grep -rn "console.log\|console.debug\|console.warn" app/ components/ stores/ lib/ --include="*.ts" --include="*.tsx"
```
Remove any `console.log` that prints tokens, passwords, user data, or API responses. Keep `console.error` in error handlers — those are useful.

Remove unused imports:
```bash
npx ts-prune # finds unused exports
```

After cleanup: `npm run build` should show fewer warnings.

---

## Final Build Checklist Before Submission

- [ ] All tabs load data correctly
- [ ] All buttons produce expected results
- [ ] No raw i18n keys visible anywhere in the UI
- [ ] Admin sees all tabs; non-admin sees only permitted tabs
- [ ] Fresh install wizard works (Spec 02)
- [ ] Logout returns to login screen (not blank white)
- [ ] Session timeout warning modal appears before auto-logout
- [ ] Receipt History tab shows (empty state if no sales yet)
- [ ] Support tab shows
- [ ] No console.log with sensitive data
- [ ] `npm run build` passes with zero TypeScript errors

```
cd "E:\my progam pharmacy"
npm run tauri build
```
