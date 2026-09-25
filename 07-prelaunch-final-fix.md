# SPEC 07 — Pre-Launch Final Fix + First-Run Wizard + Support Email + Remote Diagnostics Audit

**Context:** The MSI installs and login now works, but several critical issues remain before the app can be sold to users. This spec covers all of them in priority order.

**Read Spec 06 (Architecture Deep-Dive) before starting any work in this spec.**

---

## PART 1 — Emergency: Missing Tabs + Dark Background in MSI Build

These two issues prevent the app from being usable after installation and must be fixed first.

### Stage 1.1 — Dark Background Root Cause

The app shows a dark background in the MSI build but should show a light background by default.

**Investigate in this exact order — do not fix until the cause is confirmed:**

1. Open `app/layout.tsx` — check the `<html>` element. Does it have `className="dark"` hardcoded? If yes, that's the cause.

2. Open `app/globals.css` — find the `:root` block (the non-dark default). What are the values of `--bg-primary`, `--bg-secondary`, and `--text-main`? They should be light colors (`#F8FAFC`, `#FFFFFF`, `#1E293B`). If they're dark values, the defaults were changed.

3. Check `stores/authStore.ts` or any theme store — is there a `theme` value being initialized to `"dark"` on startup?

4. Check `localStorage` handling — is any code reading a `theme` key from `localStorage` and defaulting to dark if not set?

**State the exact cause with file+line before changing anything.**

**Fix:**
- If hardcoded `dark` class: remove it from `<html>` in `app/layout.tsx`
- If CSS variables changed: restore `:root` defaults to light values
- If theme store defaults to dark: change the initial value to `"light"`
- Add a clear comment wherever the theme is initialized: `// Default: light mode. Users can switch in settings.`

**Verify:** `npm run dev` → open browser → background is white/light gray, not dark.

---

### Stage 1.2 — Missing Tabs Root Cause

The MSI build shows fewer sidebar tabs than expected for an admin user. The dev build shows all tabs but the MSI install doesn't. This means something in the build/bundle process is causing the filtering logic to behave differently.

**Investigate:**

1. In `components/DashboardLayout.tsx`, find the `filteredSections` useMemo. Print its exact logic here — specifically: what condition determines `isAdmin`, and what happens when `isAdmin` is true?

2. Curl `GET /api/v1/auth/me` with a valid admin token from the RUNNING INSTALLED app (not the dev server) and show the full JSON response. Specifically confirm:
   - Is `role_id` present and equal to `1`?
   - Is `permissions` equal to `["*"]`?
   - Is `role` showing `"unknown"` or the correct role name?

3. If `role_id` is missing from the `/me` response: the backend schema or endpoint isn't returning it. This is the same bug that was fixed before but may not have made it into the MSI build.

**Fix (apply both unconditionally — this has failed too many times):**

In `components/DashboardLayout.tsx`, replace the entire filteredSections logic with this pattern:
```typescript
const filteredSections = useMemo(() => {
  const perms = user?.permissions ?? [];
  const isAdmin = user?.role_id === 1 || perms.includes("*");
  
  // Admin sees EVERYTHING — no filtering, no conditions, just return all tabs
  if (isAdmin) return NAV_SECTIONS;
  
  // Non-admin: filter by permission
  return NAV_SECTIONS
    .map(section => ({
      ...section,
      items: section.items.filter(item =>
        !item.permission || perms.includes(item.permission)
      )
    }))
    .filter(section => section.items.length > 0);
}, [user?.role_id, user?.permissions]);
```

In `backend_fastapi/app/api/routers/auth_route.py`, `/me` endpoint: ensure `role_id` is explicitly included in the response. Do NOT rely on it being in the JWT claim — query it fresh from the database:
```python
@router.get("/me", response_model=CurrentUser)
async def get_me(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
):
    user = await db.get(User, current_user.sub)
    if not user:
        raise HTTPException(404, "User not found")
    
    permissions = await UserRepository.permissions_for_role(db, user.role_id)
    perm_list = ["*"] if user.role_id == 1 else [p.feature_key for p in permissions]
    
    return CurrentUser(
        id=user.id,
        username=user.username,
        role_id=user.role_id,          # explicit
        role=user.role.name if user.role else "Unknown",  # from DB join
        permissions=perm_list,          # ["*"] for admin
        display_name=user.display_name,
        is_active=user.is_active,
    )
```

