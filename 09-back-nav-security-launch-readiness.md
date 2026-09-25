# SPEC 09 — Back Navigation Gaps, Supplier Modal Fix, Remote Fix Delivery, Security & Launch Readiness

**Read Spec 06 (Architecture Deep-Dive) before starting any task in this file.**
**Apply in order: Part 1, Part 2, Part 3, Part 4.**

---

## PART 1 — Back Button Missing + Suppliers Modal X Not Working

### Issue 1A — Patients Tab: No Back Button, No Sidebar

From the screenshot, `app/patients/page.tsx` renders as a full-page view with no sidebar and no back navigation. This contradicts the Objective 1 work (backnav audit) that claimed all content pages were wrapped in the dashboard shell.

**Diagnose:**
1. Open `app/patients/page.tsx` — does it import and use `DashboardLayout` as a wrapper? Or does it render its own standalone layout?
2. Run the backnav audit script: `node scripts/audit-backnav.mjs` — confirm whether `app/patients/page.tsx` is listed as shell-covered or allowlisted.
3. Check `app/dashboard/patients/page.tsx` vs `app/patients/page.tsx` — there are two patients files. Which one is the active route? Check `DashboardLayout.tsx` NAV_SECTIONS for which href is used for the Patients link.

**Fix:**
- The active patients route must be wrapped in `DashboardLayout` (sidebar + back button)
- If the file at `app/patients/page.tsx` is the active route and it doesn't use the shell, wrap it:
```tsx
// app/patients/page.tsx
import DashboardLayout from "@/components/DashboardLayout";

export default function PatientsPage() {
  return (
    <DashboardLayout>
      {/* existing patients content */}
    </DashboardLayout>
  );
}
```
- If `app/dashboard/patients/page.tsx` is the correct route but the NAV_SECTIONS href points to `/patients` instead of `/dashboard/patients`, fix the href.
- After fixing, confirm the Patients tab shows the sidebar AND a Back button at the top-left.

### Issue 1B — Label Engine: No Back Button

`app/dashboard/label-engine/page.tsx` is a full-screen design tool. The backnav audit allowlisted it as a "full-screen design tool" — but users still need a way to return to the dashboard.

**Fix:** Unlike other pages where DashboardLayout wraps everything, the Label Engine should keep its full-screen layout but add a minimal top-left back link:
```tsx
// At the very top-left of the label engine toolbar/header:
<button
  onClick={() => router.push("/dashboard")}
  className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 mr-4"
>
  ← Dashboard
</button>
```
This sits inline in the existing top toolbar, before the W/H inputs. It does not require wrapping in DashboardLayout — just a single navigation button.

### Issue 1C — Suppliers Modal "X" Button Not Working (Purchase Orders)

In `app/dashboard/purchase-orders/page.tsx`, the Suppliers modal has an "X" close button that does nothing when clicked.

**Diagnose:**
1. Find the Suppliers modal component — search for `Suppliers` modal or dialog in `app/dashboard/purchase-orders/page.tsx` or `components/`
2. Find the X button's onClick handler — what does it call? Is there a state setter like `setShowSuppliers(false)` or `setSuppliersOpen(false)`?
3. Check if the handler is correctly bound — is the X button inside the modal component, and does it have access to the close function via props or context?

**Most likely cause:** The X button calls a close function but the modal state lives in the parent component and wasn't passed down as a prop, or the onClick is `undefined`.

**Fix pattern:**
```tsx
// Parent (purchase-orders/page.tsx):
const [suppliersOpen, setSuppliersOpen] = useState(false);

// Pass close handler to modal:
<SuppliersModal
  open={suppliersOpen}
  onClose={() => setSuppliersOpen(false)}
/>

// Inside SuppliersModal:
<button onClick={onClose} aria-label="Close">✕</button>
```

**Verify:** Click the Suppliers button → modal opens. Click X → modal closes. Click outside modal → modal should also close (add `onClick` to the backdrop overlay if not already present).

### Rebuild after Part 1

After all three fixes:
```
npm run build  # must exit 0
cd "E:\my progam pharmacy"
npm run tauri build
```
Confirm output MSI path. Install and visually verify all three fixes.

---

## PART 2 — Remote Fix Delivery System

**Goal:** When a user emails `pharmacypro.support@gmail.com` with a diagnostic report, you can identify their issue and deliver a fix without requiring remote desktop access or physical presence.

### Stage 2.1 — What's already possible (no code needed)

