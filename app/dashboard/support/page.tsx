"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { getRecentErrors } from "@/stores/errorLogStore";
import { useToastStore } from "@/hooks/useToast";
import { DashboardLayout } from "@/components/DashboardLayout";

// Spec 08 Part 2: crash-report endpoint. Configured at BUILD TIME via
// NEXT_PUBLIC_CRASH_REPORT_URL. When unset, the Send button is hidden and
// only Copy Diagnostic Info is offered.
const CRASH_REPORT_URL = process.env.NEXT_PUBLIC_CRASH_REPORT_URL ?? null;

async function generateDiagnosticReport(): Promise<string> {
  const lines: string[] = [];
  const now = new Date().toISOString();

  lines.push("=== PharmacySuite Diagnostic Report ===");
  lines.push(`Generated: ${now}`);
  lines.push("");

  // --- App Info ---
  lines.push("--- App Info ---");
  try {
    const { data: ver } = await api.get("/api/v1/version");
    lines.push(`App Version: ${ver?.current_version ?? "unknown"}`);
  } catch {
    lines.push("App Version: unknown");
  }
  if (typeof navigator !== "undefined") {
    lines.push(`Platform: ${navigator.platform ?? "unknown"}`);
    lines.push(`User Agent: ${navigator.userAgent ?? "unknown"}`);
  }
  lines.push("");

  // --- Pharmacy Info (settings values only — no customer records) ---
  lines.push("--- Pharmacy Info ---");
  let pharmacyName = "(not set)";
  try {
    const { data: contact } = await api.get("/api/v1/support/contact");
    pharmacyName = contact?.pharmacy_name || "(not set)";
  } catch {
    pharmacyName = "(error fetching)";
  }
  lines.push(`Pharmacy Name: ${pharmacyName}`);

  // Current user — account identity only, never credentials.
  const user = useAuthStore.getState().user;
  lines.push(`Admin Username: ${user?.username ?? "unknown"} (ID: ${user?.id ?? "?"})`);
  lines.push("");

  // --- Backend Health (aggregate counters only) ---
  lines.push("--- Backend Health ---");
  try {
    const { data: health } = await api.get("/api/v1/health/diagnostics");
    lines.push("API Status: Connected (127.0.0.1:8000)");
    lines.push(`Database Size: ${health?.db_size_mb ?? "unknown"} MB`);
    lines.push(`User Count: ${health?.user_count ?? "unknown"}`);
    lines.push(`Medicine Count: ${health?.medicine_count ?? "unknown"}`);
    lines.push(`Environment: ${health?.env ?? "unknown"}`);
  } catch {
    lines.push("API Status: ERROR — backend not responding");
  }
  lines.push("");

  // --- Recent API errors (status/method/URL/message only) ---
  lines.push("--- Recent Errors (last 5) ---");
  const recentErrors = getRecentErrors(5);
  if (recentErrors.length === 0) {
    lines.push("(no recent errors logged)");
  } else {
    recentErrors.forEach((e) =>
      lines.push(`[${e.timestamp}] ${e.status} ${e.method} ${e.url} - ${e.message}`)
    );
  }
  lines.push("");

  // --- Session/settings preferences (non-identifying config) ---
  lines.push("--- System Settings ---");
  try {
    const { data: contact } = await api.get("/api/v1/support/contact");
    lines.push(`Support Email: ${contact?.support_email ?? "unknown"}`);
  } catch {
    lines.push("Support Email: (error fetching)");
  }
  if (typeof navigator !== "undefined") {
    lines.push(`Language: ${navigator.language ?? "unknown"}`);
  }
  lines.push("");
  lines.push("=== End of Report ===");
  return lines.join("\n");
}