In `backend_fastapi/app/shared/schemas.py`, confirm `CurrentUser` has `role_id: int` as a required field (not optional).

**Verify:**
```bash
# After fix, curl /me and confirm:
curl http://127.0.0.1:8000/api/v1/auth/me -H "Authorization: Bearer TOKEN"
# Must return: { "role_id": 1, "permissions": ["*"], "role": "Administrator", ... }
```
Then open the app → all sidebar sections and tabs visible.

---

## PART 2 — First-Run Setup Wizard (Buyers Set Their Own Password)

**This is the most important feature for selling the app.** Without it, every buyer inherits your development credentials, which is both a security problem and a support burden.

### Stage 2.1 — Remove Dev Credentials from Production Build

In `backend_fastapi/app/services/seed_service.py`, find any function that creates a default admin user with a hardcoded username/password (likely `seed_admin()` or similar).

**Change:**
```python
# BEFORE (wrong — runs in production):
async def on_startup():
    await create_schema()
    await seed_default_roles()
    await seed_default_permissions()
    await seed_admin()  # ← REMOVE THIS from production startup

# AFTER (correct):
async def on_startup():
    await create_schema()
    await seed_default_roles()
    await seed_default_permissions()
    # seed_admin() only runs in development
    if os.getenv("APP_ENV", "production") == "development":
        await seed_admin()
```

### Stage 2.2 — First-Run Detection Endpoint

Add to `backend_fastapi/app/api/routers/auth_route.py` (or a new `setup_route.py`):

```python
@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """Returns whether initial setup is required (no users exist yet)."""
    count = await db.scalar(select(func.count()).select_from(User))
    return {"setup_required": count == 0}
```

This endpoint must be **unauthenticated** — it's called before any user exists.

Register it in `backend_fastapi/app/main.py`.

### Stage 2.3 — Setup Completion Endpoint

```python
@router.post("/setup/complete")
async def complete_setup(payload: SetupRequest, db: AsyncSession = Depends(get_db)):
    """Creates the first admin account. Only works when no users exist."""
    count = await db.scalar(select(func.count()).select_from(User))
    if count > 0:
        raise HTTPException(403, "Setup already completed. Use login instead.")
    
    # Validate
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if payload.password != payload.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    
    # Create admin role if not exists (should exist from seed_default_roles)
    admin_role = await db.scalar(select(Role).where(Role.id == 1))
    if not admin_role:
        raise HTTPException(500, "Default roles not seeded. Contact support.")
    
    # Hash password and create user
    hashed = get_password_hash(payload.password)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hashed,
        role_id=1,  # Always admin for first user
        is_active=True,
    )
    db.add(user)
    
    # Store pharmacy name in settings
    if payload.pharmacy_name:
        db.add(SystemSetting(key="pharmacy_name", value=payload.pharmacy_name))
    
    await db.commit()
    return {"success": True, "message": "Setup complete. You can now sign in."}
```

Add `SetupRequest` Pydantic schema:
```python
class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    confirm_password: str
    pharmacy_name: str | None = None
```

### Stage 2.4 — Frontend: Setup Wizard Page

Create `app/setup/page.tsx` — a 3-step wizard shown only when `setup_required: true`.

**Step 1 — Welcome screen:**
```tsx
// Clean centered layout, light background
// Pharmacy Suite logo (use existing logo from public/ or src-tauri/icons/)
// Heading: "Welcome to Pharmacy Suite"
// Subtext: "Let's set up your account. This takes about 2 minutes."
// Single button: "Get Started →"
```

**Step 2 — Create Admin Account:**
```tsx
// Fields:
// - Full Name (display_name) — required
// - Username — required, alphanumeric + underscores only
// - Password — required, min 8 chars, show/hide toggle
// - Confirm Password — required, must match
// Inline validation on blur for each field
// "Create Account" button (disabled until all fields valid)
// On submit: POST /api/v1/setup/complete
// On success: move to Step 3
// On error: show error message inline (not a toast — the user needs to see it)
```