The diagnostic report (from Spec 08) gives you:
- App version
- Recent error log (last 5 API errors with URL, status, message)
- Database size and user/medicine count
- System settings

From this alone you can diagnose most issues: a 403 error on a specific endpoint tells you it's a permission problem; a 500 on checkout tells you it's the contract drift bug (already fixed); a missing tab tells you it's the role_id bypass.

**Fix delivery methods you already have:**
1. **Tell them to run a fix command** — if the bug is in settings or the database, you can walk them through a CLI command
2. **Push an app update** — the Tauri updater (Objective 2) means you can push a fixed version and they install it automatically
3. **Email them a corrected config file** — for settings issues, a replacement `SystemSetting` value they paste in via the Settings tab

### Stage 2.2 — In-App "Check for Updates" as Fix Delivery

The most scalable fix delivery mechanism is the auto-updater already built. When you fix a bug:
1. Fix it in the codebase
2. Run `node scripts/prepare-release.mjs` to produce a signed update
3. Upload to GitHub Releases
4. Users with the auto-updater get the fix automatically on next launch

**Verify the updater is wired:**
- In Settings → App Updates section: confirm "Check for Updates" button exists
- In `src-tauri/tauri.conf.json`: confirm `plugins.updater.endpoints` is set (even if pointing to a placeholder URL for now)
- In `src-tauri/src/lib.rs`: confirm the updater plugin is registered

If any of these are missing, implement them (Objective 2 work should have covered this — verify it actually made it into the build).

### Stage 2.3 — Manual Fix via Settings Import (new feature)

For cases where a user can't wait for an update, add a "Import Fix" feature to the Support tab:

```tsx
// In app/dashboard/support/page.tsx, add a "Technician Fix" section
// Only visible to admin (role_id=1):

{user?.role_id === 1 && (
  <div className="mt-6 pt-4 border-t border-gray-100">
    <h3 className="text-sm font-medium text-gray-500 mb-2">Apply Support Fix</h3>
    <p className="text-xs text-gray-400 mb-3">
      Paste the fix code provided by PharmacySuite support.
    </p>
    <textarea
      className="w-full h-24 text-xs font-mono border rounded p-2"
      placeholder="Paste fix code here..."
      value={fixCode}
      onChange={e => setFixCode(e.target.value)}
    />
    <button onClick={handleApplyFix} className="mt-2 px-4 py-1 bg-blue-600 text-white rounded text-sm">
      Apply Fix
    </button>
  </div>
)}
```

**`handleApplyFix` logic:**
```typescript
const handleApplyFix = async () => {
  try {
    // Fix codes are signed JSON: { action, payload, signature }
    const fix = JSON.parse(fixCode);
    
    // Verify signature matches a known public key (prevents malicious fix codes)
    // For now: fixes are just settings updates
    if (fix.action === "update_setting") {
      await api.put(`/api/v1/settings/${fix.key}`, { value: fix.value });
      showToast("Fix applied successfully. Restart may be required.", "success");
    } else if (fix.action === "reload_permissions") {
      await api.post("/api/v1/auth/refresh");
      showToast("Permissions reloaded.", "success");
    }
  } catch {
    showToast("Invalid fix code. Contact support.", "error");
  }
};
```

**Fix code format you send to users:**
```json
{"action": "update_setting", "key": "session_idle_minutes", "value": "60"}
```

This is simple, safe (settings changes only), and doesn't require remote access.

### Stage 2.4 — Structured Support Email Template

Add a "Contact Support" button to the Support tab that opens the user's mail client with a pre-filled template:

