# SPEC 02 — Fresh Install & First-Run Setup for Buyers

**Purpose:** When a customer buys and installs the app, they must get a completely clean slate — no pre-existing admin credentials, no demo data, no trace of your development database. The first time they open the app they go through a guided setup wizard to create their own admin account and pharmacy profile.

**Architecture reference:** `backend_fastapi/app/services/seed_service.py`, `backend_fastapi/app/core/models.py`, `app/login/page.tsx`

---

## The Core Problem

Your current build ships with `pharmacy.db` containing your development data — your admin account, your test roles, your test permissions. Every buyer who installs the app inherits your database. This must not happen.

---

## Stage 1 — Strip the Database from the Build

### Step 1.1 — Exclude pharmacy.db from the installer
In `src-tauri/tauri.conf.json`, under `bundle.resources`, confirm `pharmacy.db` is NOT listed. The database file must never be bundled with the installer.

In `src-tauri/src/lib.rs`, when the backend sidecar starts, it should check if `pharmacy.db` exists in the app data directory. If it does NOT exist, the backend creates a fresh empty database using `create_schema` — this is the standard FastAPI startup behavior via `on_startup`.

Confirm `backend_fastapi/app/main.py` `on_startup` event calls `create_schema()` which creates all tables if they don't exist. This is the correct behavior — it means a fresh install automatically gets an empty database.

### Step 1.2 — Remove dev seed data from production startup
In `backend_fastapi/app/services/seed_service.py`, there are likely seed functions that create a default admin, default roles, and default permissions.

Audit every function called in `on_startup`:
- `seed_default_roles()` → keep this (creates system roles like Administrator, Staff)
- `seed_default_permissions()` → keep this (creates the permission registry)
- `seed_admin()` or any function that creates a specific admin user with a hardcoded username/password → **REMOVE from production startup**. This function should only run in a dev/test environment.

Add an environment check:
```python
if os.getenv("APP_ENV") == "development":
    await seed_admin()  # Only in dev
```

The `APP_ENV` env var is already used elsewhere in the codebase — use the same pattern.

---

## Stage 2 — First-Run Detection

### Step 2.1 — Backend: first-run endpoint
Add `GET /api/v1/setup/status` (unauthenticated):
```python
@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    user_count = await db.scalar(select(func.count()).select_from(User))
    return {"setup_required": user_count == 0}
```

This is the single source of truth: if there are zero users in the database, setup is required.

### Step 2.2 — Frontend: first-run redirect
In `app/login/page.tsx` (or `app/layout.tsx`), on load, call `GET /api/v1/setup/status`. If `setup_required: true`, redirect to `/setup` instead of showing the login form.

---

## Stage 3 — First-Run Setup Wizard (new page: `app/setup/page.tsx`)

This page is only accessible when `setup_required: true`. Once setup is complete and a user exists, navigating to `/setup` redirects to `/login`.

### Step 3.1 — Wizard design (3 steps)

**Step 1: Welcome**
- App logo, app name "Pharmacy Suite"
- Heading: "Welcome. Let's set up your pharmacy."
- Subtext: "This takes about 2 minutes. You'll create your admin account and enter your pharmacy details."
- One button: "Get Started →"

**Step 2: Create Admin Account**
Fields:
- Admin Full Name (required)
- Username (required, alphanumeric, shown as login credential)
- Password (required, min 8 chars, show/hide toggle)
- Confirm Password (required, must match)

Validation: inline, on blur. "Create Account" button disabled until all fields valid.

On submit: calls `POST /api/v1/setup/complete`:
```json
{
  "admin_name": "John Smith",
  "username": "admin",
  "password": "their_chosen_password"
}
```

**Step 3: Pharmacy Profile**
Fields:
- Pharmacy Name (required) — stored in `SystemSetting` key `pharmacy_name`
- Address (optional)
- Phone (optional)
- License Number (optional)

"Finish Setup" button → calls `PUT /api/v1/settings` to store these values → redirects to `/login` with a success message: "Setup complete. Sign in with your new credentials."

### Step 3.2 — Backend: setup endpoint
Add `POST /api/v1/setup/complete` (unauthenticated, but only works when user count = 0):
```python
@router.post("/setup/complete")
async def complete_setup(payload: SetupRequest, db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(User))
    if count > 0:
        raise HTTPException(403, "Setup already completed")
    
    # Create admin role (role_id=1) if not exists
    # Create admin user with role_id=1
    # Hash password with bcrypt
    # Store pharmacy settings
    return {"success": True}
```

This endpoint is safe to leave unauthenticated because it only works when zero users exist — calling it on an already-set-up instance returns 403.

---

## Stage 4 — Password Change After Purchase

The buyer sets their password during setup (Stage 3). They can change it at any time via the existing `POST /api/v1/auth/change-password` endpoint, which is already implemented in `auth_route.py`.

Confirm this endpoint:
1. Requires the current password to be provided (prevents unauthorized changes)
2. Is accessible from the Settings tab under "Account" section
3. Works correctly for role_id=1 without requiring the separate lock password

---

## Stage 5 — Database Storage Location

The database must be stored in the OS app data directory, not next to the executable (which may be read-only after installation):

In `backend_fastapi/app/core/database.py`, the database URL should use:
```python
import platformdirs
data_dir = platformdirs.user_data_dir("PharmacySuite", "PharmacySuite")
os.makedirs(data_dir, exist_ok=True)
db_path = os.path.join(data_dir, "pharmacy.db")
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
```

On Windows this resolves to `%APPDATA%\PharmacySuite\PharmacySuite\pharmacy.db` — writable even when the app is installed in Program Files.

Add `platformdirs` to `requirements.txt` if not already present.

---

## Verify End-to-End

1. Build the app with `npm run tauri build`
2. Install it fresh on a Windows machine that has never had the app
3. Confirm: app opens to the setup wizard, not the login screen
4. Complete setup with a test username and password
5. Confirm: redirected to login, can log in with the new credentials
6. Confirm: all sidebar tabs are visible (role_id=1 bypass working)
7. Uninstall and reinstall — confirm setup wizard appears again (fresh database)
