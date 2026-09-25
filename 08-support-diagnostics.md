# SPEC 08 — Support Tab: Diagnostic Info + Crash Report Submission

**Purpose:** Give users two practical ways to report issues to you without requiring remote access to their machine:
1. A "Copy Diagnostic Info" button that copies their app state to clipboard for pasting into an email
2. A "Send Crash Report" button that POSTs structured data to a lightweight server you control

**Read Spec 06 (Architecture Deep-Dive) before starting.**
**Apply after Spec 07 (Support tab base is created there).**

---

## PART 1 — "Copy Diagnostic Info" Button

### What it does
When a user clicks this button, it gathers key information about their installation and copies it to their clipboard as formatted text. They paste it into an email to `pharmacypro.support@gmail.com` and you immediately have everything you need to diagnose their issue.

### Stage 1.1 — What to collect

The diagnostic info bundle should contain:

```
=== PharmacySuite Diagnostic Report ===
Generated: 2026-09-21 14:30:00 UTC

--- App Info ---
App Version: 1.0.0
Build: production
Platform: Windows 11 (10.0.22631)
Architecture: x64

--- Pharmacy Info ---
Pharmacy Name: City Pharmacy
Admin Username: admin (ID: 1)

--- Backend Health ---
API Status: Connected (127.0.0.1:8000)
Database: pharmacy.db (2.4 MB)
User Count: 3
Medicine Count: 147
Last Backup: 2026-09-20 09:15:00

--- Session Info ---
Session Started: 2026-09-21 13:00:00
Current User: admin (role_id: 1)
Permissions: * (full access)

--- Recent Errors (last 5) ---
[2026-09-21 14:22:01] 403 GET /api/v1/roles - Permission denied
[2026-09-21 14:10:45] Network timeout on /api/v1/analytics
(none if no recent errors)

--- System Settings ---
Session Idle Timeout: 15 minutes
Session Absolute Timeout: 480 minutes
Language: en

=== End of Report ===
```

### Stage 1.2 — Frontend: gather the data

In `app/dashboard/support/page.tsx`, add a `generateDiagnosticReport()` async function:

```typescript
async function generateDiagnosticReport(): Promise<string> {
  const lines: string[] = [];
  const now = new Date().toISOString();
  
  lines.push("=== PharmacySuite Diagnostic Report ===");
  lines.push(`Generated: ${now}`);
  lines.push("");
  
  // App info — from Tauri or a /api/v1/version endpoint
  lines.push("--- App Info ---");
  try {
    const { data: ver } = await api.get("/api/v1/version");
    lines.push(`App Version: ${ver.version}`);
    lines.push(`Build: ${ver.env ?? "production"}`);
  } catch {
    lines.push("App Version: unknown");
  }
  
  // Platform info — from Tauri APIs if available, or navigator
  lines.push(`Platform: ${navigator.platform}`);
  lines.push(`User Agent: ${navigator.userAgent}`);
  lines.push("");
  
  // Pharmacy info
  lines.push("--- Pharmacy Info ---");
  try {
    const { data: settings } = await api.get("/api/v1/settings");
    const map = Object.fromEntries(settings.map((s: any) => [s.key, s.value]));
    lines.push(`Pharmacy Name: ${map.pharmacy_name || "(not set)"}`);
  } catch {
    lines.push("Pharmacy Name: (error fetching)");
  }
  
  // Current user
  const user = useAuthStore.getState().user;
  lines.push(`Admin Username: ${user?.username ?? "unknown"} (ID: ${user?.id ?? "?"})`);
  lines.push("");
  
  // Backend health
  lines.push("--- Backend Health ---");
  try {
    const { data: health } = await api.get("/api/v1/health");
    lines.push(`API Status: Connected (127.0.0.1:8000)`);
    lines.push(`Database Size: ${health.db_size_mb ?? "unknown"} MB`);
    lines.push(`User Count: ${health.user_count ?? "unknown"}`);
    lines.push(`Medicine Count: ${health.medicine_count ?? "unknown"}`);
  } catch (err) {
    lines.push("API Status: ERROR — backend not responding");
  }
  lines.push("");
  
  // Recent errors from the error log store
  lines.push("--- Recent Errors (last 5) ---");
  const recentErrors = getRecentErrors(); // from error log (see Stage 1.3)
  if (recentErrors.length === 0) {
    lines.push("(no recent errors logged)");
  } else {
    recentErrors.forEach(e => lines.push(`[${e.timestamp}] ${e.status} ${e.method} ${e.url} - ${e.message}`));
  }
  lines.push("");
  
  lines.push("=== End of Report ===");
  return lines.join("\n");
}
```

### Stage 1.3 — Error log store

Create a lightweight in-memory error log in `stores/errorLogStore.ts`:

