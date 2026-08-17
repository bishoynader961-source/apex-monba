"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuthStore } from "@/stores/authStore";
import { useLicenseStore } from "@/stores/licenseStore";

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
          disabled={loading}
          style={{ width: "100%", padding: "0.7rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: loading ? "default" : "pointer", opacity: loading ? 0.7 : 1 }}
        >
          {loading ? "Validating…" : "Validate License"}
        </button>
      </form>

      {status && (
        <pre style={{ background: "#f3f4f6", padding: 12, borderRadius: 6, marginTop: 16, fontSize: 12, overflowX: "auto" }}>
          {JSON.stringify(status, null, 2)}
        </pre>
      )}
    </main>
  );
}