```typescript
const openSupportEmail = (diagnosticReport: string) => {
  const subject = encodeURIComponent("PharmacySuite Support Request");
  const body = encodeURIComponent(
    `Dear PharmacySuite Support,\n\n` +
    `I'm experiencing the following issue:\n\n` +
    `[DESCRIBE YOUR ISSUE HERE]\n\n` +
    `--- Diagnostic Report (auto-generated) ---\n` +
    diagnosticReport +
    `\n--- End of Report ---`
  );
  window.open(`mailto:pharmacypro.support@gmail.com?subject=${subject}&body=${body}`);
};
```

Button: "📧 Email Support (includes diagnostic info)" — clicking it gathers the diagnostic report and opens the mail client with everything pre-filled.

---

## PART 3 — Security Hardening (App + Support Email)

### Stage 3.1 — App Security: What's Already In Place

Based on the codebase audit, confirm these are present and note their status:

| Security Control | Location | Status |
|-----------------|----------|--------|
| JWT auth on all endpoints | `backend_fastapi/app/api/deps.py` | Verify with curl |
| bcrypt password hashing | `backend_fastapi/app/services/auth_service.py` | Confirm algorithm |
| Rate limiting on login | `auth_route.py` | Confirm limit (should be 5/minute) |
| Backend binds to 127.0.0.1 only | `main.py` startup | Verify with netstat |
| DevTools disabled in production | `tauri.conf.json` | Confirm `devtools: false` |
| Job Objects sidecar kill | `src-tauri/src/lib.rs` | Already confirmed |
| CSP in tauri.conf.json | `tauri.conf.json` | Show current policy |
| No secrets in git | `.gitignore` | Already cleaned up |
| Input validation + sanitization | `backend_fastapi/app/shared/schemas.py` | `SanitizedText` applied |

For any item not confirmed: curl the endpoint, show the config line, or run the check. Don't assume.

### Stage 3.2 — Additional App Hardening

**3.2.1 — Brute force protection on login:**
The rate limiter exists — confirm its limit. If it's more than 10 attempts/minute per IP, tighten to 5/minute. After 10 failed attempts from the same IP, block for 15 minutes.

Check `auth_route.py` for `@limiter.limit(...)` — show the current limit string.

**3.2.2 — Session fixation prevention:**
After login, confirm a NEW JWT is issued rather than reusing any existing token. The login flow already does this — verify explicitly.

**3.2.3 — Sensitive data not in logs:**
Search for any logging of passwords, tokens, or patient data:
```bash
grep -rn "password\|token\|patient" backend_fastapi/app/ --include="*.py" | grep -i "log\|print\|info\|debug"
```
Remove any that exist. Passwords and tokens must never appear in log output.

**3.2.4 — Database encryption (optional but recommended):**
SQLite by default stores data unencrypted. For a pharmacy handling patient records, the database should be encrypted at rest. Two options:
- **SQLCipher** — encrypted SQLite, requires recompiling SQLAlchemy bindings
- **OS-level encryption** — rely on Windows BitLocker (simpler, no code change)

For now: add a note in `docs/SECURITY_HARDENING.md` that the database at `%APPDATA%\PharmacySuite\pharmacy.db` is unencrypted and advise users to enable BitLocker on the drive. Flag SQLCipher as a future enhancement.

**3.2.5 — Backup file security:**
The Backup tab exports database files. Confirm backup files:
- Are saved to a user-chosen location (not a fixed path)
- Do not include password hashes in exports (or if they do, this is noted in the privacy policy)
- Cannot be imported by unauthorized users (check if backup restore requires authentication)

### Stage 3.3 — Support Email Security

**3.3.1 — Anti-phishing notice in Support tab (already planned in Spec 07):**
Confirm the Security Notice is in the Support tab:
```
⚠️ Security Notice:
PharmacySuite support will NEVER:
• Ask for your login password
• Ask you to share your pharmacy.db file
• Ask for your secret.key file
• Call you unsolicited and ask for remote access

If anyone claiming to be PharmacySuite support asks for any of
the above, do not comply and report it to pharmacypro.support@gmail.com
```

**3.3.2 — Gmail 2FA (your side):**
The support Gmail account `pharmacypro.support@gmail.com` must have:
- 2-factor authentication enabled
- App passwords disabled (use Google Authenticator or hardware key only)
- Login alerts enabled (email + SMS notification on new sign-in)

This is a manual step on your Gmail account — not a code change.

**3.3.3 — SPF record for your domain (if/when you get a custom domain):**
When you get `pharmacysuite.app` or similar:
- Add SPF: `v=spf1 include:_spf.google.com ~all`
- Add DKIM via Google Workspace
- Add DMARC: `v=DMARC1; p=reject; rua=mailto:dmarc@pharmacysuite.app`

Document these in `docs/SUPPORT_EMAIL_SECURITY.md` (may already exist from earlier session).

**3.3.4 — Fix codes must be unforgeable:**
The fix codes from Stage 2.3 must be verifiable. Without signing, a malicious person could email your user a "fix code" that changes a setting to something harmful.

Simple protection: fix codes include a HMAC signature:
```python
# You generate fix codes like this (on YOUR machine, never in the app):
import hmac, hashlib, json, os

