# Pharmacy Suite 5‑Phase Implementation Plan

**Purpose**: Execute the master specification while preserving existing architecture, database schema, and UI layout.

---

## Phase 1 – Global Typography & Button Accessibility

1. **Verify** `app/globals.css` contains the *Phase 1* block (lines 93‑108) that forces `color: #000000` on light‑mode tabs, tables, and grids and `color: #F1F5F9` on dark mode. If missing, **add** identical CSS rules.
2. **Audit** all generic `<Button>` components (search `components/**/*.tsx` for `onClick` handlers). Ensure each handler is wrapped in `try { … } catch (e) { toast({title:"Error",message:e instanceof Error?e.message:"Action failed",variant:"destructive"}); }` to surface failures via toast instead of silent errors.
3. **Test** manually that tab text is black in light mode and white in dark mode across the app.

---

## Phase 2 – Analytics Tab Crash Resolution

1. **Locate** every `.reduce(` usage in the repo (run `rg "\.reduce\(" -n`). Confirm that each call supplies an explicit initial value (`0`, `0n`, `{}` etc.).
2. **Critical fixes** (if missing):
   - `app/pos/page.tsx` line 679: change `lines.reduce((a, l) => a + l.quantity)` → `lines.reduce((a, l) => a + l.quantity, 0)`.
   - Any other reduce without initial value must be patched similarly.
3. **Add unit‑tests** (or update existing) that call the affected functions with empty arrays and assert no exception is thrown.
4. **Run** `npm test` (or the project's test command) to ensure the regression is resolved.

---

## Phase 3 – Label Engine Button Wiring

1. **Open‑Standalone** button already calls `openLabelWindow()` which uses Tauri IPC `invoke('open_label_window')` with browser fallback – verify the Rust command `open_label_window` exists in the Tauri backend.
2. **Print** button uses `handlePrint()` that invokes `print_label` with image data – verify the Rust command `print_label` is implemented.
3. **Save / Load** template and product label functions (`handleSaveTemplate`, `handleLoadTemplate`, `handleSaveProductLabel`, `handleLoadProductLabel`) already call the REST API. Ensure the corresponding endpoints exist in the FastAPI backend.
4. **Add** missing UI disabled states: disable Save/Load buttons when required fields are empty and show a loading spinner while API calls are in progress.
5. **Write integration tests** that simulate a user clicking each toolbar button and assert the expected IPC or API call occurs (mock Tauri `invoke`).

---

## Phase 4 – Database Seeding & Admin Initialization

1. **Schema check**: confirm `backend_fastapi/app/models.py` (or equivalent) defines `roles` (`id PK, name, permissions JSON`) and `users` (`id PK, username, password_hash, role_id FK, is_owner BOOLEAN`). If missing, add migrations.
2. **Boot‑sequence**: locate the app start‑up script (e.g., `backend_fastapi/app/main.py`). Add logic after DB engine init:
   ```python
   if not session.query(User).first():
       admin_role = Role(id=1, name="Administrator", permissions=["*"])
       admin_user = User(id=1, username="admin", password_hash=hash_pw(initial_pw), role_id=1, is_owner=True)
       session.add_all([admin_role, admin_user])
       session.commit()
   ```
   *Make the password configurable via env var or a generated random value logged to console for first‑time setup.*
3. **Backend safeguards**: in user and role CRUD endpoints, reject any request that attempts to delete `User.id == 1` or modify `Role.id == 1` permissions. Return HTTP 403 with a clear message.
4. **Add unit‑tests** confirming the seeding runs only once and that protected operations return 403.

---

## Phase 5 – RBAC UI & Secure Auth Confirmation

1. **Roles UI** (`app/dashboard/roles/page.tsx`): extend the "New Role" modal to include a multi‑select list of modules (`POS`, `Inventory`, `Analytics`, `Users`, `Settings`). Store the selection as an array of strings in `permissions` column.
2. **Users UI** (`app/dashboard/users/page.tsx`): add a permission assign dropdown per user that mirrors the role permissions; allow admins to grant/revoke individual module permissions.
3. **Route Guard**: create a higher‑order component `withPermission` that reads `user.permissions` from the auth store and renders `<Unauthorized />` when the required permission is absent.
   - Wrap all protected pages (POS, Inventory, Analytics, Users, Settings) with this HOC, passing the module key.
4. **AuthConfirmModal** (`components/AuthConfirmModal.tsx` already exists). Wire it into sensitive actions:
   - **Change password** flow in settings.
   - **Edit role** modal submit handler.
   - **Delete user** confirmation button.
   The modal should request the current admin password, validate via `/api/v1/auth/confirm` endpoint, and only proceed on success.
5. **Enforce admin bypass**: if `user.role_id === 1` (owner) skip the modal and UI checks.
6. **Testing**: add end‑to‑end tests (e.g., using Playwright) that attempt to delete the owner user and verify the operation is blocked.

---

## Validation Checklist (post‑implementation)

- [ ] All tab/table text renders black in light mode and white in dark mode.
- [ ] No `.reduce()` call crashes on empty input (manual test with empty datasets).
- [ ] Label Engine toolbar buttons trigger the correct Tauri IPC or API calls.
- [ ] First launch creates immutable admin (User ID 1, Role ID 1) with `*` permissions.
- [ ] Backend rejects deletion/modification of these immutable records (403 response).
- [ ] RBAC UI allows granular permission assignment and reflects changes instantly.
- [ ] Sensitive actions always display `AuthConfirmModal` for non‑owner admins.
- [ ] All existing unit/integration tests pass.
- [ ] Manual smoke‑test of the full POS → Analytics → Label Engine workflow.

---

**Open issues / decisions**
- Initial admin password generation strategy (env var vs interactive prompt).
- Persistence of role permission list format (JSON array vs stringified list). Use JSON array for simplicity.

**Next steps**: hand this plan to an implementation‑capable agent.
