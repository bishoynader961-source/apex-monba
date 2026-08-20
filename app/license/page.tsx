"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuthStore } from "@/stores/authStore";
import { useLicenseStore } from "@/stores/licenseStore";
import { initiateCheckout } from "@/lib/api/license";

export default function LicensePage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  const [licenseKey, setLicenseKey] = useState("");
  const [hardwareId, setHardwareId] = useState("");

  const status = useLicenseStore((s) => s.status);
  const loading = useLicenseStore((s) => s.loading);
  const error = useLicenseStore((s) => s.error);
  const validate = useLicenseStore((s) => s.validate);

  if (!isAuthenticated()) {
    router.replace("/login");
    return null;
  }

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

  return (
    <main style={{ maxWidth: 520, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>License Validation</h1>
        <nav style={{ display: "flex", gap: 12, fontSize: 13 }}>
          <a href="/pos">POS</a>
          <a href="/license">License</a>
          <button onClick={() => logout()} style={{ fontSize: 13 }}>Logout</button>
        </nav>
      </header>

      <form onSubmit={onSubmit}>
        <label style={{ display: "block", marginBottom: 14, fontSize: 13 }}>
          License key
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
          Hardware ID
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
          {loading ? "Validating…" : "Validate License"}
        </button>
      </form>

      <div style={{ marginTop: 20, paddingTop: 20, borderTop: "1px solid #e5e7eb", textAlign: "center" }}>
        <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>Need a new license or subscription renewal?</p>
        <button
          onClick={() => void handlePurchase()}
          disabled={checkoutLoading || loading}
          style={{ padding: "0.6rem 1.2rem", background: "#10b981", color: "#fff", border: "none", borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: checkoutLoading ? "default" : "pointer", opacity: checkoutLoading ? 0.7 : 1 }}
        >
          {checkoutLoading ? "Starting Checkout…" : "Purchase License via Creem"}
        </button>
      </div>

      {status && (
        <pre style={{ background: "#f3f4f6", padding: 12, borderRadius: 6, marginTop: 16, fontSize: 12, overflowX: "auto" }}>
          {JSON.stringify(status, null, 2)}
        </pre>
      )}
    </main>
  );
}
