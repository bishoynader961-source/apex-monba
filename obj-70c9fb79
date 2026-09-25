"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { listSettings, updateSetting } from "@/lib/api/settings";
import { changePassword } from "@/lib/api/auth";
import { useToast } from "@/hooks/useToast";
import type { SystemSettingRead } from "@/types/contracts";
import { Plug, Plus, X, Check, Loader2, Building2, Receipt, ShieldAlert, Mail, Clock, Globe, MessageSquare, Server, Cpu, Wifi, WifiOff, Save, Sun, Moon, Monitor } from "lucide-react";
import { api } from "@/lib/api";
import { useUiStore } from "@/stores/uiStore";
import { UpdateChecker } from "@/components/UpdateChecker";

interface Integration {
  id: string;
  provider_name: string;
  is_active: number;
  base_url: string | null;
  created_at: string | null;
}

const SECTION_STYLE = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
} as const;

const INPUT_STYLE = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid var(--border)",
  borderRadius: 6,
  fontSize: 14,
  background: "var(--bg-input)",
  color: "var(--fg)",
  boxSizing: "border-box" as const,
};

const LABEL_STYLE = {
  display: "block",
  fontSize: 13,
  fontWeight: 500,
  color: "var(--fg-muted)",
  marginBottom: 4,
};

