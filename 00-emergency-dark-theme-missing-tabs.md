# EMERGENCY FIX — Dark Theme Regression + Missing Sidebar Tabs

**Priority: Apply immediately, before any other spec.**

Two regressions visible in screenshot taken 9/21/2026:
1. App is rendering in dark mode when light mode is expected
2. Most sidebar tabs are missing despite being logged in as admin

---

## Fix 1 — Dark Theme Regression

### Diagnose
The app switched from a light background to a fully dark theme. This is either:
- **Case A:** A `dark` class was added to `<html>` in `app/layout.tsx` or a theme provider
- **Case B:** CSS variables were changed in `app/globals.css` so that the default (non-dark) theme now uses dark colors
- **Case C:** A `localStorage` key like `theme` or `color-scheme` got set to `"dark"` and is being read on startup

**Check immediately (no code changes yet):**
1. Open `app/layout.tsx` — does it have `className="dark"` on `<html>`? If yes, remove it.
2. Open `app/globals.css` — what are the `:root` (non-dark) variable values for `--bg-primary` and `--text-main`? They should be light colors like `#F8FAFC` and `#1E293B`. If they've been changed to dark values, revert them.
3. Search for any `localStorage.setItem` call that sets a `theme` or `dark` key — if found, check when it's called.

**Fix based on case found:**
- Case A: Remove `dark` class from `<html>` in `app/layout.tsx`
- Case B: Restore `:root` CSS variable values to light-mode defaults in `app/globals.css`
- Case C: Clear the localStorage key on startup if the user hasn't explicitly chosen dark mode

**Verify:** After fix, `npm run dev` → open `http://localhost:3000` → app should render with white/light background.

---

## Fix 2 — Missing Sidebar Tabs (Partial role_id=1 Bypass Failure)

### Evidence
The last working screenshot (9/18/2026) showed all tabs. The current screenshot (9/21/2026) is missing:
- Clinical: Drug Interactions, Drugs, Quick SIG, SIG Codes
- Tools: Templates, Bulk Import, Bulk Label Print, Label Engine, Invoice Parse, Gift Cards
- Administration: Backup, Settings

Only showing: Operations (partial), Insights (Sales Analytics, Analytics only), Administration (Users, Roles, Support).

The "admin / unknown" at bottom-left means the role name from `/me` is still `"unknown"` — the role fix didn't fully land.

### Diagnose — Two separate problems

**Problem A: role name "unknown"**
`GET /api/v1/auth/me` is returning `role: "unknown"`. Check the `/me` endpoint handler in `backend_fastapi/app/api/routers/auth_route.py`:
1. What SQL query fetches the user?
2. Does it JOIN to the `Role` table to get the role name?
3. Is `role` field in `CurrentUser` schema populated from the JWT claim or from a DB lookup?

Curl it directly and show the full response:
```bash
curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Problem B: NAV_SECTIONS items filtered despite admin**
The tabs that are disappearing all have permission requirements. Even though role_id=1 should bypass everything, SOME tabs show and SOME don't. This means the `isAdmin` check is returning `true` for some items and `false` for others — which should be impossible if it's a single boolean.

Check `components/DashboardLayout.tsx`:
1. Find the `filteredSections` useMemo
2. Find the `isAdmin` calculation
3. Is `isAdmin` being recalculated per-item, or once per render?
4. Is there any OTHER filtering happening after the isAdmin check (e.g. a section being filtered out if ALL its items are hidden)?

The most likely cause: the NAV_SECTIONS filtering logic has a bug where sections with ALL items filtered become empty, and empty sections get removed — but if isAdmin is intermittently false for some items, some sections lose all their items.

### Fix

**For "unknown" role:**
In `auth_route.py` `/me` handler, ensure it fetches the role name from the database rather than from the JWT `role` claim (which may be stale). The `CurrentUser` schema's `role` field should come from `user.role.name` via a JOIN, not from the token.

If the token's `role` claim is `"Administrator"` but the schema returns `"unknown"`, the schema mapping is wrong. Check `backend_fastapi/app/shared/schemas.py` `CurrentUser` class — specifically how `role` is populated from the `User` ORM object.

**For missing tabs:**
In `components/DashboardLayout.tsx`:
```typescript
const filteredSections = useMemo(() => {
  // THIS must be calculated ONCE, not per-item
  const isAdmin = (user?.role_id ?? 0) === 1 || 
                  (user?.permissions ?? []).includes("*");
  
  if (isAdmin) {
    // Return ALL sections with ALL items - no filtering at all
    return NAV_SECTIONS;
  }
  
  // Only filter for non-admin users
  return NAV_SECTIONS
    .map(section => ({
      ...section,
      items: section.items.filter(item => 
        !item.permission || hasPermission(item.permission)
      )
    }))
    .filter(section => section.items.length > 0);
}, [user]);
```

The key change: if `isAdmin` is true, return `NAV_SECTIONS` directly without any filtering or mapping. This eliminates any possibility of items being accidentally filtered for the admin.

### Verify
After fix:
1. `curl GET /api/v1/auth/me` with admin token → confirm `role_id: 1`, `role: "Administrator"` (or similar), `permissions: ["*"]`
2. Open the app → confirm ALL sections and tabs visible in the sidebar
3. Confirm role name at bottom-left shows "Administrator" not "unknown"

---

## After Both Fixes

Run `npm run build` → confirm no TypeScript errors → then:
```
cd "E:\my progam pharmacy"
npm run tauri build
```

Test the packaged app:
- Confirm light (white) background
- Confirm all sidebar sections and tabs visible
- Confirm "admin / Administrator" shown at bottom-left
