# Fix: Admin Sidebar Missing Tabs — role_id=1 Bypass Failure

## Problem Statement
After the permission enforcement work (Stages 1–8 of the permission spec), the admin user (role_id=1) only sees Operations tabs in the sidebar. All other sections (Clinical, Insights, Tools, Administration) are hidden. This should never happen for role_id=1 — the admin bypass is supposed to show everything regardless of permissions.

This is a regression introduced by the permission enforcement code, not a pre-existing bug. The sidebar filtering worked before that work was done.

---

## Stage 1 — Trace the Exact Failure Point (no code changes yet)

### Step 1.1 — Confirm what the API actually returns for the admin user
Run the FastAPI backend and curl the /me endpoint with a valid admin token:

```bash
# First login to get a token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "YOUR_PASSWORD"}'

# Then use the access_token to call /me
curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Capture and paste the FULL JSON response from /me. Specifically confirm:
- Is `role_id` present in the response? What is its value?
- Is `permissions` present? What does it contain? Is it `["*"]` or a list of specific keys or empty?
- Is `role` (the role name string) present?

This is the ground truth. Everything else depends on what this returns.

### Step 1.2 — Confirm what the frontend auth store actually holds after login
In `stores/authStore.ts`, find the `fetchCurrentUser` function and check:
- Does it map the API response into the store correctly?
- Is `role_id` being extracted from the response and stored?
- What is the exact shape of the `user` object stored in the Zustand store after login?

Compare the API response shape from Step 1.1 against what `fetchCurrentUser` extracts. Any field not explicitly extracted will be `undefined` in the store even if the API returns it.

### Step 1.3 — Check the isAdmin condition in DashboardLayout.tsx
Find the exact line that determines whether the admin bypass fires. It should look something like:
```typescript
const isAdmin = user?.role_id === 1 || user?.permissions?.includes("*");
```

Check:
- Is `user?.role_id` actually populated? (depends on Step 1.2)
- Does `user?.permissions` contain `"*"` for role_id=1? (depends on Step 1.1)
- If both are undefined/false, the bypass never fires and ALL tabs get filtered

### Step 1.4 — Check the NAV_SECTIONS permission requirements
In `DashboardLayout.tsx`, look at `NAV_SECTIONS`. Each nav item has a `permission` field. List what permission each non-Operations tab requires. Then check: does the admin user's `permissions` array (from Step 1.1) actually contain those permission keys?

If the admin's permissions array is `[]` (empty) or missing the required keys, AND role_id bypass isn't firing, every tab with a permission requirement gets filtered out.

### Step 1.5 — Check the CurrentUser type definition
In `types/contracts.ts` (or wherever `CurrentUser` is defined), confirm:
- Does the type include `role_id: number`?
- Was this field added recently (in the permission enforcement work)?
- Is the field optional (`role_id?: number`) or required?

If it was added as optional and the API doesn't return it in the exact field name expected, it will be `undefined` at runtime even though the type says it exists.

---

## Stage 2 — Root Cause Classification

Based on Stage 1 findings, the root cause will be one of these:

**Case A — API doesn't return role_id in /me response**
The backend `CurrentUser` schema or the `/me` endpoint handler doesn't include `role_id` in what it returns. The frontend never gets it.
Fix: Add `role_id` to the `CurrentUser` schema in `schemas.py` and ensure the `/me` endpoint includes it.

**Case B — API returns role_id but frontend doesn't store it**
The `fetchCurrentUser` function in `authStore.ts` doesn't map `role_id` from the response into the stored user object.
Fix: Update `fetchCurrentUser` to explicitly include `role_id` when building the user object for the store.

**Case C — role_id stored but isAdmin check wrong**
The `isAdmin` check in `DashboardLayout.tsx` uses the wrong field name, wrong comparison, or is structured in a way that evaluates to false even when role_id=1.
Fix: Fix the isAdmin condition.

**Case D — Admin's permissions array is empty or wrong**
The `/me` endpoint returns an empty permissions array (or one missing the keys needed for the tabs), AND the role_id bypass fails too (one of Cases A/B/C). Both conditions fail simultaneously.
Fix: Both the role_id bypass AND ensure role_id=1 gets `["*"]` in permissions.

**Case E — NAV_SECTIONS permission keys don't match what admin has**
The permission keys in NAV_SECTIONS (e.g. `clinical.read`, `insights.view`) don't match what's stored in the database for the admin role, and the bypass isn't working.
Fix: Either fix the bypass OR ensure admin's role has all needed permissions.

---

## Stage 3 — Fix (based on Stage 2 finding)

### If Case A (API missing role_id):
In `backend_fastapi/app/core/schemas.py`, find the `CurrentUser` class and add `role_id: int` to it.
In `backend_fastapi/app/api/routers/auth_route.py`, find the `/me` handler and ensure it includes `role_id` in what it returns.
Verify with curl (Step 1.1) that `role_id` now appears in the response.

### If Case B (frontend not mapping role_id):
In `stores/authStore.ts`, find `fetchCurrentUser` and ensure the user object being stored includes `role_id`:
```typescript
// When storing the user from the API response, include role_id:
set({ user: { ...response.data, role_id: response.data.role_id } })
```
Also check the `CurrentUser` type — if `role_id` is optional (`role_id?: number`), make it required (`role_id: number`) so TypeScript catches future gaps.

### If Case C (wrong isAdmin check):
In `DashboardLayout.tsx`, fix the isAdmin condition. The correct check is:
```typescript
const isAdmin = (user?.role_id ?? 0) === 1 || (user?.permissions ?? []).includes("*");
```
Note: `user?.role_id === 1` can silently fail if role_id is undefined (undefined !== 1). The `?? 0` fallback makes it explicit.

### If Case D or E (multiple failures):
Fix all failing conditions — don't fix just one and assume the other resolves itself.

### In ALL cases — add a safety net:
In the sidebar filtering logic, add an explicit check BEFORE any permission filtering:
```typescript
// If user is role_id=1 or has wildcard permissions, show everything
if (isAdmin) return NAV_SECTIONS; // return unfiltered
```
This makes the admin bypass impossible to accidentally filter further down the code path.

---

## Stage 4 — Fix the NAV_SECTIONS Permission Mapping

While in DashboardLayout.tsx, audit the `permission` field on every nav item:
- Confirm each tab's required permission actually exists in the database permissions table
- Confirm the permission key names in NAV_SECTIONS exactly match the `feature_key` values in the database (case-sensitive exact match)
- If any tab requires a permission that doesn't exist in the database yet, either add it to the database via seed or remove the requirement from that nav item

List every nav item and its required permission, and confirm each one exists.

---

## Stage 5 — Fix Missing i18n Keys (found in screenshot)

The Rx Queue section still shows some raw keys. Search the entire codebase for any remaining `t("rx.queue.*")` or `t("rx.*")` calls and confirm all keys exist in `lib/i18n/locales/en.json`. Add any missing ones.

Also search for any other raw key patterns visible in the UI (anything showing as `section.key` format in rendered text) and add those too.

---

## Stage 6 — Verify End-to-End

After fixes:
1. Login as admin → confirm ALL sidebar sections visible (Operations, Clinical, Insights, Tools, Administration)
2. Login as a non-admin user with limited permissions → confirm only permitted tabs show
3. Curl `GET /api/v1/auth/me` with admin token → confirm `role_id: 1` and `permissions: ["*"]` in response
4. Run `npm run build` → confirm no TypeScript errors

---

## Build

After Stage 6 confirmed:
```
cd "E:\my progam pharmacy"
npm run tauri build
```
Output: `E:\my progam pharmacy\src-tauri\target\release\bundle\nsis\`

Do not build until Stage 6 passes. Show Stage 1 curl output before writing any fix code.