**Step 3 — Pharmacy Details (optional but encouraged):**
```tsx
// Fields:
// - Pharmacy Name — stored as SystemSetting "pharmacy_name"
// - Address — optional, stored as "pharmacy_address"
// - Phone — optional, stored as "pharmacy_phone"
// - License Number — optional, stored as "pharmacy_license"
// "Finish Setup" button
// "Skip for now" link (smaller text below button)
// On finish or skip: redirect to /login with message:
//   "Setup complete! Sign in with the credentials you just created."
```

**Redirect logic (in `app/login/page.tsx` or root layout):**
```typescript
// On app load, before showing login:
const { data } = await api.get("/api/v1/setup/status");
if (data.setup_required) {
  router.replace("/setup");
  return;
}
// Otherwise show normal login
```

### Stage 2.5 — Database Location (Critical for MSI)

The installed MSI app must write its database to a user-writable location, not next to the executable (Program Files is read-only without admin rights).

In `backend_fastapi/app/core/database.py`:
```python
import os
import sys

def get_database_path() -> str:
    """Get the correct database path for the current environment."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle (production)
        # Use %APPDATA%\PharmacySuite on Windows
        if sys.platform == "win32":
            app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
            data_dir = os.path.join(app_data, "PharmacySuite")
        else:
            data_dir = os.path.expanduser("~/.pharmacysuite")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "pharmacy.db")
    else:
        # Development: use local file
        return os.path.join(os.path.dirname(__file__), "../../../../pharmacy.db")

DATABASE_URL = f"sqlite+aiosqlite:///{get_database_path()}"
```

**Verify after MSI install:**
```bash
# Check database exists at correct location
dir "%APPDATA%\PharmacySuite\"
# Should show: pharmacy.db

# Check it's empty (zero users) on fresh install
sqlite3 "%APPDATA%\PharmacySuite\pharmacy.db" "SELECT COUNT(*) FROM users;"
# Should return: 0
# This means setup wizard will appear on first launch ✓
```

---

## PART 3 — Support Email Configuration

### Stage 3.1 — Seed the support email

