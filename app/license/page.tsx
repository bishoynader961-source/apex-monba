"use client";

import { useRouter } from "next/navigation";
  import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { useAuthStore } from "@/stores/authStore";
import { useLicenseStore } from "@/stores/licenseStore";
import { getDeviceId } from "@/lib/deviceId";
import { importLicenseFile, initiateCheckout } from "@/lib/api/license";

export default function LicensePage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);
  const { t } = useI18n();

  const [licenseKey, setLicenseKey] = useState("");
  const [hardwareId, setHardwareId] = useState(() =>
    typeof window !== "undefined" ? getDeviceId() : ""
  );

  const status = useLicenseStore((s) => s.status);
  const loading = useLicenseStore((s) => s.loading);
  const error = useLicenseStore((s) => s.error);
  const validate = useLicenseStore((s) => s.validate);

  const isTauri = typeof window !== "undefined" && "__TAURI__" in window;
  const [importLoading, setImportLoading] = useState(false);

  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
    }
  }, [token, router]);

  useEffect(() => {
    if (status && status.status === "active") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void validate(licenseKey, hardwareId);
  };

  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const handlePurchase = async () => {
    setCheckoutLoading(true);
    try {
      const res = await initiateCheckout({
        success_url: window.location.origin + "/license?activated=1",
        cancel_url: window.location.origin + "/license"
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      useLicenseStore.setState({ error: err instanceof Error ? err.message : "Checkout failed" });
      setCheckoutLoading(false);
    }
  };

  const handleImportFile = async () => {
    if (!isTauri) return;
    setImportLoading(true);
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const { readTextFile } = await import("@tauri-apps/plugin-fs");

      const selected = await open({
        multiple: false,
        filters: [{ name: "License File", extensions: ["json", "lic"] }],
      });

      if (!selected) return;

      const fileContent = await readTextFile(selected as string);
      const hwId = hardwareId || getDeviceId();
      const result = await importLicenseFile(hwId, fileContent);

      useLicenseStore.setState({ status: result, loading: false });
      localStorage.setItem("pp_license_key", result.license_key);
      router.replace("/dashboard");
    } catch (err) {
      useLicenseStore.setState({
        error: err instanceof Error ? err.message : "File import failed",
      });
      setImportLoading(false);
    }
  };

  return (
    <main style={{ maxWidth: 520, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("license.title")}</h1>
        <nav style={{ display: "flex", gap: 12, fontSize: 13 }}>
          <a href="/pos">{t("license.navPos")}</a>
          <a href="/license">{t("license.navLicense")}</a>
          <button onClick={() => logout()} style={{ fontSize: 13 }}>{t("license.logout")}</button>
        </nav>
      </header>

      <form onSubmit={onSubmit}>
        <label style={{ display: "block", marginBottom: 14, fontSize: 13 }}>
          {t("license.labelLicenseKey")}
          <input
            type="text"
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="PHARM-XXXX-XXXX-XXXX"
            required
            style={{ width: "100%", marginTop: 6, padding: "0.5rem 0.7rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 18, fontSize: 13 }}>
          {t("license.labelHardwareId")}
          <input
            type="text"
            value={hardwareId}
            onChange={(e) => setHardwareId(e.target.value)}
            required
            style={{ width: "100%", marginTop: 6, padding: "0.5rem 0.7rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
          />
        </label>
        {error && (
          <div style={{ background: "#fee2e2", color: "#991b2b", padding: "0.6rem 1rem", borderRadius: 6, marginBottom: 14, fontSize: 13 }}>
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading || checkoutLoading}
          style={{ width: "100%", padding: "0.7rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: loading ? "default" : "pointer", opacity: loading ? 0.7 : 1 }}
        >
          {loading ? t("license.validating") : t("license.validateLicense")}
        </button>
      </form>

      <div style={{ marginTop: 20, paddingTop: 20, borderTop: "1px solid #e5e7eb", textAlign: "center" }}>
        <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>{t("license.purchasePrompt")}</p>
        <button
          onClick={() => void handlePurchase()}
          disabled={checkoutLoading || loading}
          style={{ padding: "0.6rem 1.2rem", background: "#10b981", color: "#fff", border: "none", borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: checkoutLoading ? "default" : "pointer", opacity: checkoutLoading ? 0.7 : 1 }}
        >
          {checkoutLoading ? t("license.checkoutLoading") : t("license.purchaseViaCreem")}
        </button>
      </div>

      <div style={{ marginTop: 20, paddingTop: 20, borderTop: "1px solid #e5e7eb", textAlign: "center" }}>
        {isTauri ? (
          <>
            <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>{t("license.importPrompt")}</p>
            <button
              onClick={() => void handleImportFile()}
              disabled={importLoading || loading}
              style={{ padding: "0.6rem 1.2rem", background: "#3b82f6", color: "#fff", border: "none", borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: importLoading ? "default" : "pointer", opacity: importLoading ? 0.7 : 1 }}
            >
              {importLoading ? t("license.importLoading") : t("license.importFileButton")}
            </button>
          </>
        ) : (
          <p style={{ fontSize: 13, color: "#9ca3af" }}>
            {t("license.importDesktopOnly")}
          </p>
        )}
      </div>
    </main>
  );
}