```typescript
interface ErrorEntry {
  timestamp: string;
  status: number;
  method: string;
  url: string;
  message: string;
}

interface ErrorLogState {
  entries: ErrorEntry[];
  addEntry: (entry: ErrorEntry) => void;
  getRecent: (n?: number) => ErrorEntry[];
  clear: () => void;
}

export const useErrorLogStore = create<ErrorLogState>()((set, get) => ({
  entries: [],
  addEntry: (entry) => set(state => ({
    entries: [entry, ...state.entries].slice(0, 50) // keep last 50
  })),
  getRecent: (n = 5) => get().entries.slice(0, n),
  clear: () => set({ entries: [] }),
}));

// Helper for use outside React components
export const getRecentErrors = (n = 5) =>
  useErrorLogStore.getState().getRecent(n);
```

In `lib/api.ts`, update the response interceptor to log errors:
```typescript
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status ?? 0;
    const method = error.config?.method?.toUpperCase() ?? "?";
    const url = error.config?.url ?? "?";
    const message = (error.response?.data as any)?.detail ?? error.message ?? "Unknown error";
    
    // Log to error store for diagnostic report
    useErrorLogStore.getState().addEntry({
      timestamp: new Date().toISOString(),
      status,
      method,
      url,
      message,
    });
    
    // Existing toast logic for 403/500
    if (status === 403) {
      useUiStore.getState().showToast("You don't have permission to do that.", "error");
    } else if (status === 500) {
      useUiStore.getState().showToast(message, "error");
    }
    
    return Promise.reject(error);
  }
);
```

### Stage 1.4 — Backend: health endpoint with diagnostic data

Add `GET /api/v1/health` (or enhance if it exists) in a `health_route.py`:

```python
@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Returns diagnostic health info for the support panel."""
    user_count = await db.scalar(select(func.count()).select_from(User))
    medicine_count = await db.scalar(select(func.count()).select_from(Product))
    
    # Get database file size
    db_path = str(engine.url).replace("sqlite+aiosqlite:///", "")
    db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2) if os.path.exists(db_path) else 0
    
    return {
        "status": "ok",
        "version": "1.0.0",
        "user_count": user_count,
        "medicine_count": medicine_count,
        "db_size_mb": db_size_mb,
        "env": os.getenv("APP_ENV", "production"),
    }
```

Register this router in `main.py`. This endpoint should require authentication (no unauthenticated health dumps).

### Stage 1.5 — Copy to clipboard UI

In `app/dashboard/support/page.tsx`, add the button:

```tsx
const [copying, setCopying] = useState(false);
const [copied, setCopied] = useState(false);

const handleCopyDiagnostics = async () => {
  setCopying(true);
  try {
    const report = await generateDiagnosticReport();
    await navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  } catch (err) {
    // Fallback: show in a textarea the user can manually copy
    setFallbackReport(report);
  } finally {
    setCopying(false);
  }
};

// Button JSX:
<button
  onClick={handleCopyDiagnostics}
  disabled={copying}
  className="w-full py-2 px-4 rounded-lg border border-gray-200 text-gray-700
             hover:bg-gray-50 flex items-center gap-2 justify-center"
>
  {copying ? (
    <span>Gathering info...</span>
  ) : copied ? (
    <span>✓ Copied to clipboard</span>
  ) : (
    <span>📋 Copy Diagnostic Info</span>
  )}
</button>

<p className="text-xs text-gray-400 mt-2 text-center">
  Paste this into your email to support. It contains no passwords or patient data.
</p>
```

If clipboard API fails (some environments block it), show a `<textarea>` with the report text pre-selected so the user can manually Ctrl+A and copy.

---

## PART 2 — "Send Crash Report" Button

### What it does
When a user clicks "Send Crash Report," it POSTs their diagnostic info plus any error details to a lightweight server you control. You see it in a simple dashboard or email. No remote access to their machine — just structured data you can read.

### Stage 2.1 — Crash report server options (choose one)

