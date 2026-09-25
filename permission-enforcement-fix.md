# Permission Enforcement Fix — Frontend Role-Based Access Control

**The problem in one sentence:** Roles and permissions are stored and configurable, but never actually enforced — every logged-in user can see and use everything in the UI regardless of their assigned role.

**Ground rules:**
- Find what's actually in place (or missing) with file+line evidence before writing any code.
- Fix at the correct architectural level — not per-tab patches, but a single shared enforcement mechanism.
- Role_id=1 (owner/admin) is always exempt — sees and can do everything, no restrictions ever applied.
- ONE build at the end in `E:\my progam pharmacy`.
- Do not build while anything is pending.

---

## Stage 1 — Audit What Currently Exists

Before writing any code, answer these questions with file+line evidence:

1. When a user logs in, what does the JWT/session token contain? Does it include `role_id` and/or the list of granted permissions? Check the login endpoint response in `backend_fastapi/app/api/routers/auth_route.py` and the token creation logic.

2. On the frontend, after login, where is the user's identity stored? Check `lib/auth.ts` or equivalent — is `role_id` and the permissions list stored in localStorage, a React context, or a Zustand/Redux store?

3. In `DashboardLayout.tsx`, how are sidebar nav items rendered? Is there any existing conditional logic that checks the current user's role or permissions before showing a nav item? If yes, show the lines. If no, state that explicitly.

4. On individual tab pages, is there any existing permission check before rendering action buttons (e.g. "New Medicine", "Delete", "Export")? Search for any `hasPermission`, `canAccess`, or similar guard calls across the codebase. If none exist, state that explicitly.

5. Does the backend enforce role-based access on API endpoints (beyond just requiring a valid token)? Check if any route uses a `require_permission` or similar dependency in FastAPI. Show examples if they exist.

Report all five answers with file+line references before proceeding to Stage 2.

---

## Stage 2 — Backend: Ensure Permissions Are in the Auth Token

The frontend needs to know the current user's permissions without making a separate API call on every render. The cleanest way: include permissions in the login response and/or the JWT.

1. Modify the login response (`POST /api/v1/auth/login`) to include:
   - `user.role_id`
   - `user.role_name`
   - `user.permissions` — array of `feature_key` strings the user's role grants (e.g. `["inventory.read", "inventory.write", "pos.checkout"]`)
   - For role_id=1: set `permissions` to `["*"]` (wildcard meaning full access) — never enumerate all permissions for the owner.

2. Add a `GET /api/v1/auth/me` endpoint that returns the same structure — used to refresh the current user's state after a role change without requiring re-login.

3. Verify with curl:
   - Login as a non-admin user → confirm `permissions` array is in the response and matches what's configured in the Roles tab for that user's role.
   - Login as role_id=1 → confirm `permissions` is `["*"]`.

---

## Stage 3 — Frontend: Store Permissions in Global State

1. After a successful login, store the following in a persistent auth store (localStorage + React context or Zustand, whichever the app already uses):
   - `userId`, `username`, `roleId`, `roleName`, `permissions` (array of feature_key strings, or `["*"]` for owner)

2. Create a single shared utility function:
   ```typescript
   function hasPermission(permission: string): boolean
   ```
   - If `permissions` contains `"*"` → always returns `true` (owner).
   - If `permissions` contains the exact `permission` string → returns `true`.
   - Otherwise → returns `false`.
   - This function is the ONLY place permission checking happens — import it everywhere, don't duplicate the logic.

3. Create a React context/hook `usePermissions()` that exposes `hasPermission` and the current user's `roleId`, `roleName` — components use this hook, never read localStorage directly.

4. When `GET /api/v1/auth/me` is called (on app startup to restore session), update the store with fresh permissions in case the role was changed since last login.

---

## Stage 4 — Frontend: Enforce Permissions on Sidebar Navigation

In `DashboardLayout.tsx`, map each nav item to the permission it requires. Use this mapping (extend as needed for all tabs):

| Nav item | Required permission |
|----------|-------------------|
| Point of Sale | `pos.checkout` |
| Inventory | `inventory.read` |
| Expiry Alerts | `inventory.read` |
| Patients | `patients.read` |
| Prescribers | `patients.read` |
| WC Claims | `insurance.read` |
| Vendors | `inventory.manage` |
| Receiving Log | `inventory.write` |
| Purchase Orders | `inventory.manage` |
| Drug Interactions | `patients.read` |
| Drugs | `dictionaries.write` |
| Quick SIG | `dictionaries.write` |
| SIG Codes | `dictionaries.write` |
| Sales Analytics | `analytics.view` |
| Analytics | `analytics.view` |
| Audit Log | `settings.manage` |
| Email | `settings.manage` |
| Templates | `inventory.write` |
| Bulk Import | `inventory.write` |
| Bulk Label Print | `inventory.write` |
| Label Engine | `inventory.write` |
| Invoice Parse | `inventory.write` |
| Gift Cards | `pos.checkout` |
| Users | `users.read` |
| Roles | `users.manage` |
| Backup | `settings.manage` |
| Settings | `settings.read` |
| Receipt History | `pos.checkout` |