export default function SettingsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("inventory.read");
  const canWrite = useCan("inventory.write");
  const canManage = useCan("settings.manage");
  const { t } = useI18n();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role_id === 1;

  const [settings, setSettings] = useState<SystemSettingRead[]>([]);
  const brightness = useUiStore((s) => s.brightness);
  const setBrightness = useUiStore((s) => s.setBrightness);
  const resetBrightness = useUiStore((s) => s.resetBrightness);
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [showAddIntegration, setShowAddIntegration] = useState(false);
  const [integForm, setIntegForm] = useState({ provider_name: "", api_key: "", base_url: "" });
  const [integSaving, setIntegSaving] = useState(false);

  // Business Info form
  const [bizForm, setBizForm] = useState({
    pharmacy_name: "",
    pharmacy_address: "",
    pharmacy_phone: "",
    pharmacy_npi: "",
    pharmacy_dea: "",
    pharmacy_license: "",
  });

  // Tax form
  const [taxForm, setTaxForm] = useState({
    tax_rate: "0",
    tax_label: "Tax",
    tax_exempt_enabled: "true",
  });

  // Drug interaction form
  const [ddiForm, setDdiForm] = useState({
    ddi_alerts_enabled: "true",
    ddi_severity_threshold: "moderate",
  });

  // Email form
  const [emailForm, setEmailForm] = useState({
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    smtp_from: "",
  });

  // Session/Alert form ("never" is stored as the string "never")
  const [sessionForm, setSessionForm] = useState({
    session_idle_minutes: "15",
    session_absolute_minutes: "480",
    alert_check_enabled: "true",
    alert_expiry_critical_days: "30",
    alert_expiry_warning_days: "90",
  });

  // Support Contact form (admin only)
  const [supportForm, setSupportForm] = useState({
    support_name: "",
    support_email: "",
    support_message: "",
  });

  // Account form (password change)
  const [accountForm, setAccountForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmNewPassword: "",
  });
  const [accountSaving, setAccountSaving] = useState(false);
  const [accountError, setAccountError] = useState("");
  const [accountSuccess, setAccountSuccess] = useState(false);

  const { toast } = useToast();

  // Region form
  const [regionCode, setRegionCode] = useState("US");
  const [regionInfo, setRegionInfo] = useState<{
    currency: string; currency_symbol: string; date_format: string;
    tax_label: string; default_tax_rate: number;
  } | null>(null);

  // Terminal Mode form (SPEC 07)
  const [terminalMode, setTerminalMode] = useState<"main" | "client">("main");
  const [serverIp, setServerIp] = useState("");

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSettings();
      setSettings(data);

      // Populate forms from loaded settings
      const map: Record<string, string> = {};
      data.forEach((s) => { map[s.key] = s.value ?? ""; });

      setBizForm({
        pharmacy_name: map.pharmacy_name ?? "",
        pharmacy_address: map.pharmacy_address ?? "",
        pharmacy_phone: map.pharmacy_phone ?? "",
        pharmacy_npi: map.pharmacy_npi ?? "",
        pharmacy_dea: map.pharmacy_dea ?? "",
        pharmacy_license: map.pharmacy_license ?? "",
      });
      setTaxForm({
        tax_rate: map.tax_rate ?? "0",
        tax_label: map.tax_label ?? "Tax",
        tax_exempt_enabled: map.tax_exempt_enabled ?? "true",
      });
      setDdiForm({
        ddi_alerts_enabled: map.ddi_alerts_enabled ?? "true",
        ddi_severity_threshold: map.ddi_severity_threshold ?? "moderate",
      });
      setEmailForm({
        smtp_host: map.smtp_host ?? "",
        smtp_port: map.smtp_port ?? "587",
        smtp_user: map.smtp_user ?? "",
        smtp_password: map.smtp_password ?? "",
        smtp_from: map.smtp_from ?? "",
      });
      const toInternal = (value: string | undefined): string => {
        if (value === "never" || value === undefined) return "never";
        const n = parseInt(value, 10);
        return isNaN(n) || n <= 0 ? "never" : String(n);
      };

      setSessionForm({
        session_idle_minutes: toInternal(map.session_idle_minutes),
        session_absolute_minutes: toInternal(map.session_absolute_minutes),
        alert_check_enabled: map.alert_check_enabled ?? "true",
        alert_expiry_critical_days: map.alert_expiry_critical_days ?? "30",
        alert_expiry_warning_days: map.alert_expiry_warning_days ?? "90",
      });
      setSupportForm({
        support_name: map.support_name ?? "",
        support_email: map.support_email ?? "",
        support_message: map.support_message ?? "",
      });
      // Terminal Mode (SPEC 07)
      setTerminalMode((map.terminal_mode as "main" | "client") ?? "main");
      setServerIp(map.server_ip ?? "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIntegrations = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/integrations");
      setIntegrations(res.data);
    } catch {
      // silently fail
    }
  }, []);

  const loadRegion = useCallback(async () => {
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch("/api/v1/region/detect", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRegionCode(data.code);
        setRegionInfo({
          currency: data.currency,
          currency_symbol: data.currency_symbol,
          date_format: data.date_format,
          tax_label: data.tax_label,
          default_tax_rate: data.default_tax_rate,
        });
      }
    } catch {
      // silently fail
    }
  }, []);

  const handleRegionChange = async (code: string) => {
    setRegionCode(code);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`/api/v1/region/${code}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRegionInfo({
          currency: data.currency,
          currency_symbol: data.currency_symbol,
          date_format: data.date_format,
          tax_label: data.tax_label,
          default_tax_rate: data.default_tax_rate,
        });
        localStorage.setItem("pharmacy_region", JSON.stringify(data));
      }
    } catch {
      // silently fail
    }
  };

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    loadSettings();
    loadIntegrations();
    loadRegion();
  }, [canRead, loadSettings, loadIntegrations]);

  async function saveSection(entries: [string, string][]) {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      for (const [key, value] of entries) {
        await updateSetting(key, value);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      await loadSettings();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function saveSessionSettings() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateSetting("session_idle_minutes", sessionForm.session_idle_minutes);
      await updateSetting("session_absolute_minutes", sessionForm.session_absolute_minutes);
      await updateSetting("alert_check_enabled", sessionForm.alert_check_enabled);
      await updateSetting("alert_expiry_critical_days", sessionForm.alert_expiry_critical_days);
      await updateSetting("alert_expiry_warning_days", sessionForm.alert_expiry_warning_days);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      toast({ title: "Success", message: "Session settings saved" });
      await loadSettings();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save";
      setError(msg);
      toast({ title: "Error", message: msg, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  async function saveSupportSettings() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateSetting("support_name", supportForm.support_name);
      await updateSetting("support_email", supportForm.support_email);
      await updateSetting("support_message", supportForm.support_message);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      toast({ title: "Success", message: "Support settings saved" });
      await loadSettings();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save";
      setError(msg);
      toast({ title: "Error", message: msg, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  async function handleAddIntegration() {
    if (!integForm.provider_name || !integForm.api_key) return;
    setIntegSaving(true);
    try {
      await api.post("/api/v1/integrations", integForm);
      setShowAddIntegration(false);
      setIntegForm({ provider_name: "", api_key: "", base_url: "" });
      await loadIntegrations();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save integration");
    } finally {
      setIntegSaving(false);
    }
  }

  return (
    <DashboardLayout>
      <RouteGuard permission="settings.read">
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", marginBottom: 20 }}>{t("settings.title")}</h1>

      {error && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--danger)", color: "var(--danger)", padding: "10px 16px", borderRadius: 8, marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{ color: "var(--danger)", background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
        </div>
      )}

      {saved && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--success)", color: "var(--success)", padding: "10px 16px", borderRadius: 8, marginBottom: 16 }}>
          Settings saved successfully.
        </div>
      )}

      {loading ? (
        <p style={{ color: "var(--fg-muted)" }}>{t("settings.loading")}</p>
      ) : (
        <>
          {/* ── Appearance (Theme + Brightness) ─────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Sun size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Appearance</h2>
            </div>

            {/* ── Theme selector ───────────────────────────────────────────── */}
            <div style={{ marginBottom: 20 }}>
              <p style={{ ...LABEL_STYLE, marginBottom: 8 }}>Theme</p>
              <div
                id="settings-theme-toggle"
                role="group"
                aria-label="Select theme"
                style={{ display: "inline-flex", gap: 8 }}
              >
                {(
                  [
                    { value: "light",  label: "Light",  Icon: Sun },
                    { value: "dark",   label: "Dark",   Icon: Moon },
                    { value: "system", label: "System", Icon: Monitor },
                  ] as const
                ).map(({ value, label, Icon }) => (
                  <button
                    key={value}
                    id={`theme-btn-${value}`}
                    type="button"
                    onClick={() => setTheme(value)}
                    aria-pressed={theme === value}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "7px 16px",
                      borderRadius: 6,
                      border: theme === value ? "2px solid var(--primary)" : "1px solid var(--border)",
                      background: theme === value ? "var(--primary)" : "var(--bg-input, var(--bg-secondary))",
                      color: theme === value ? "#fff" : "var(--fg)",
                      fontSize: 13, fontWeight: 500, cursor: "pointer",
                      transition: "all 0.15s",
                    }}
                  >
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
              </div>
              <p style={{ marginTop: 6, fontSize: 11, color: "var(--fg-muted)" }}>
                &quot;System&quot; follows your OS preference and switches automatically.
              </p>
            </div>

            {/* ── Brightness slider ─────────────────────────────────────────── */}
            <div style={{ maxWidth: 420 }}>
              <label style={LABEL_STYLE} htmlFor="brightness-slider">
                Brightness — {Math.round(brightness * 100)}%
              </label>
              <input
                id="brightness-slider"
                type="range"
                min={0.8}
                max={1.2}
                step={0.02}
                value={brightness}
                onChange={(e) => setBrightness(Number(e.target.value))}
                style={{ width: "100%", accentColor: "var(--primary)" }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--fg-muted)", marginTop: 2 }}>
                <span>Darker (80%)</span>
                <button
                  type="button"
                  onClick={() => resetBrightness()}
                  style={{ background: "none", border: "none", color: "var(--primary)", cursor: "pointer", fontSize: 11, textDecoration: "underline" }}
                >
                  Reset to 100%
                </button>
                <span>Brighter (120%)</span>
              </div>
            </div>

            {/* ── App Updates (desktop builds only; renders nothing in browser) ── */}
            <div style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 12 }}>
              <p style={{ ...LABEL_STYLE, marginBottom: 4 }}>App Updates</p>
              <UpdateChecker />
            </div>
          </div>

          {/* ── Region Configuration ───────────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Globe size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Region & Currency</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-1">Region</label>
                <select id="page-field-1"
                  style={INPUT_STYLE}
                  value={regionCode}
                  onChange={(e) => void handleRegionChange(e.target.value)}
                >
                  <option value="US">United States (USD)</option>
                  <option value="GB">United Kingdom (GBP)</option>
                  <option value="DE">Germany (EUR)</option>
                  <option value="EG">Egypt (EGP)</option>
                </select>
              </div>
              {regionInfo && (
                <>
                  <div>
                    <label style={LABEL_STYLE} htmlFor="page-field-2">Currency</label>
                    <input id="page-field-2" style={INPUT_STYLE} value={`${regionInfo.currency_symbol} ${regionInfo.currency}`} readOnly />
                  </div>
                  <div>
                    <label style={LABEL_STYLE} htmlFor="page-field-3">Date Format</label>
                    <input id="page-field-3" style={INPUT_STYLE} value={regionInfo.date_format} readOnly />
                  </div>
                  <div>
                    <label style={LABEL_STYLE} htmlFor="page-field-4">Tax Label</label>
                    <input id="page-field-4" style={INPUT_STYLE} value={`${regionInfo.tax_label} (${(regionInfo.default_tax_rate * 100).toFixed(0)}%)`} readOnly />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── Terminal Mode Configuration (SPEC 07) ───────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Server size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Terminal Mode</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-5">Mode</label>
                <select id="page-field-5" style={INPUT_STYLE} value={terminalMode} onChange={(e) => setTerminalMode(e.target.value as "main" | "client")}>
                  <option value="main">Main Server (Hosts DB & API)</option>
                  <option value="client">Client Terminal (Connects to Main Server)</option>
                </select>
              </div>
              {terminalMode === "client" && (
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-6">Main Server LAN IP</label>
                  <input id="page-field-6" style={INPUT_STYLE} type="text" placeholder="e.g. 192.168.1.100" value={serverIp} onChange={(e) => setServerIp(e.target.value)} />
                </div>
              )}
            </div>
            <button
              onClick={async () => {
                setSaving(true);
                setError(null);
                try {
                  await updateSetting("terminal_mode", terminalMode);
                  if (terminalMode === "client" && serverIp) {
                    await updateSetting("server_ip", serverIp);
                    // Also set localStorage for API interceptor
                    if (typeof window !== "undefined") {
                      localStorage.setItem("db_setup_configured", "client");
                      localStorage.setItem("server_ip", serverIp);
                    }
                  } else if (terminalMode === "main") {
                    // Clear client mode settings
                    if (typeof window !== "undefined") {
                      localStorage.removeItem("db_setup_configured");
                      localStorage.removeItem("server_ip");
                    }
                  }
                  setSaved(true);
                  setTimeout(() => setSaved(false), 2000);
                  toast({ title: "Success", message: "Terminal mode saved. Restart the app for changes to take effect." });
                } catch (e: unknown) {
                  setError(e instanceof Error ? e.message : "Failed to save");
                  toast({ title: "Error", message: e instanceof Error ? e.message : "Failed to save", variant: "destructive" });
                } finally {
                  setSaving(false);
                }
              }}
              disabled={saving}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving..." : t("common.save")}
            </button>
            <p style={{ marginTop: 8, fontSize: 12, color: "var(--fg-muted)" }}>
              Main Server: Runs local FastAPI backend and SQLite/PostgreSQL database. Other terminals connect to this machine.
            </p>
            <p style={{ marginTop: 4, fontSize: 12, color: "var(--fg-muted)" }}>
              Client Terminal: Connects to Main Server over LAN. Does not run local backend.
            </p>
          </div>

          {/* ── Business Information ──────────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Building2 size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Business Information</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-7">Pharmacy Name</label>
                <input id="page-field-7" style={INPUT_STYLE} value={bizForm.pharmacy_name} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_name: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-8">Phone</label>
                <input id="page-field-8" style={INPUT_STYLE} value={bizForm.pharmacy_phone} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_phone: e.target.value }))} />
              </div>
              <div style={{ gridColumn: "span 2" }}>
                <label style={LABEL_STYLE} htmlFor="page-field-9">Address</label>
                <input id="page-field-9" style={INPUT_STYLE} value={bizForm.pharmacy_address} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_address: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-10">NPI Number</label>
                <input id="page-field-10" style={INPUT_STYLE} value={bizForm.pharmacy_npi} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_npi: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-11">DEA Number</label>
                <input id="page-field-11" style={INPUT_STYLE} value={bizForm.pharmacy_dea} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_dea: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-12">License Number</label>
                <input id="page-field-12" style={INPUT_STYLE} value={bizForm.pharmacy_license} onChange={(e) => setBizForm((f) => ({ ...f, pharmacy_license: e.target.value }))} />
              </div>
            </div>
            <button
              onClick={() => void saveSection(Object.entries(bizForm))}
              disabled={saving}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving..." : t("common.save")}
            </button>
          </div>

          {/* ── Account (Password Change) ───────────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <ShieldAlert size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>{t("settings.account.heading")}</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-13">{t("settings.account.currentPassword")}</label>
                <input id="page-field-13"
                  type="password"
                  style={INPUT_STYLE}
                  value={accountForm.currentPassword}
                  onChange={(e) => setAccountForm((f) => ({ ...f, currentPassword: e.target.value }))}
                  disabled={accountSaving}
                />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-14">{t("settings.account.newPassword")}</label>
                <input id="page-field-14"
                  type="password"
                  style={INPUT_STYLE}
                  value={accountForm.newPassword}
                  onChange={(e) => setAccountForm((f) => ({ ...f, newPassword: e.target.value }))}
                  disabled={accountSaving}
                  minLength={8}
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400" style={{ marginTop: 4, fontSize: 12, color: "var(--fg-muted)" }}>
                  {t("settings.account.passwordMinLength")}
                </p>
              </div>
              <div style={{ gridColumn: "span 2" }}>
                <label style={LABEL_STYLE} htmlFor="page-field-15">{t("settings.account.confirmNewPassword")}</label>
                <input id="page-field-15"
                  type="password"
                  style={INPUT_STYLE}
                  value={accountForm.confirmNewPassword}
                  onChange={(e) => setAccountForm((f) => ({ ...f, confirmNewPassword: e.target.value }))}
                  disabled={accountSaving}
                />
                {accountForm.confirmNewPassword && accountForm.newPassword !== accountForm.confirmNewPassword && (
                  <p style={{ marginTop: 4, fontSize: 12, color: "var(--danger)" }}>
                    {t("settings.account.passwordMismatch")}
                  </p>
                )}
              </div>
            </div>
            {accountError && (
              <div style={{ marginTop: 12, padding: "8px 12px", background: "var(--danger)", color: "var(--danger-fg, #fff)", borderRadius: 6, fontSize: 13 }}>
                {accountError}
              </div>
            )}
            {accountSuccess && (
              <div style={{ marginTop: 12, padding: "8px 12px", background: "var(--success)", color: "var(--success-fg, #fff)", borderRadius: 6, fontSize: 13 }}>
                {t("settings.account.success")}
              </div>
            )}
            <button
              onClick={async () => {
                if (!accountForm.currentPassword || !accountForm.newPassword || !accountForm.confirmNewPassword) return;
                if (accountForm.newPassword !== accountForm.confirmNewPassword) return;
                if (accountForm.newPassword.length < 8) return;
                setAccountSaving(true);
                setAccountError("");
                setAccountSuccess(false);
                try {
                  await changePassword({
                    current_password: accountForm.currentPassword,
                    new_password: accountForm.newPassword,
                  });
                  setAccountSuccess(true);
                  setAccountForm({ currentPassword: "", newPassword: "", confirmNewPassword: "" });
                  toast({ title: t("settings.account.success"), message: "" });
                } catch (e: unknown) {
                  const msg = e instanceof Error ? e.message : t("settings.account.error");
                  setAccountError(msg);
                  toast({ title: t("settings.account.error"), message: msg, variant: "destructive" });
                } finally {
                  setAccountSaving(false);
                }
              }}
              disabled={accountSaving || !accountForm.currentPassword || !accountForm.newPassword || !accountForm.confirmNewPassword || accountForm.newPassword !== accountForm.confirmNewPassword || accountForm.newPassword.length < 8}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: accountSaving ? "default" : "pointer", opacity: accountSaving ? 0.6 : 1 }}
            >
              {accountSaving ? t("settings.account.updating") : t("settings.account.updatePassword")}
            </button>
          </div>

          {/* ── Tax Configuration ─────────────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Receipt size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Tax Configuration</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-16">Tax Rate (%)</label>
                <input id="page-field-16" style={INPUT_STYLE} type="number" step="0.01" value={taxForm.tax_rate} onChange={(e) => setTaxForm((f) => ({ ...f, tax_rate: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-17">Tax Label</label>
                <input id="page-field-17" style={INPUT_STYLE} value={taxForm.tax_label} onChange={(e) => setTaxForm((f) => ({ ...f, tax_label: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-18">Tax-Exempt Allowed</label>
                <select id="page-field-18" style={INPUT_STYLE} value={taxForm.tax_exempt_enabled} onChange={(e) => setTaxForm((f) => ({ ...f, tax_exempt_enabled: e.target.value }))}>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
            </div>
            <button
              onClick={() => void saveSection(Object.entries(taxForm))}
              disabled={saving}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving..." : t("common.save")}
            </button>
          </div>

          {/* ── Drug Interaction Alerts ───────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <ShieldAlert size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Drug Interaction Alerts</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-19">Enable Alerts</label>
                <select id="page-field-19" style={INPUT_STYLE} value={ddiForm.ddi_alerts_enabled} onChange={(e) => setDdiForm((f) => ({ ...f, ddi_alerts_enabled: e.target.value }))}>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-20">Severity Threshold</label>
                <select id="page-field-20" style={INPUT_STYLE} value={ddiForm.ddi_severity_threshold} onChange={(e) => setDdiForm((f) => ({ ...f, ddi_severity_threshold: e.target.value }))}>
                  <option value="minor">Minor</option>
                  <option value="moderate">Moderate</option>
                  <option value="major">Major</option>
                  <option value="contraindicated">Contraindicated</option>
                </select>
              </div>
            </div>
            <button
              onClick={() => void saveSection(Object.entries(ddiForm))}
              disabled={saving}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving..." : t("common.save")}
            </button>
          </div>

          {/* ── Email / SMTP ──────────────────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Mail size={20} style={{ color: "var(--primary)" }} />
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Email / SMTP Settings</h2>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-21">SMTP Host</label>
                <input id="page-field-21" style={INPUT_STYLE} value={emailForm.smtp_host} onChange={(e) => setEmailForm((f) => ({ ...f, smtp_host: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-22">SMTP Port</label>
                <input id="page-field-22" style={INPUT_STYLE} value={emailForm.smtp_port} onChange={(e) => setEmailForm((f) => ({ ...f, smtp_port: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-23">Username</label>
                <input id="page-field-23" style={INPUT_STYLE} value={emailForm.smtp_user} onChange={(e) => setEmailForm((f) => ({ ...f, smtp_user: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-24">Password</label>
                <input id="page-field-24" style={INPUT_STYLE} type="password" value={emailForm.smtp_password} onChange={(e) => setEmailForm((f) => ({ ...f, smtp_password: e.target.value }))} />
              </div>
              <div style={{ gridColumn: "span 2" }}>
                <label style={LABEL_STYLE} htmlFor="page-field-25">From Address</label>
                <input id="page-field-25" style={INPUT_STYLE} type="email" value={emailForm.smtp_from} onChange={(e) => setEmailForm((f) => ({ ...f, smtp_from: e.target.value }))} />
              </div>
            </div>
            <button
              onClick={() => void saveSection(Object.entries(emailForm))}
              disabled={saving}
              style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
            >
              {saving ? "Saving..." : t("common.save")}
            </button>
          </div>

          {/* ── Session & Security Configuration (Admin Only) ─────────────────── */}
          {isAdmin && (
            <div style={SECTION_STYLE}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <Clock size={20} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Session & Security</h2>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-26">Session Timeout</label>
                  <select id="page-field-26"
                    style={INPUT_STYLE}
                    value={sessionForm.session_idle_minutes}
                    onChange={(e) => setSessionForm((f) => ({ ...f, session_idle_minutes: e.target.value }))}
                  >
                    <option value="15">15 minutes (default)</option>
                    <option value="30">30 minutes</option>
                    <option value="60">1 hour</option>
                    <option value="240">4 hours</option>
                    <option value="480">8 hours</option>
                    <option value="never">Never ⚠️</option>
                  </select>
                  {sessionForm.session_idle_minutes === "never" && (
                    <p style={{ fontSize: 12, color: "var(--warning, #d97706)", marginTop: 6 }}>
                      Sessions that never expire are less secure. Only use this on private, single-user devices.
                    </p>
                  )}
                </div>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-27">Absolute Session Limit</label>
                  <select id="page-field-27"
                    style={INPUT_STYLE}
                    value={sessionForm.session_absolute_minutes}
                    onChange={(e) => setSessionForm((f) => ({ ...f, session_absolute_minutes: e.target.value }))}
                  >
                    <option value="240">4 hours</option>
                    <option value="480">8 hours (default)</option>
                    <option value="1440">24 hours</option>
                    <option value="never">Never</option>
                  </select>
                  {sessionForm.session_absolute_minutes === "never" && (
                    <p style={{ fontSize: 12, color: "var(--warning, #d97706)", marginTop: 6 }}>
                      Sessions that never expire are less secure. Only use this on private, single-user devices.
                    </p>
                  )}
                </div>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-28">Alerts Enabled</label>
                  <select id="page-field-28" style={INPUT_STYLE} value={sessionForm.alert_check_enabled} onChange={(e) => setSessionForm((f) => ({ ...f, alert_check_enabled: e.target.value }))}>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </select>
                </div>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-29">Critical Expiry (days)</label>
                  <input id="page-field-29" style={INPUT_STYLE} type="number" min="1" value={sessionForm.alert_expiry_critical_days} onChange={(e) => setSessionForm((f) => ({ ...f, alert_expiry_critical_days: e.target.value }))} />
                </div>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-30">Warning Expiry (days)</label>
                  <input id="page-field-30" style={INPUT_STYLE} type="number" min="1" value={sessionForm.alert_expiry_warning_days} onChange={(e) => setSessionForm((f) => ({ ...f, alert_expiry_warning_days: e.target.value }))} />
                </div>
              </div>
              <button
                onClick={() => void saveSessionSettings()}
                disabled={saving}
                style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
              >
                {saving ? "Saving..." : t("common.save")}
              </button>
            </div>
          )}

          {/* ── Support Contact (Admin Only) ─────────────────────────────── */}
          {isAdmin && (
            <div style={SECTION_STYLE}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <MessageSquare size={20} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Support Contact</h2>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-31">Support Name</label>
                  <input id="page-field-31" style={INPUT_STYLE} value={supportForm.support_name} onChange={(e) => setSupportForm((f) => ({ ...f, support_name: e.target.value }))} placeholder="e.g. Pharmacy Support Team" />
                </div>
                <div>
                  <label style={LABEL_STYLE} htmlFor="page-field-32">Support Email</label>
                  <input id="page-field-32" style={INPUT_STYLE} type="email" value={supportForm.support_email} onChange={(e) => setSupportForm((f) => ({ ...f, support_email: e.target.value }))} placeholder="support@pharmacy.com" />
                </div>
                <div style={{ gridColumn: "span 2" }}>
                  <label style={LABEL_STYLE} htmlFor="page-field-33">Custom Message (optional)</label>
                  <textarea id="page-field-33" style={{ ...INPUT_STYLE, minHeight: 80, resize: "vertical" }} value={supportForm.support_message} onChange={(e) => setSupportForm((f) => ({ ...f, support_message: e.target.value }))} placeholder="Optional message displayed on the Support page" />
                </div>
              </div>
              <button
                onClick={() => void saveSupportSettings()}
                disabled={saving}
                style={{ marginTop: 12, padding: "8px 20px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
              >
                {saving ? "Saving..." : t("common.save")}
              </button>
            </div>
          )}

          {/* ── Third-Party Integrations ──────────────────────────────── */}
          <div style={SECTION_STYLE}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Plug size={20} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Third-Party Integrations</h2>
              </div>
              {canManage && (
                <button
                  onClick={() => setShowAddIntegration(true)}
                  style={{ display: "flex", alignItems: "center", gap: 4, padding: "6px 12px", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}
                >
                  <Plus size={14} /> Add
                </button>
              )}
            </div>

            {integrations.length === 0 ? (
              <p style={{ color: "var(--fg-muted)", fontSize: 13 }}>No integrations configured.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--fg-muted)", fontWeight: 600 }}>Provider</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--fg-muted)", fontWeight: 600 }}>Base URL</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--fg-muted)", fontWeight: 600 }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {integrations.map((integ) => (
                    <tr key={integ.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 12px", color: "var(--fg)" }}>{integ.provider_name}</td>
                      <td style={{ padding: "8px 12px", color: "var(--fg-muted)", fontFamily: "monospace" }}>{integ.base_url || "—"}</td>
                      <td style={{ padding: "8px 12px" }}>
                        <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 4, background: integ.is_active ? "var(--success)" : "var(--bg-hover)", color: integ.is_active ? "#fff" : "var(--fg-muted)" }}>
                          {integ.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* Add Integration Modal */}
      {showAddIntegration && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 50 }}>
          <div style={{ width: "100%", maxWidth: 400, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, padding: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)" }}>Add Integration</h2>
              <button onClick={() => setShowAddIntegration(false)} style={{ background: "none", border: "none", color: "var(--fg-muted)", cursor: "pointer" }}><X size={18} /></button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-34">Provider Name</label>
                <input id="page-field-34" style={INPUT_STYLE} placeholder="e.g. drug_evaluate" value={integForm.provider_name} onChange={(e) => setIntegForm((f) => ({ ...f, provider_name: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-35">API Key</label>
                <input id="page-field-35" style={INPUT_STYLE} type="password" placeholder="Bearer token or API key" value={integForm.api_key} onChange={(e) => setIntegForm((f) => ({ ...f, api_key: e.target.value }))} />
              </div>
              <div>
                <label style={LABEL_STYLE} htmlFor="page-field-36">Base URL (optional)</label>
                <input id="page-field-36" style={INPUT_STYLE} placeholder="https://api.example.com" value={integForm.base_url} onChange={(e) => setIntegForm((f) => ({ ...f, base_url: e.target.value }))} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button onClick={() => setShowAddIntegration(false)} style={{ flex: 1, padding: "8px 0", border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-input)", color: "var(--fg)", fontSize: 13, cursor: "pointer" }}>Cancel</button>
              <button
                onClick={() => void handleAddIntegration()}
                disabled={integSaving || !integForm.provider_name || !integForm.api_key}
                style={{ flex: 1, padding: "8px 0", background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: integSaving ? "default" : "pointer", opacity: integSaving || !integForm.provider_name || !integForm.api_key ? 0.6 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
              >
                {integSaving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                Save
              </button>
            </div>
          </div>
        </div>
      )}
      </RouteGuard>
    </DashboardLayout>
  );
}
