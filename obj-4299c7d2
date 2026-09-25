# Round 6 — Users & Roles Refinement + Contact Tab

**Rules:** Same as all previous rounds. Find root causes with evidence before fixing. No build until everything is confirmed. ONE build at the end in `E:\my progam pharmacy`.

---

## Section 1 — Auth: "Not Authenticated" on Permission Change

### What's happening
When entering the current password in "Confirm Permission Change," the backend returns "Not authenticated." This means the password verification endpoint (`POST /api/v1/auth/verify-password`) is rejecting the password entered.

### Stage 1.1 — Diagnose
1. Check what `POST /api/v1/auth/verify-password` actually does: does it verify the password against the currently logged-in user's stored hash, or against a hardcoded/seed value?
2. Check what password hash is stored for the admin user (role_id=1) in the database right now — query `SELECT username, password_hash FROM users WHERE role_id=1`.
3. Check whether the request includes the auth token correctly (the "Not authenticated" error could also mean the token is missing or expired, not that the password is wrong).
4. Confirm: is this a wrong password issue, an expired token issue, or a bug in the verify-password endpoint?

### Stage 1.2 — Fix
- If the token is expired: ensure the app refreshes tokens correctly and the verify-password call includes a valid token.
- If the password hash doesn't match: this may be a seeding issue — the seed created the admin with one password but the user set a different one. Fix the verify-password flow to check against the actual stored hash, not a seed value.
- If the endpoint is buggy: fix it.
- Show curl evidence of the fix working (valid password → success, wrong password → proper rejection).

---

## Section 2 — How Permissions Are Applied to Logged-In Users

### The gap
Currently there is no visible mechanism in the app that enforces role-based permissions at the UI level — tabs and buttons appear for everyone regardless of role. The user/owner needs to know:
1. How does the system know WHO is logged in and WHAT their role is?
2. How does their role actually restrict what they see/can do?

### Stage 2.1 — Audit current enforcement
- Check: when a user logs in, does the JWT/session token include their `role_id`?
- Check: does the frontend read the role from the token and use it to conditionally show/hide tabs or buttons?
- Check: does the backend enforce role-based access on API endpoints, or is it frontend-only?
- Report what's actually in place right now, with file+line references.

### Stage 2.2 — Implement visible role enforcement in the UI
If role enforcement is missing or incomplete at the frontend level:
1. On login, store the user's `role_id` and their granted permissions in app state (from the JWT or a `/api/v1/auth/me` endpoint).
2. In `DashboardLayout.tsx`, hide sidebar tabs the user's role doesn't have `*.view` permission for.
3. On each tab, disable or hide action buttons the user's role doesn't have the corresponding permission for (e.g. hide "New Medicine" if the user lacks `inventory.create`).
4. Show a clear indicator of who is logged in and what role they have — this is already partially visible (bottom-left shows "admin / Administrator") but should be consistent across all views.
5. Role_id=1 (owner/admin) always sees everything — no restrictions applied.

### Stage 2.3 — Verify
- Create a test non-admin user with limited permissions (e.g. only `inventory.read`).
- Confirm that user sees only the permitted tabs and buttons.
- Confirm role_id=1 still sees everything.
- Report findings with file+line for every enforcement point added.

---

## Section 3 — Deactivate Button for Users

### What's needed
In the Users tab, each user row has a "View" action but no way to deactivate/suspend a user without deleting them. Add a **Deactivate / Reactivate** toggle button per user row (except for role_id=1 which can never be deactivated).

### Stage 3.1 — Backend
- Check if the `User` model has an `is_active` field already (likely yes, since the Users table shows "Active" status column).
- Add/verify endpoint: `PATCH /api/v1/users/{user_id}/status` with body `{"is_active": false}` — toggles active state.
- Guard: role_id=1 cannot be deactivated — return 403 if attempted.
- Admin-only: only role_id=1 or users with `users.manage` permission can deactivate others.

### Stage 3.2 — Frontend
- In the Users table, add a **Deactivate** button (shown as "Reactivate" if user is already inactive) in the Actions column, next to "View."
- On click: confirmation dialog ("Deactivate [username]? They will lose access immediately.") → call `PATCH /api/v1/users/{id}/status`.
- Deactivated users: shown with a visual indicator (e.g. greyed out row, "Inactive" badge).
- The deactivate button is hidden for role_id=1.
- Deactivated users cannot log in — enforce this in the login endpoint.

### Stage 3.3 — Verify
- Curl `PATCH /api/v1/users/{id}/status` with `{"is_active": false}` → confirm status changes.
- Curl `POST /api/v1/auth/login` with a deactivated user's credentials → confirm 403/401 returned.
- Confirm role_id=1 cannot be deactivated (curl → expect 403).

---

## Section 4 — Users & Roles Tabs: Relationship and Coherence

The Users tab and Roles tab are currently separate and not visually connected. A user viewing the Users tab can't easily see what permissions that user's role grants, and vice versa.

### Stage 4.1 — Link roles to users visually
- In the Users table, make the "Role ID" column show the role NAME (not just the ID number) — fetch role names from the roles list and display them.
- In the user detail/view modal (when "View" is clicked), add a "Role Permissions" section showing what permissions the user's role grants — a read-only list, not editable here (edit permissions in the Roles tab).

### Stage 4.2 — Link users to roles visually
- In the Roles tab, when a role is selected, show a "Users with this role" count/list alongside the permissions matrix — so the admin knows how many/which users would be affected by changing a role's permissions.

### Stage 4.3 — Role assignment in Users tab
- When creating or editing a user, the Role dropdown should show role NAMES (not IDs) and include a brief description of each role if available.
- After assigning a role, show a preview of what permissions that role grants — so the admin knows what access they're granting before saving.

---

## Section 5 — Contact / Support Tab

### What's needed
A simple tab at the end of the sidebar (under Administration, after Settings, or as a separate bottom section) labeled "Contact" or "Support" — containing the owner's contact information for users who need additional features or support.

### Stage 5.1 — Static content tab
- Add a "Contact Us" or "Support" tab to the sidebar, at the very bottom.
- Content: a simple page with the owner's name/pharmacy name, email address, and optionally a brief description ("For feature requests, support, or questions, contact us at:").
- The email should be configurable — stored in `SystemSetting` (key: `support_email`, `support_name`) so it can be changed from Settings without a code change.
- Display the current values from settings; if not set, show a placeholder prompting the admin to configure it in Settings.

### Stage 5.2 — Settings integration
- In the Settings tab, add a "Support Contact" section where the admin (role_id=1 only) can set: Support Name, Support Email, Support Message (optional custom text).
- These values are stored via `PUT /api/v1/settings/support` and read via `GET /api/v1/settings/support`.

### Stage 5.3 — Verify
- Set a support email via the Settings endpoint, confirm it persists.
- Confirm the Contact tab shows the stored email.
- Confirm the tab appears in the sidebar.

---

## Build

After all 5 sections confirmed with evidence:
```
cd "E:\my progam pharmacy"
npm run tauri build
```
Output: `E:\my progam pharmacy\src-tauri\target\release\bundle\nsis\`

Final manual confirmation list will be provided after the build — things that require clicking through the GUI to verify.