For each nav item: if `hasPermission(requiredPermission)` is false AND `roleId !== 1`, hide the item entirely from the sidebar. Do not show it greyed out — hide it, so users only see what they can access.

Role_id=1 always sees all nav items regardless of this mapping.

---

## Stage 5 — Frontend: Enforce Permissions on Action Buttons

For the most critical action buttons across tabs, add `hasPermission` checks that hide or disable the button if the user lacks the permission. Priority targets:

| Tab | Button | Required permission |
|-----|--------|-------------------|
| Inventory | New Medicine | `inventory.write` |
| Inventory | Add/Adjust Stock | `inventory.write` |
| Inventory | Export Excel | `inventory.reports` |
| Inventory | Import Wizard | `inventory.write` |
| Inventory | Delete (row) | `inventory.write` |
| Inventory | Batch: Mark Expired | `inventory.write` |
| Inventory | Batch: Adjust Price | `inventory.write` |
| Users | New User | `users.write` |
| Users | Edit/Delete (row) | `users.write` |
| Users | Deactivate | `users.write` |
| Roles | Add Permission | `users.manage` |
| Roles | New Role | `users.manage` |
| Roles | Set Lock Password | role_id=1 only |
| Roles | Edit/Delete role | `users.manage` |
| POS | All actions | `pos.checkout` |
| Settings | All write actions | `settings.manage` |

For each: if `hasPermission(required)` is false AND `roleId !== 1`, hide the button (don't render it, don't just disable it — a disabled button still reveals that the feature exists).

---

## Stage 6 — Backend: API-Level Enforcement

Frontend enforcement alone is not enough — a user could call the API directly. Add backend enforcement:

1. Create a FastAPI dependency `require_permission(feature_key: str)` that:
   - Reads the current user's role_id from the JWT.
   - Checks whether that role has the given permission in the database.
   - Returns 403 if not (with message "Insufficient permissions").
   - Skips the check entirely for role_id=1.

2. Apply this dependency to the most sensitive endpoints:
   - `POST /api/v1/inventory/medicines` → `require_permission("inventory.write")`
   - `DELETE /api/v1/inventory/medicines/{id}` → `require_permission("inventory.write")`
   - `POST /api/v1/users` → `require_permission("users.write")`
   - `DELETE /api/v1/users/{id}` → `require_permission("users.write")`
   - `POST /api/v1/roles/permissions` → `require_permission("users.manage")`
   - `PUT /api/v1/roles/{id}/permissions` → `require_permission("users.manage")`
   - `POST /api/v1/roles/lock-password` → role_id=1 only (already guarded — verify)

3. Verify with curl:
   - Call a protected endpoint with a token from a user who lacks the permission → confirm 403 response.
   - Call the same endpoint with role_id=1's token → confirm it succeeds.

---

## Stage 7 — Session Handling: Role Changes Take Effect

If an admin changes a non-admin user's role while they're logged in, their current session still has the old permissions. Handle this:

1. On every app navigation (tab change), call `GET /api/v1/auth/me` in the background and refresh the stored permissions silently.
2. If the returned permissions differ from what's stored, update the store — this causes sidebar items and buttons to re-render with the new permissions.
3. If the user's account has been deactivated, `GET /api/v1/auth/me` should return 403 — handle this by logging the user out immediately and showing "Your account has been deactivated. Contact your administrator."

---

## Stage 8 — Verify End-to-End

1. Create a test user with a role that only has `inventory.read` and `pos.checkout`.
2. Log in as that user.
3. Confirm: only the permitted sidebar tabs are visible.
4. Confirm: in Inventory, only read actions are available (no New Medicine, no Delete, no Import).
5. Confirm: Roles, Users, Settings, Backup tabs are not visible at all.
6. Confirm: direct API calls to protected endpoints return 403.
7. Log in as role_id=1 — confirm everything is visible and accessible.
8. Report findings per step with evidence.

---

## Build

After all stages confirmed:
```
cd "E:\my progam pharmacy"
npm run tauri build
```
Output: `E:\my progam pharmacy\src-tauri\target\release\bundle\nsis\`

List all items requiring manual visual confirmation after the build.