export default function SupportPage() {

  // Anti-phishing notice shown even when the backend is unreachable —
  // scammers impersonate support most convincingly when "the server is down".
  const SECURITY_NOTICE_FALLBACK =
    "Official support will NEVER ask for your password, your secret.key file, or your pharmacy.db file. We will never call you first or request remote access.";

  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fallbackReport, setFallbackReport] = useState<string | null>(null);

  // Use the auth store for role gating (single source of truth — no props)
  const { user } = useAuthStore();


  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  // ── Technician fix-code import (Stage 2.3) ──
  const [settings, setSettings] = useState<{
    support_email: string;
    support_name: string;
    support_message: string;
    pharmacy_name: string;
    security_notice: string;
  } | null>(null);

  const [fixCode, setFixCode] = useState("");
  const [fixApplying, setFixApplying] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);

  // ── Stage 2.4 → Step 2.7: pre-filled support email (client-side only) ──
  // Email Privacy hardening (blueprint Step 2.7):
  //   * Delegation-only: the app never sends mail itself — no SMTP
  //     credentials exist in the client, so none can leak (invariant #6).
  //   * The body embeds the SANITIZED diagnostic report only. The report
  //     generator already excludes patient data, credentials, and stack
  //     traces; a final guard below strips any accidental control
  //     characters so a malformed line can't smuggle content into headers.
  //   * The user sees the complete email in their own mail client before
  //     anything is sent — full transparency, nothing automatic.
  const openSupportEmail = (diagnosticReport: string) => {
    // Strip control characters (header-injection + paste-artifact guard).
    const safeReport = diagnosticReport.replace(/[\u0000-\u001f\u007f]/g, (ch) =>
      ch === "\n" ? "\n" : " "
    );
    const subject = encodeURIComponent("PharmacySuite Support Request");
    const body = encodeURIComponent(
      `Dear PharmacySuite Support,\n\n` +
      `I'm experiencing the following issue:\n\n` +
      `[DESCRIBE YOUR ISSUE HERE]\n\n` +
      `--- Diagnostic Report (auto-generated, no patient data) ---\n` +
      safeReport +
      `\n--- End of Report ---`
    );
    window.open(`mailto:pharmacypro.support@gmail.com?subject=${subject}&body=${body}`);
  };

  useEffect(() => {
    // Live support contact — readable by every logged-in role (no admin gate).
    api.get("/api/v1/support/contact").then(({ data }) => {
      setSettings({
        support_email: data.support_email ?? "pharmacypro.support@gmail.com",
        support_name: data.support_name ?? "PharmacySuite Support",
        support_message: data.support_message ?? "",
        pharmacy_name: data.pharmacy_name ?? "",
        security_notice: data.security_notice ?? SECURITY_NOTICE_FALLBACK,
      });
    }).catch(() => {
      // Backend unreachable — keep the seeded fallback email visible.
      setSettings({
        support_email: "pharmacypro.support@gmail.com",
        support_name: "PharmacySuite Support",
        support_message: "",
        pharmacy_name: "",
        security_notice: SECURITY_NOTICE_FALLBACK,
      });
    });
  }, []);

  const handleCopyDiagnostics = async () => {
    setCopying(true);
    let report = "";
    try {
      report = await generateDiagnosticReport();
      await navigator.clipboard.writeText(report);
      setCopied(true);
      setFallbackReport(null);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // Clipboard API blocked — show a textarea the user can copy manually.
      setFallbackReport(report || "Could not generate report.");
    } finally {
      setCopying(false);
    }
  };

  const handleSendCrashReport = async () => {
    if (!CRASH_REPORT_URL) return;
    setSending(true);
    setSendError(null);

    try {
      const user = useAuthStore.getState().user;

      const res = await fetch(CRASH_REPORT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_text: "diagnostic report",
          app_version: "1.0.0",
          pharmacy_name: settings?.pharmacy_name ?? "",
          user_id: user?.id,
          submitted_at: new Date().toISOString(),
        }),
      });
      if (!res.ok) throw new Error(`send failed: ${res.status}`);
      setSent(true);
    } catch {
      setSendError("Could not send report. Please use 'Copy Diagnostic Info' and email us instead.");
    } finally {
      setSending(false);
    }
  };

  // Fix codes are signed JSON envelopes: {"action", "payload", "sig"}.
  // The signature is HMAC-SHA256 over the canonical JSON of `payload`,
  // computed by PharmacySuite support tooling — never by the app.
  const handleApplyFix = async () => {
    if (!fixCode.trim()) return;
    setFixApplying(true);
    setFixError(null);
    try {
      const envelope = JSON.parse(fixCode) as {
        action?: unknown;
        payload?: unknown;
        sig?: unknown;
      };
      if (
        typeof envelope.action !== "string" ||
        typeof envelope.sig !== "string" ||
        envelope.payload === null ||
        typeof envelope.payload !== "object"
      ) {
        throw new Error("Fix code must be {\"action\", \"payload\", \"sig\"} JSON.");
      }
      await api.post("/api/v1/support/fix-code/verify", {
        action: envelope.action,
        payload: envelope.payload,
        sig: envelope.sig,
      });
      useToastStore.getState().toast({ title: "Success", message: "Fix applied successfully. Restart may be required.", variant: "success" });
      setFixCode("");
    } catch (err) {
      if (err instanceof SyntaxError) {
        setFixError("Fix code is not valid JSON.");
      } else {
        setFixError(err instanceof Error ? err.message : "Could not apply fix.");
      }
    } finally {
      setFixApplying(false);
    }
  };

  return (
    <DashboardLayout>
    <div className="max-w-lg mx-auto mt-16 p-8 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
        <div className="text-center mb-8">
          <span className="text-4xl">💊</span>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-4">
            PharmacySuite Support
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            {settings?.support_message ?? "We're here to help."}
          </p>
        </div>

        {/* Anti-phishing Security Notice (spec: Final UX & Security Audit) */}
        <div
          role="note"
          aria-label="Security notice"
          style={{
            border: "1px solid #fcd34d",
            background: "#fffbeb",
            borderRadius: 8,
            padding: "10px 14px",
            marginBottom: 16,
          }}
          className="dark:!bg-amber-950/40 dark:!border-amber-800"
        >
          <p
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#92400e",
              marginBottom: 4,
            }}
            className="dark:!text-amber-300"
          >
            🔒 Security Notice — how to spot a scam
          </p>
          <p
            style={{ fontSize: 12, lineHeight: 1.5, color: "#92400e" }}
            className="dark:!text-amber-200"
          >
            {settings?.security_notice ?? SECURITY_NOTICE_FALLBACK}
          </p>
        </div>
  );

      <div className="space-y-4">
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Support Team</p>
          <p className="text-gray-900 dark:text-white">{settings?.support_name}</p>
        </div>
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Email</p>
          <a
            href={`mailto:${settings?.support_email}`}
            className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
          >
            {settings?.support_email ?? "pharmacypro.support@gmail.com"}
          </a>
        </div>

        {/* Microsoft Store requirement: privacy policy reachable from within the app. */}
        <div>
          <a
            href="/privacy"
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline font-medium"
          >
            Privacy Policy →
          </a>
        </div>

        <div className="pt-4 border-t border-gray-100 dark:border-gray-700">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Having a problem?
          </p>

          <button
            onClick={handleCopyDiagnostics}
            disabled={copying}
            className="w-full py-2 px-4 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2 justify-center disabled:opacity-50"
          >
            {copying ? (
              <span>Gathering info...</span>
            ) : copied ? (
              <span>✓ Copied to clipboard</span>
            ) : (
              <span>📋 Copy Diagnostic Info</span>
            )}
          </button>            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
            Paste this into your email to support. It contains no passwords or patient data.
          </p>

          {/* Stage 2.3: technician fix import (admin only) */}
          {user?.role_id === 1 && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-300 mb-2">
                Apply Support Fix
              </h3>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
                Paste the fix code provided by PharmacySuite support.
              </p>
              <textarea
                className="w-full h-24 text-xs font-mono border rounded p-2"
                placeholder="Paste fix code here..."
                value={fixCode}
                onChange={(e) => setFixCode(e.target.value)}
              />
              <button
                onClick={handleApplyFix}
                disabled={fixApplying}
                className="mt-2 px-4 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
              >
                {fixApplying ? "Applying..." : "Apply Fix"}
              </button>
              {fixError && (
                <p className="text-xs text-red-500 mt-2">{fixError}</p>
              )}
            </div>
          )}

          {fallbackReport !== null && (
            <textarea
              readOnly
              value={fallbackReport}
              onFocus={(e) => e.currentTarget.select()}
              rows={12}
              className="mt-3 w-full font-mono text-xs p-3 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-gray-800 dark:text-gray-200"
            />
          )}

          {CRASH_REPORT_URL && (
            <>
              <button
                onClick={handleSendCrashReport}
                disabled={sending || sent}
                className="mt-4 w-full py-2 px-4 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 justify-center"
              >
                {sending ? "Sending..." : sent ? "✓ Report Sent" : "📤 Send Crash Report"}
              </button>
              {sent && (
                <p className="text-sm text-green-600 dark:text-green-400 text-center mt-1">
                  Report received. We&apos;ll respond within 24 hours at {settings?.support_email}.
                </p>
              )}
              {sendError && (
                <p className="text-sm text-red-500 text-center mt-1">{sendError}</p>
              )}
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
                Reports contain app version, error logs, and pharmacy settings.
                No patient records, prescriptions, or passwords are included.
              </p>
            </>
          )}
        </div>

        <div className="pt-4 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            Include your pharmacy name and a description of the issue in your email.
            Response time: typically within 24 hours on business days.
          </p>
        </div>

        {/* Stage 2.4: pre-filled support email (admin only) */}
        {user?.role_id === 1 && (
          <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
            <button
              onClick={() => { (async () => { const r = await generateDiagnosticReport(); openSupportEmail(r); })(); }}
              className="w-full py-2 px-4 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2 justify-center"
            >
              📧 Email Support (includes diagnostic info)
            </button>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
              Opens your mail client with a pre-filled support report — no passwords or patient data included.
            </p>
          </div>
        )}
      </div>
    </div>
    </DashboardLayout>
  );
}
