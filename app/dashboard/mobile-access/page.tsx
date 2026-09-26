"use client";

/**
 * Mobile Access (Phase 4 Step 1.5 — blueprint §1.4).
 *
 * QR tab: renders the HMAC-signed pairing QR (networkKey = HMAC-SHA256 over
 * url + instanceId + expiresAt, keyed by the server-side qr_secret_key that
 * is never exposed), auto-refreshes every 24h with a manual refresh button,
 * and lists paired devices with immediate revocation. Includes the required
 * firewall note from blueprint §1.3.2.
 */
import { useCallback, useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { QRCodeSVG } from "qrcode.react";
import { Smartphone, RefreshCw, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { DeviceRead, QrPayload } from "@/types/contracts";

const SECTION_STYLE = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
} as const;

function formatSeen(iso?: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export default function MobileAccessPage() {
  const [qr, setQr] = useState<QrPayload | null>(null);
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<number | null>(null);

  const loadDevices = useCallback(async () => {
    const { data } = await api.get<DeviceRead[]>("/api/v1/devices");
    setDevices(data);
  }, []);

  const loadQr = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const { data } = await api.get<QrPayload>("/api/v1/devices/qr-payload");
      setQr(data);
      await loadDevices();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load QR payload");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, [loadDevices]);

  useEffect(() => {
    void loadQr();
    // Blueprint §1.4.2: QR regenerates every 24 hours automatically.
    const REFRESH_MS = 24 * 60 * 60 * 1000;
    const timer = setInterval(() => void loadQr(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadQr]);

  const revokeDevice = useCallback(
    async (id: number) => {
      setRevoking(id);
      try {
        await api.delete(`/api/v1/devices/${id}`);
        await loadDevices();
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Revoke failed");
      } finally {
        setRevoking(null);
      }
    },
    [loadDevices],
  );

  const qrText = qr
    ? JSON.stringify({
        url: qr.url,
        networkKey: qr.network_key,
        instanceId: qr.instance_id,
        apiVersion: qr.api_version,
        expiresAt: qr.expires_at,
      })
    : "";

  return (
    <DashboardLayout>
      <RouteGuard permission="settings.read">
        <div style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
            <Smartphone size={22} style={{ color: "var(--primary)" }} />
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", margin: 0 }}>Mobile Access</h1>
          </div>

          {error && (
            <div style={{ ...SECTION_STYLE, borderColor: "var(--warning, #d97706)" }}>
              <p style={{ margin: 0, color: "var(--warning, #d97706)", fontSize: 13 }}>{error}</p>
            </div>
          )}

          {/* ── Pairing QR (blueprint §1.4.2/§1.4.3) ─────────────────── */}
          <div style={SECTION_STYLE}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginTop: 0 }}>
              Pair a new device
            </h2>
            <p style={{ fontSize: 13, color: "var(--fg-muted, #6b7280)", marginTop: 0 }}>
              Scan this QR with the Pharmacy Suite mobile app. The code is signed and expires
              {qr ? ` ${new Date(qr.expires_at).toLocaleString()}` : " in 24 hours"}.
            </p>
            {loading ? (
              <Loader2 size={28} className="animate-spin" style={{ color: "var(--primary)" }} />
            ) : qr ? (
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
                <div
                  style={{
                    background: "#fff",
                    padding: 12,
                    borderRadius: 10,
                    border: "1px solid var(--border)",
                  }}
                >
                  <QRCodeSVG value={qrText} size={192} level="M" />
                </div>
                <div style={{ fontSize: 13, color: "var(--fg)", minWidth: 220 }}>
                  <div>
                    <strong>Server:</strong> {qr.url}
                  </div>
                  <div>
                    <strong>Instance:</strong> <span style={{ fontFamily: "monospace" }}>{qr.instance_id}</span>
                  </div>
                  <div>
                    <strong>API version:</strong> {qr.api_version}
                  </div>
                  <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                    <button
                      onClick={() => void loadQr()}
                      disabled={refreshing}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "8px 16px",
                        background: "var(--primary)",
                        color: "var(--primary-fg)",
                        border: "none",
                        borderRadius: 6,
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: refreshing ? "default" : "pointer",
                        opacity: refreshing ? 0.6 : 1,
                      }}
                    >
                      <RefreshCw size={14} /> Refresh QR
                    </button>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--fg-muted, #6b7280)", marginTop: 10 }}>
                    The pairing secret never leaves the server — the QR carries only its HMAC signature.
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          {/* ── Firewall note (blueprint §1.3.2 — required) ──────────── */}
          <div style={SECTION_STYLE}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginTop: 0 }}>Network requirements</h2>
            <p style={{ fontSize: 13, color: "var(--fg)", margin: 0 }}>
              Shared mode requires port 8000 to be open on your local network firewall. Your pharmacy
              network router may need configuration. This does NOT expose your data to the internet —
              only devices on your local WiFi can connect.
            </p>
          </div>

          {/* ── Connected devices (blueprint §1.4.6) ─────────────────── */}
          <div style={SECTION_STYLE}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginTop: 0 }}>Connected devices</h2>
            {devices.length === 0 ? (
              <p style={{ fontSize: 13, color: "var(--fg-muted, #6b7280)" }}>
                No devices paired yet. Scan the QR above with the mobile app.
              </p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--fg-muted, #6b7280)" }}>
                    <th style={TH}>Device</th>
                    <th style={TH}>Paired</th>
                    <th style={TH}>Last Seen</th>
                    <th style={TH}>User</th>
                    <th style={TH}>Status</th>
                    <th style={TH}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.map((d) => (
                    <tr key={d.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={TD}>{d.device_name || `Device #${d.id}`}</td>
                      <td style={TD}>{d.created_at ? new Date(d.created_at).toLocaleDateString() : "—"}</td>
                      <td style={TD}>{formatSeen(d.last_seen_at)}</td>
                      <td style={TD}>{d.user_id ? `#${d.user_id}` : "—"}</td>
                      <td style={TD}>
                        <span style={{ color: d.revoked ? "var(--warning, #d97706)" : "var(--primary)" }}>
                          {d.revoked ? "Revoked" : "Active"}
                        </span>
                      </td>
                      <td style={TD}>
                        {!d.revoked && (
                          <button
                            onClick={() => void revokeDevice(d.id)}
                            disabled={revoking === d.id}
                            style={{
                              padding: "4px 12px",
                              background: "#ef4444",
                              color: "#fff",
                              border: "none",
                              borderRadius: 6,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: revoking === d.id ? "default" : "pointer",
                              opacity: revoking === d.id ? 0.6 : 1,
                            }}
                          >
                            {revoking === d.id ? "Revoking…" : "Revoke"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </RouteGuard>
    </DashboardLayout>
  );
}

const TH = { padding: "8px 10px", fontWeight: 600 } as const;
const TD = { padding: "8px 10px", color: "var(--fg)" } as const;