**Option A: Email via EmailJS (simplest, free, no server needed)**
- Sign up at [emailjs.com](https://www.emailjs.com) (free tier: 200 emails/month)
- Create a service connected to your `pharmacypro.support@gmail.com`
- Create an email template with variables for the diagnostic data
- Call EmailJS SDK directly from the frontend — no backend needed
- Emails arrive in your Gmail inbox with structured data

**Option B: Simple backend endpoint + email forwarding**
- Add `POST /api/v1/crash-report` to the FastAPI backend (may already exist — check first)
- Backend logs the report to a file AND emails you via SMTP
- The backend is local (not internet-accessible) so this only works if the backend is exposed — for a Tauri desktop app, this means the report stays local unless you add an external call

**Option C: Direct POST to a free hosted endpoint (recommended)**
- Deploy a tiny FastAPI or Flask app on [Render.com](https://render.com) (free tier)
- Your crash report endpoint URL: `https://pharmacysuite-support.onrender.com/crash-report`
- The frontend POSTs directly to this URL from the Tauri app
- Your server stores reports in a SQLite database and emails you for each one
- You log into your server's dashboard to see all reports

**Recommendation: Option A for now (fastest to set up, zero cost, zero server maintenance), Option C for scale later.**

### Stage 2.2 — Frontend: crash report submission

In `app/dashboard/support/page.tsx`:

```typescript
const CRASH_REPORT_URL = process.env.NEXT_PUBLIC_CRASH_REPORT_URL ?? null;
// Set this in .env: NEXT_PUBLIC_CRASH_REPORT_URL=https://your-server.onrender.com/crash-report
// If null, the button is hidden and only the copy-to-clipboard option shows

const [sending, setSending] = useState(false);
const [sent, setSent] = useState(false);
const [sendError, setSendError] = useState<string | null>(null);

const handleSendCrashReport = async () => {
  if (!CRASH_REPORT_URL) return;
  setSending(true);
  setSendError(null);
  
  try {
    const report = await generateDiagnosticReport();
    const user = useAuthStore.getState().user;
    
    await fetch(CRASH_REPORT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        report_text: report,
        app_version: "1.0.0",
        pharmacy_name: pharmacyName,
        user_id: user?.id,
        submitted_at: new Date().toISOString(),
      }),
    });
    
    setSent(true);
  } catch (err) {
    setSendError("Could not send report. Please use 'Copy Diagnostic Info' and email us instead.");
  } finally {
    setSending(false);
  }
};
```

Button JSX (only show if CRASH_REPORT_URL is configured):
```tsx
{CRASH_REPORT_URL && (
  <button
    onClick={handleSendCrashReport}
    disabled={sending || sent}
    className="w-full py-2 px-4 rounded-lg bg-blue-600 text-white
               hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 justify-center"
  >
    {sending ? "Sending..." : sent ? "✓ Report Sent" : "📤 Send Crash Report"}
  </button>
)}
{sent && (
  <p className="text-sm text-green-600 text-center mt-1">
    Report received. We'll respond within 24 hours at {supportEmail}.
  </p>
)}
{sendError && (
  <p className="text-sm text-red-500 text-center mt-1">{sendError}</p>
)}
```

### Stage 2.3 — Tauri CSP update

If you add an external crash report URL, you must add it to the Content Security Policy in `src-tauri/tauri.conf.json`:

```json
"csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:3000 http://127.0.0.1:8000 https://your-server.onrender.com; ..."
```

Without this, Tauri will block the external request and the send will fail silently.

### Stage 2.4 — Privacy note (required)

Add a one-line privacy notice below the Send button:
```tsx
<p className="text-xs text-gray-400 mt-2 text-center">
  Reports contain app version, error logs, and pharmacy settings.
  No patient records, prescriptions, or passwords are included.
</p>
```

This is important for trust and is required if you ever publish to the Microsoft Store.

---

## PART 3 — Final Support Tab Layout

After both features are added, the Support tab should look like this (top to bottom):

```
┌─────────────────────────────────────────┐
│  [App Logo]                             │
│  PharmacySuite Support                  │
│  "For feature requests or issues..."    │
│                                         │
│  Support Team: PharmacySuite Support   │
│  Email: pharmacypro.support@gmail.com  │
│  [mailto link]                          │
│                                         │
│  ──────────────────────────────────    │
│  Having a problem?                      │
│                                         │
│  [📋 Copy Diagnostic Info]              │
│  Paste into your support email          │
│                                         │
│  [📤 Send Crash Report]   ← only if    │
│                              configured │
│  No patient data is included            │
│                                         │
│  ──────────────────────────────────    │
│  Response time: within 24 hours        │
└─────────────────────────────────────────┘
```

---

## PART 4 — Verify

After implementing:

1. Open the Support tab — confirm support email is displayed as a clickable mailto link
2. Click "Copy Diagnostic Info" — paste into a text editor and verify the report contains app version, pharmacy name, user info, and recent errors (or "no recent errors")
3. Verify the report contains NO patient names, prescription data, or passwords
4. If crash report URL is configured: click "Send Crash Report" and verify it arrives at your server/email
5. Trigger a deliberate error (navigate to a non-existent API endpoint) — then open Support tab and copy diagnostics — verify the error appears in the "Recent Errors" section

---

## Build

```
cd "E:\my progam pharmacy"
npm run tauri build
```

If adding external crash report URL, update CSP in `tauri.conf.json` before building.