In `backend_fastapi/app/services/seed_service.py`, add to `seed_default_settings()` (or create this function if it doesn't exist):
```python
async def seed_default_settings(db: AsyncSession):
    defaults = [
        ("support_email", "pharmacypro.support@gmail.com"),
        ("support_name", "PharmacySuite Support"),
        ("support_message", "For feature requests, technical issues, or questions, email us anytime."),
        ("pharmacy_name", ""),
        ("session_idle_minutes", "15"),
        ("session_absolute_minutes", "480"),
    ]
    for key, value in defaults:
        existing = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if not existing:
            db.add(SystemSetting(key=key, value=value))
    await db.commit()
```

Call this in `on_startup()`.

### Stage 3.2 — Support Tab page

Create `app/dashboard/support/page.tsx` if it doesn't exist, or verify the existing one:

```tsx
export default function SupportPage() {
  const [settings, setSettings] = useState<{
    support_email: string;
    support_name: string;
    support_message: string;
    pharmacy_name: string;
  } | null>(null);

  useEffect(() => {
    // Fetch support settings from /api/v1/settings
    api.get("/api/v1/settings").then(({ data }) => {
      const map = Object.fromEntries(data.map((s: any) => [s.key, s.value]));
      setSettings({
        support_email: map.support_email ?? "pharmacypro.support@gmail.com",
        support_name: map.support_name ?? "PharmacySuite Support",
        support_message: map.support_message ?? "",
        pharmacy_name: map.pharmacy_name ?? "",
      });
    });
  }, []);

  return (
    <div className="max-w-lg mx-auto mt-16 p-8 bg-white rounded-xl shadow-sm border border-gray-100">
      <div className="text-center mb-8">
        {/* App logo */}
        <h1 className="text-2xl font-bold text-gray-900 mt-4">PharmacySuite Support</h1>
        <p className="text-gray-500 mt-2">
          {settings?.support_message ?? "We're here to help."}
        </p>
      </div>
      
      <div className="space-y-4">
        <div>
          <p className="text-sm font-medium text-gray-500">Support Team</p>
          <p className="text-gray-900">{settings?.support_name}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500">Email</p>
          <a
            href={`mailto:${settings?.support_email}`}
            className="text-blue-600 hover:underline font-medium"
          >
            {settings?.support_email ?? "pharmacypro.support@gmail.com"}
          </a>
        </div>
        <div className="pt-4 border-t border-gray-100">
          <p className="text-xs text-gray-400">
            Include your pharmacy name and a description of the issue in your email.
            Response time: typically within 24 hours on business days.
          </p>
        </div>
      </div>
    </div>
  );
}
```

### Stage 3.3 — Verify Support tab in sidebar

In `components/DashboardLayout.tsx`, confirm the Support nav item exists:
```typescript
{
  href: "/dashboard/support",
  label: "nav.support",
  icon: HelpCircleIcon,
  permission: undefined,  // visible to all logged-in users
}
```

Add `"nav.support": "Support"` to all locale files if missing.

---

## PART 4 — Remote Diagnostics / GitHub Connection Audit

**This is an AUDIT ONLY — do not make any code changes in this part.**

The question: does the app have any existing mechanism for you to help users fix issues remotely, or for users to submit bug reports that you can see?

**Check these locations and report what exists:**

### 4.1 — Crash Reporting
Check if `POST /api/v1/crash-report` endpoint exists in the backend routers. If yes:
- What data does it collect? (stack trace, user info, app version?)
- Where does it send the data? (a remote server, a local log file, or nowhere?)
- Does the `ErrorBoundary` in `app/layout.tsx` call this endpoint when a crash happens?

### 4.2 — Error Logging
Check `backend_fastapi/app/main.py` for any logging configuration. Is the backend writing logs to a file, or only to stdout (which disappears when the sidecar window is hidden)?

### 4.3 — Audit Log
The blueprint mentions an "Audit Log" tab. What does it log? Is this log accessible to you remotely, or only to the pharmacy admin locally?

### 4.4 — Telemetry
Does the app send any telemetry, analytics, or usage data to any external server? Check for any external API calls that aren't to `127.0.0.1`.

### 4.5 — Update Mechanism
Does the app check for updates? Is there a version endpoint or Tauri updater configured?

**Report findings as a table:**
| Feature | Exists? | What it does | Can you see it remotely? |
|---------|---------|--------------|--------------------------|
| Crash reporting | ? | ? | ? |
| Error logging to file | ? | ? | ? |
| Audit log | ? | ? | ? |
| Telemetry | ? | ? | ? |
| Update checking | ? | ? | ? |

**Based on the findings, also answer:**
- Can you currently help a user fix an issue without physically accessing their machine? (Yes/No + why)
- What would need to be added to enable remote diagnostics? (brief description, no implementation yet)

---

## PART 5 — Final Verification Checklist

After Parts 1–4 are complete, verify each item by actually running the installed MSI:

| Item | How to verify | Expected result |
|------|---------------|-----------------|
| Light background | Open MSI app | White/light gray background |
| All tabs visible | Log in as admin | All sections: Operations, Clinical, Insights, Tools, Administration |
| Setup wizard | Fresh install on a machine with no pharmacy.db | Setup wizard appears, NOT login screen |
| Support email | Click Support tab | Shows "pharmacypro.support@gmail.com" |
| Login after setup | Complete wizard, then log in | Succeeds with chosen credentials |
| Role name | Bottom-left of sidebar | Shows "Administrator" not "unknown" |

---

## Build

After Parts 1–4 are confirmed:
```
cd "E:\my progam pharmacy"
npm run tauri build
```

Output MSI: `E:\my progam pharmacy\src-tauri\target\release\bundle\msi\`
Output NSIS: `E:\my progam pharmacy\src-tauri\target\release\bundle\nsis\`

Install the MSI fresh and run through the Part 5 verification checklist before considering this complete.
