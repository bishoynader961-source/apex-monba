# SPEC 01 — Critical Bug Fixes (Apply First)

**Apply this spec before all others.** These are foundational bugs that affect every other part of the app. Fixing them first means every subsequent spec builds on a stable base.

**Architecture reference:** APP_BLUEPRINT.md Section 7 (Top 3 Structural Errors) + logout/loading bugs found in manual testing.

---

## Bug 1 — Logout Produces Blank White Window

**Files:** `stores/authStore.ts`, `components/DashboardLayout.tsx`

**Root cause:** `logout()` in `authStore.ts` clears token and user state but does not trigger navigation. `DashboardLayout` returns `null` when unauthenticated (line 118), producing a blank white screen with no redirect.

**Fix:**
In `components/DashboardLayout.tsx`, add a `useEffect` that watches `user` from the auth store and redirects to `/login` when it becomes null:
```typescript
const user = useAuthStore((s) => s.user);
const router = useRouter();
useEffect(() => {
  if (!user) router.replace("/login");
}, [user, router]);
```
This must fire BEFORE the layout renders any content — place it at the top of the component, before any other logic.

Also add a loading state: while `user` is null but a token exists in localStorage (indicating a refresh is in progress), show a spinner rather than redirecting immediately. This prevents a flash-to-login on cold start before `fetchCurrentUser` resolves.

**Verify:** Click logout in the running dev server. Confirm the login screen appears immediately with no blank white state.

---

## Bug 2 — Users and Roles Tabs Stuck on "Loading..." Forever

**Files:** `stores/authStore.ts` (`hasPermission`, `useCan`), `backend_fastapi/app/api/deps.py` (`require_permission`)

**Root cause (two simultaneous gaps):**
- **Frontend:** `useCan("users.read")` calls `hasPermission` which checks `perms.includes(permission)`. When admin's permissions array is `["*"]`, `perms.includes("users.read")` is `false` because `"*"` is not `"users.read"`. The page guard evaluates to false and the page never makes the API call.
- **Backend:** `require_permission` in `deps.py` relies on `user.role.lower().startswith("admin")` as the admin bypass. This is fragile — the role name string can change. It should check `user.role_id == 1` OR `"*" in user.permissions`.

**Fix (frontend) — `stores/authStore.ts`:**
```typescript
const hasPermission = (permission: string): boolean => {
  const perms = get().user?.permissions ?? [];
  return perms.includes("*") || perms.includes(permission);
};
```
Also update `useCan` hook to use the same logic if it has a separate implementation.

**Fix (backend) — `backend_fastapi/app/api/deps.py`:**
```python
async def require_permission(permission: str, user: CurrentUser = Depends(get_current_user)):
    if user.role_id == 1:
        return  # Owner has all permissions
    if "*" in (user.permissions or []):
        return  # Wildcard grant
    if permission in (user.permissions or []):
        return  # Explicit grant
    raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
```
Remove the fragile `user.role.lower().startswith("admin")` check entirely.

**Verify:**
```bash
# With admin token (role_id=1, permissions=["*"]):
curl http://127.0.0.1:8000/api/v1/users -H "Authorization: Bearer ADMIN_TOKEN"
curl http://127.0.0.1:8000/api/v1/roles -H "Authorization: Bearer ADMIN_TOKEN"
# Both must return 200 with data, not 403
```
Then navigate to Users and Roles tabs — both must load data, not show "Loading..." forever.

---

## Bug 3 — API 403/500 Errors Never Shown to User (Silent Failures)

**Files:** `lib/api.ts` (Axios interceptor), `stores/uiStore.ts`

**Root cause (Blueprint §7 #1):** The Axios interceptor at `lib/api.ts:64-65` only handles 401. 403 Forbidden and 500 Server Error are thrown as raw errors with no user notification. This causes pages to silently hang on "Loading..." with no explanation.

**Fix — `lib/api.ts` interceptor:**
```typescript
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status;
    if (status === 401) {
      // existing refresh logic
    } else if (status === 403) {
      useUiStore.getState().showToast(
        "You don't have permission to perform this action.",
        "error"
      );
    } else if (status === 500) {
      const detail = (error.response?.data as any)?.detail ?? "Server error. Please try again.";
      useUiStore.getState().showToast(detail, "error");
    }
    return Promise.reject(error);
  }
);
```

**Verify:** Trigger a 403 by calling a protected endpoint without permission. Confirm a toast notification appears. Check that 500 errors also produce a visible toast.

---

## Bug 4 — Permission Guard Drift (Blueprint §7 #2)

**Files:** `backend_fastapi/app/api/deps.py`, `stores/authStore.ts`

Already described in Bug 2 fix above. After fixing Bug 2, confirm both frontend and backend use the same authority hierarchy: `role_id == 1` → `"*"` in permissions → explicit permission string.

Search the entire codebase for any remaining `role.lower().startswith("admin")` pattern and replace all instances with `role_id == 1` checks.

**Verify:** Grep for `startswith("admin")` in the backend — should find zero results after fix.

---

## Bug 5 — SessionStore Type Unsoundness (Blueprint §7 #3)

**Files:** `stores/sessionStore.ts`

**Root cause:** `TimeoutValue = number | "never"` causes arithmetic on a union type. TypeScript errors were suppressed with local `const` extraction rather than proper narrowing.

**Fix:** Refactor `tick()` to split into separate functions that only accept `number`:
```typescript
// Store "never" as null internally
type SessionConfig = {
  idleMs: number | null;    // null = never timeout
  absoluteMs: number | null; // null = never timeout
};

function checkIdleTimeout(idleMs: number, lastActivity: number): boolean {
  return Date.now() - lastActivity > idleMs;
}

function checkAbsoluteTimeout(absoluteMs: number, sessionStart: number): boolean {
  return Date.now() - sessionStart > absoluteMs;
}

// In tick():
if (config.idleMs !== null && checkIdleTimeout(config.idleMs, lastActivity)) {
  triggerLogout("idle");
}
if (config.absoluteMs !== null && checkAbsoluteTimeout(config.absoluteMs, sessionStart)) {
  triggerLogout("absolute");
}
```

Convert `"never"` string from the API/settings to `null` at the store boundary, never inside `tick()`.

**Verify:** `npm run build` must complete with zero TypeScript errors. No `TS2362` or similar arithmetic-on-union errors.

---

## Execution Order

1. Bug 2 (Users/Roles loading) — fix first, it's blocking admin functionality
2. Bug 3 (403/500 silence) — fix second, it makes all other bugs visible
3. Bug 1 (logout white screen)
4. Bug 4 (permission guard drift)
5. Bug 5 (sessionStore type)

After all five: `npm run build` must pass with zero errors. Then:
```
cd "E:\my progam pharmacy"
npm run tauri build
```