SECRET = os.getenv("FIX_CODE_SECRET")  # only you know this
payload = {"action": "update_setting", "key": "session_idle_minutes", "value": "60"}
sig = hmac.new(SECRET.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()
fix_code = json.dumps({**payload, "sig": sig})
```

The app verifies the signature before applying:
```typescript
// In handleApplyFix, before applying:
// POST to /api/v1/support/verify-fix-code with the full JSON
// Backend verifies HMAC using the same secret (stored as env var)
// Returns 200 if valid, 403 if invalid
```

The `FIX_CODE_SECRET` env var is set in the backend's `.env` file and never leaves your server.

---

## PART 4 — Launch Readiness Audit

### Stage 4.1 — Functional checklist (verify each by clicking in the app)

Go through each item and mark Pass/Fail from actually running the installed MSI:

| Feature | Test | Expected |
|---------|------|----------|
| Login | Enter credentials | Success, all tabs visible |
| Setup wizard | Fresh DB (delete pharmacy.db) | Wizard appears, not login |
| Patients tab | Click Patients | Page loads with sidebar and Back button |
| Label Engine | Click Label Engine | Full-screen designer with ← Dashboard button |
| Purchase Orders → Suppliers | Click X | Modal closes |
| Support tab | Click Support | Shows pharmacypro.support@gmail.com |
| Logout | Click logout | Returns to login screen, not blank |
| Sidecar cleanup | Close app, tasklist | No backend.exe or node.exe remaining |
| Receipt History | Click Receipt History | Tab loads (empty state OK) |
| Settings → Session | Check timeout controls | Visible, admin-only |
| Roles tab | Click Roles | Loads (not stuck "Loading...") |
| Users tab | Click Users | Loads with admin user listed |
| Auto-updater | Settings → App Updates | "Check for Updates" button visible |

### Stage 4.2 — Microsoft Store readiness (current status)

Based on all work done, the current blockers before Store submission:

| Blocker | Status | What's needed |
|---------|--------|---------------|
| MSIX package | ✅ Built (81 MB) | Ready |
| Privacy policy | ✅ Created in docs/ | Must be hosted at public URL |
| Store metadata | ✅ Created in docs/ | Ready to paste into Partner Center |
| App icons | ✅ Present in src-tauri/icons/ | Ready |
| Screenshots | ❌ Not captured | Need 9+ screenshots of working app |
| Hero image | ❌ Not created | 3000×1750 PNG showing the app |
| EV code signing cert | ❌ Not purchased | Required for MSIX signing |
| Partner Center account | ❌ Not registered | $19 one-time fee |
| Age rating (IARC) | ❌ Not completed | ~5 minute questionnaire |
| Wide logo (310×150) | ⚠️ Placeholder | Needs proper asset |
| Auto-updater endpoint | ⚠️ Placeholder URL | Needs GitHub Releases setup |
| Store-channel build | ⚠️ Not configured | Must disable in-app updater for Store build |

**Priority order for completing Store submission:**
1. Register Partner Center account ($19) and reserve "Pharmacy Suite" app name
2. Host privacy policy on GitHub Pages
3. Take 9+ screenshots of the working app
4. Create hero image (use Canva or similar — 3000×1750)
5. Set up GitHub Releases for update hosting
6. Purchase EV signing cert (DigiCert ~$300/year)
7. Submit MSIX to Partner Center

### Stage 4.3 — Known remaining issues to document

Items that are known but deferred — document these in `docs/KNOWN_ISSUES.md` so you don't forget them:

1. **ESLint warnings (327):** Not errors, but include things like `react-hooks/exhaustive-deps` — worth a cleanup pass before 1.1 release
2. **Gmail DMARC:** Cannot be applied to gmail.com domain — migrate to custom domain for proper email security
3. **SQLite unencrypted at rest:** Patient data not encrypted — recommend BitLocker to users, plan SQLCipher for v2
4. **`app/patients/page.tsx` vs `app/dashboard/patients/page.tsx`:** Two files for the same feature — clean up after confirming which is active
5. **Mobile app (`mobile/` folder):** Separate codebase, not part of this release, but checkout contract drift fix should be applied there too
6. **`tauri-build-target/` in git:** ~2900 build artifacts committed — run `git rm -r --cached tauri-build-target/` and add to `.gitignore`

---

## Build and Final Verification

After completing Parts 1–3:
```
npm run build      # must exit 0
pytest             # must pass (746+/1 skipped/0 failed)
vitest run         # must pass (54/54)
node scripts/audit-labels.mjs    # must show 0 missing, 0 dangling
node scripts/audit-backnav.mjs   # must show 0 missing

cd "E:\my progam pharmacy"
npm run tauri build
```

Install fresh MSI and run the Part 4.1 checklist by clicking through the actual running app. Report each item as Pass/Fail with what you actually saw.
