"use client";

import { useState, useEffect, useCallback } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { api } from "@/lib/api";
import { getAlerts, type AlertCounts } from "@/lib/api/alerts";
import { useRouter } from "next/navigation";
import { AlertTriangle, Clock, Package, TrendingDown } from "lucide-react";

interface ExpiryItem {
  name: string;
  quantity_on_hand: number;
  expiry_date: string;
  internal_unique_barcode: string;
  vendor_name: string;
  price: number;
  reorder_threshold?: number;
}

const CARD_BASE = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 16,
};

export default function ExpiryAlertsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("inventory.read");

  const [items, setItems] = useState<ExpiryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [thresholdDays, setThresholdDays] = useState(90);
  const [criticalDays, setCriticalDays] = useState(30);
  const [vendorFilter, setVendorFilter] = useState("");
  const [alertCounts, setAlertCounts] = useState<AlertCounts | null>(null);

  const loadAlerts = useCallback(async () => {
    try {
      setAlertCounts(await getAlerts());
    } catch {
      // silently fail
    }
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/v1/inventory/batches?expiry_within=${thresholdDays}`);
      setItems(res.data.items ?? res.data ?? []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [thresholdDays]);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated() && canRead) {
      void loadItems();
      void loadAlerts();
    }
  }, [isAuthenticated, canRead, loadItems, loadAlerts]);

  if (!isAuthenticated()) return null;

  const now = new Date();
  const criticalCutoff = new Date(now.getTime() + criticalDays * 86400000);
  const thresholdCutoff = new Date(now.getTime() + thresholdDays * 86400000);

  const expired = items.filter((i) => new Date(i.expiry_date) < now);
  const critical = items.filter((i) => {
    const d = new Date(i.expiry_date);
    return d >= now && d <= criticalCutoff;
  });
  const warning = items.filter((i) => {
    const d = new Date(i.expiry_date);
    return d > criticalCutoff && d <= thresholdCutoff;
  });

  const lowStock = items.filter(
    (i) => i.reorder_threshold && i.quantity_on_hand <= i.reorder_threshold
  );

  const filtered = (list: ExpiryItem[]) =>
    vendorFilter ? list.filter((i) => i.vendor_name === vendorFilter) : list;

  const vendors = [...new Set(items.map((i) => i.vendor_name).filter(Boolean))].sort();

  function renderTable(items: ExpiryItem[], color: string) {
    if (items.length === 0) return <p style={{ fontSize: 12, color: "var(--fg-muted)" }}>None.</p>;
    return (
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--fg-muted)" }}>Product</th>
            <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--fg-muted)" }}>Qty</th>
            <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--fg-muted)" }}>Expiry</th>
            <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--fg-muted)" }}>Vendor</th>
            <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--fg-muted)" }}>Value</th>
          </tr>
        </thead>
        <tbody>
          {filtered(items).map((item) => (
            <tr key={item.internal_unique_barcode} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "6px 8px", color: "var(--fg)" }}>{item.name}</td>
              <td style={{ padding: "6px 8px", textAlign: "right", color: "var(--fg)" }}>{item.quantity_on_hand}</td>
              <td style={{ padding: "6px 8px", color }}>{item.expiry_date}</td>
              <td style={{ padding: "6px 8px", color: "var(--fg-muted)" }}>{item.vendor_name}</td>
              <td style={{ padding: "6px 8px", textAlign: "right", color: "var(--fg)" }}>${(item.price * item.quantity_on_hand).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <DashboardLayout>
      <RouteGuard permission="inventory.read">
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", marginBottom: 16 }}>Expiry Alerts</h1>

      {/* Alert Summary Cards */}
      {alertCounts && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "Expired", value: alertCounts.expired, icon: AlertTriangle, color: "#ef4444" },
            { label: "Critical", value: alertCounts.critical, icon: Clock, color: "#f97316" },
            { label: "Warning", value: alertCounts.warning, icon: AlertTriangle, color: "#eab308" },
            { label: "Low Stock", value: alertCounts.low_stock, icon: TrendingDown, color: "#3b82f6" },
          ].map((card) => (
            <div
              key={card.label}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderLeft: `3px solid ${card.color}`,
                borderRadius: 8,
                padding: 12,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <card.icon size={18} style={{ color: card.color }} />
              <div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--fg)" }}>{card.value}</div>
                <div style={{ fontSize: 11, color: "var(--fg-muted)" }}>{card.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Controls */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, color: "var(--fg-muted)" }}>
          Threshold:
          <input
            aria-label="Expiry threshold days"
            type="number"
            value={thresholdDays}
            onChange={(e) => setThresholdDays(parseInt(e.target.value) || 90)}
            style={{ width: 60, marginLeft: 4, padding: "4px 6px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-input)", color: "var(--fg)" }}
          /> days
        </label>
        <label style={{ fontSize: 12, color: "var(--fg-muted)" }}>
          Critical:
          <input
            aria-label="Critical expiry days"
            type="number"
            value={criticalDays}
            onChange={(e) => setCriticalDays(parseInt(e.target.value) || 30)}
            style={{ width: 60, marginLeft: 4, padding: "4px 6px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-input)", color: "var(--fg)" }}
          /> days
        </label>
        <select
          value={vendorFilter}
          onChange={(e) => setVendorFilter(e.target.value)}
          style={{ padding: "4px 8px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-input)", color: "var(--fg)" }}
        >
          <option value="">All Vendors</option>
          {vendors.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
        <button
          onClick={() => void loadItems()}
          style={{ padding: "6px 14px", fontSize: 12, background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <p style={{ color: "var(--fg-muted)" }}>Loading...</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Expired */}
          <div style={{ ...CARD_BASE, borderLeft: "3px solid #ef4444" }}>
            <h2 style={{ fontSize: 14, fontWeight: 600, color: "#ef4444", marginBottom: 8 }}>
              Already Expired ({filtered(expired).length})
            </h2>
            {renderTable(expired, "#ef4444")}
          </div>

          {/* Critical */}
          <div style={{ ...CARD_BASE, borderLeft: "3px solid #f97316" }}>
            <h2 style={{ fontSize: 14, fontWeight: 600, color: "#f97316", marginBottom: 8 }}>
              Critical / Urgent ({filtered(critical).length})
            </h2>
            {renderTable(critical, "#f97316")}
          </div>

          {/* Warning */}
          <div style={{ ...CARD_BASE, borderLeft: "3px solid #eab308" }}>
            <h2 style={{ fontSize: 14, fontWeight: 600, color: "#eab308", marginBottom: 8 }}>
              Expiring Soon ({filtered(warning).length})
            </h2>
            {renderTable(warning, "#eab308")}
          </div>

          {/* Low Stock */}
          {lowStock.length > 0 && (
            <div style={{ ...CARD_BASE, borderLeft: "3px solid #3b82f6" }}>
              <h2 style={{ fontSize: 14, fontWeight: 600, color: "#3b82f6", marginBottom: 8 }}>
                <TrendingDown size={14} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />
                Low Stock ({filtered(lowStock).length})
              </h2>
              {renderTable(lowStock, "#3b82f6")}
            </div>
          )}
        </div>
      )}
      </RouteGuard>
    </DashboardLayout>
  );
}
