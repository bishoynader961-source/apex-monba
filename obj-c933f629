# RBAC Enforcement & Route Guard Repair Specification

## Problem Statement
The Roles & Permissions UI correctly updates role permissions in the database, but non-admin users with restricted roles can still view all sidebar tabs and execute restricted actions across the entire application.

---

## Root Causes to Fix
1. **Sidebar Visibility:** `DashboardLayout.tsx` renders all `NAV_SECTIONS` unconditionally without checking active user permissions.
2. **Route Protection:** Next.js dashboard pages lack page-level RBAC checks or a `<RouteGuard />` wrapper.
3. **Backend Middleware Enforcement:** FastAPI routers do not enforce `require_permission(...)` on write/read endpoints, allowing API calls regardless of the caller's role.

---

## Required Fixes

### Phase 1: Frontend Permission Helper & Sidebar Filtering
* **Location:** `app/lib/auth.ts` or `app/components/DashboardLayout.tsx`
* **Tasks:**
  1. Create a helper function `hasPermission(user, requiredPermission: string): boolean`.
  2. If `user.role_id === 1` or `user.permissions.includes('*')`, return `true` (Owner/Admin bypass).
  3. Filter the `NAV_SECTIONS` array in `DashboardLayout.tsx` dynamically so users only see sidebar items matching their granted permissions.

### Phase 2: Page-Level Route Guard
* **Location:** `app/components/RouteGuard.tsx` (or inside each `app/dashboard/*/page.tsx`)
* **Tasks:**
  1. Wrap dashboard tab views with a `<RouteGuard permission="feature.key">` component.
  2. If the user lacks the required permission key, render an `<UnauthorizedAccess />` state instead of the tab content.

### Phase 3: Backend FastAPI Dependency Audit
* **Location:** `backend_fastapi/app/api/routers/*.py`
* **Tasks:**
  1. Audit every router file (`pos_route.py`, `inventory_route.py`, `roles_route.py`, `users_route.py`, `analytics_route.py`, etc.).
  2. Ensure every endpoint signature explicitly includes:
     `current_user: CurrentUser = Depends(require_permission("feature_key"))`
  3. Verify that `require_permission` raises `HTTP_403_FORBIDDEN` when the permission key is missing from the user's role permission list.

### Phase 4: Verification Walkthrough
1. Log in as an Administrator (`role_id: 1`) → Verify full access to all tabs and features.
2. Log in as a user with the restricted `clain` role (`inventory.read`, `inventory.write`, `inventory.reports`) →
   - Sidebar must ONLY display Inventory-related links.
   - Direct navigation to `/dashboard/roles` or `/dashboard/pos` must display an "Unauthorized Access" view.
   - Direct API calls to restricted routes without permissions must return `403 Forbidden`.