"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { getDashboardMetrics, type DashboardMetrics } from "@/lib/api/dashboard";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import { RxQueueDashboard } from "@/components/rx/RxQueueDashboard";

const CARD_BASE = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 16,
};

export default function DashboardPage() {
  const { t } = useI18n();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await getDashboardMetrics();
      setMetrics(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated()) {
      void loadMetrics();
    }
  }, [isAuthenticated, loadMetrics]);

  if (!isAuthenticated()) return null;

  const MODULES = [
    { href: "/pos", label: t("dashboard.posLabel"), desc: t("dashboard.posDesc"), color: "#16a34a" },
    { href: "/dashboard/inventory", label: t("dashboard.inventoryLabel"), desc: t("dashboard.inventoryDesc"), color: "#2563eb" },
    { href: "/patients", label: t("dashboard.patientsLabel"), desc: t("dashboard.patientsDesc"), color: "#7c3aed" },
    { href: "/dashboard/analytics", label: t("dashboard.analyticsLabel"), desc: t("dashboard.analyticsDesc"), color: "#d97706" },
    { href: "/dashboard/quick-sig", label: t("dashboard.quickSigLabel") ?? "Quick-SIG", desc: t("dashboard.quickSigDesc") ?? "SIG templates", color: "#0891b2" },
    { href: "/dashboard/purchase-orders", label: t("dashboard.poLabel") ?? "Purchase Orders", desc: t("dashboard.poDesc") ?? "Manage POs", color: "#4f46e5" },
    { href: "/dashboard/drug-interactions", label: t("interactions.title") ?? "Drug Interactions", desc: t("interactions.label") ?? "Manage DDI", color: "#dc2626" },
    { href: "/dashboard/label-engine", label: "Label Designer", desc: "Design product labels", color: "#0d9488" },
    { href: "/dashboard/invoice-parse", label: "Invoice Parser", desc: "Parse supplier invoices", color: "#d97706" },
    { href: "/dashboard/expiry-alerts", label: "Expiry Alerts", desc: "Monitor expiring stock", color: "#ef4444" },
  ];

  return (
    <DashboardLayout>
      <RouteGuard permission="inventory.read">
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", marginBottom: 4 }}>
        {t("dashboard.title")}
      </h1>
      {user && (
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 20 }}>
          {t("dashboard.signedInAs")} <span style={{ color: "var(--fg)" }}>{user.username}</span>
        </p>
      )}

      {/* ── KPI Cards ──────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
        {[
          { label: "Total Inventory Value", value: metrics ? formatMoney(parseMoney(metrics.total_inventory_value)) : "—", icon: "💰" },
          { label: "Today's Sales", value: metrics ? formatMoney(parseMoney(metrics.today_revenue)) : "—", icon: "📈" },
          { label: "Total Products", value: metrics?.total_products?.toString() ?? "—", icon: "📦" },
          { label: "Low Stock Items", value: metrics?.low_stock?.length?.toString() ?? "—", icon: "⚠️", alert: (metrics?.low_stock?.length ?? 0) > 0 },
          { label: "Active Patients", value: metrics?.active_patients?.toString() ?? "—", icon: "👤" },
          { label: "Pending Rx", value: metrics?.pending_rx_count?.toString() ?? "—", icon: "📋", alert: (metrics?.pending_rx_count ?? 0) > 0 },
        ].map((kpi) => (
          <div key={kpi.label} style={{ ...CARD_BASE, display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 28 }}>{kpi.icon}</span>
            <div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>{kpi.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: kpi.alert ? "#ef4444" : "var(--fg)" }}>{kpi.value}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16, marginBottom: 20 }}>
        {/* ── Low-Stock Alerts ──────────────────────────────────────── */}
        <div style={CARD_BASE}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Low-Stock Alerts</h2>
          {loading ? (
            <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>Loading...</p>
          ) : !metrics || metrics.low_stock.length === 0 ? (
            <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>No low-stock items.</p>
          ) : (
            <div style={{ maxHeight: 200, overflowY: "auto" }}>
              {metrics.low_stock.map((item) => (
                <div key={item.barcode} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: 12 }}>
                  <span style={{ color: "var(--fg)" }}>{item.name}</span>
                  <span style={{ color: item.on_hand === 0 ? "#ef4444" : "#d97706", fontWeight: 600 }}>
                    {item.on_hand} / {item.threshold}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Expiring Soon ─────────────────────────────────────────── */}
        <div style={CARD_BASE}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Expiring Soon</h2>
          {loading ? (
            <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>Loading...</p>
          ) : !metrics || metrics.expiring_soon.length === 0 ? (
            <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>No items expiring soon.</p>
          ) : (
            <div style={{ maxHeight: 200, overflowY: "auto" }}>
              {metrics.expiring_soon.map((item) => (
                <div key={item.barcode} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: 12 }}>
                  <span style={{ color: "var(--fg)" }}>{item.name}</span>
                  <span style={{ color: "#ef4444", fontWeight: 600 }}>{item.expiry}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Recent Activity ──────────────────────────────────────────── */}
      <div style={{ ...CARD_BASE, marginBottom: 20 }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Recent Activity</h2>
        {loading ? (
          <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>Loading...</p>
        ) : !metrics || metrics.recent_activity.length === 0 ? (
          <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>No recent activity.</p>
        ) : (
          <div style={{ maxHeight: 200, overflowY: "auto" }}>
            {metrics.recent_activity.map((a, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: 12 }}>
                <span style={{ color: "var(--fg)", fontWeight: 500 }}>{a.action}</span>
                <span style={{ color: "var(--fg-muted)", flex: 1, margin: "0 12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.details}</span>
                <span style={{ color: "var(--fg-muted)", flexShrink: 0 }}>{a.time ? new Date(a.time).toLocaleString() : ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Rx Queue Widget ────────────────────────────────────────────── */}
      <div style={{ ...CARD_BASE, marginBottom: 20 }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Rx Queue (Awaiting Action)</h2>
        <RxQueueDashboard />
      </div>

      {/* ── Quick Navigation ──────────────────────────────────────────── */}
      <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Quick Access</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
        {MODULES.map((mod) => (
          <Link
            key={mod.href}
            href={mod.href}
            style={{
              ...CARD_BASE,
              borderLeft: `3px solid ${mod.color}`,
              textDecoration: "none",
              transition: "background 0.15s",
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)" }}>{mod.label}</div>
            <div style={{ fontSize: 12, color: "var(--fg-muted)", marginTop: 2 }}>{mod.desc}</div>
          </Link>
        ))}
      </div>

      {/* ── Task Panel ───────────────────────────────────────────────── */}
      <div style={{ ...CARD_BASE, marginTop: 20 }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", marginBottom: 10 }}>Tasks</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
          {[
            { label: "New Rx", desc: "Process prescriptions", href: "/rx", color: "#7c3aed", count: undefined },
            { label: "Add Patient", desc: "Register new patient", href: "/patients", color: "#7c3aed", count: undefined },
            { label: "Receive Stock", desc: "Log incoming inventory", href: "/dashboard/vendors", color: "#2563eb", count: metrics?.low_stock?.length },
            { label: "Expiry Check", desc: "Review expiring items", href: "/dashboard/expiry-alerts", color: "#ef4444", count: metrics?.expiring_soon?.length },
            { label: "Run Report", desc: "View analytics dashboard", href: "/dashboard/analytics", color: "#d97706", count: undefined },
            { label: "Purchase Orders", desc: "Manage POs", href: "/dashboard/purchase-orders", color: "#4f46e5", count: undefined },
            { label: "Invoice Parse", desc: "Scan supplier invoices", href: "/dashboard/invoice-parse", color: "#d97706", count: undefined },
            { label: "Bulk Import", desc: "Import from file", href: "/dashboard/bulk-import", color: "#0891b2", count: undefined },
          ].map((task) => (
            <Link
              key={task.href}
              href={task.href}
              style={{
                ...CARD_BASE,
                borderLeft: `3px solid ${task.color}`,
                textDecoration: "none",
                padding: 12,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>{task.label}</span>
                {task.count !== undefined && task.count > 0 && (
                  <span style={{ fontSize: 11, fontWeight: 700, color: task.color, background: `${task.color}20`, padding: "2px 6px", borderRadius: 10 }}>
                    {task.count}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 2 }}>{task.desc}</div>
            </Link>
          ))}
        </div>
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}
