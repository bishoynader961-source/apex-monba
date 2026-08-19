"use client";

import { useEffect, useState } from "react";

import { getSalesReport } from "@/lib/api/pos";
import type { SalesReport } from "@/types/contracts";

interface Props {
  open: boolean;
  onClose: () => void;
}

const money = (v: string | number): string => `$${Number(v).toFixed(2)}`;

// Sales report modal (B5). Fetches `GET /pos/reports/sales` when opened. The
// launch button is gated by `inventory.reports`; this modal additionally renders
// a friendly message on a 403/network error instead of crashing.
export function SalesReportModal({ open, onClose }: Props) {
  const [report, setReport] = useState<SalesReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setReport(null);
    getSalesReport()
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load report");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
      onClick={onClose}
    >
      <div style={{ background: "#fff", borderRadius: 8, padding: 24, width: 420 }} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Sales Report</h2>

        {loading && <p style={{ fontSize: 14 }}>Loading…</p>}
        {error && (
          <p style={{ color: "#b91c1c", fontSize: 14 }}>
            {error === "Access denied" || error.includes("403")
              ? "You do not have permission to view the sales report."
              : error}
          </p>
        )}

        {report && (
          <>
            <table style={{ width: "100%", fontSize: 14, marginBottom: 12 }}>
              <tbody>
                <tr><td>Receipts</td><td style={{ textAlign: "right" }}>{report.receipt_count}</td></tr>
                <tr><td>Gross revenue</td><td style={{ textAlign: "right" }}>{money(report.gross_revenue)}</td></tr>
                <tr><td>Refunds</td><td style={{ textAlign: "right", color: "#b91c1c" }}>{money(report.refund_total)}</td></tr>
                <tr><td><strong>Net revenue</strong></td><td style={{ textAlign: "right", fontWeight: 700 }}>{money(report.net_revenue)}</td></tr>
              </tbody>
            </table>
            {Object.keys(report.by_payment_method).length > 0 && (
              <div style={{ background: "#f9fafb", borderRadius: 6, padding: 12, fontSize: 13 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>By payment method</div>
                {Object.entries(report.by_payment_method).map(([method, amt]) => (
                  <div key={method} style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{method}</span><span>{money(amt)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6 }}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
