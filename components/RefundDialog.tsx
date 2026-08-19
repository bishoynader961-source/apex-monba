"use client";

import { useState } from "react";

import { refundSale } from "@/lib/api/pos";

interface Props {
  open: boolean;
  onClose: () => void;
}

// Refund dialog (B5). Permission-gated by the caller (the button is only shown
// when the user holds `pos.checkout`), so this dialog just performs the action
// and renders server errors verbatim from the uniform error contract.
export function RefundDialog({ open, onClose }: Props) {
  const [receiptId, setReceiptId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ id: number; total_amount: number } | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const handleRefund = async () => {
    setError(null);
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) {
      setError("Enter a valid receipt id");
      return;
    }
    setBusy(true);
    try {
      const r = await refundSale({ receipt_id: id, reason: reason || null });
      setResult({ id: r.id, total_amount: Number(r.total_amount) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refund failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
      onClick={onClose}
    >
      <div style={{ background: "#fff", borderRadius: 8, padding: 24, width: 380 }} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Refund Sale</h2>

        {result ? (
          <>
            <p style={{ fontSize: 14, marginBottom: 12 }}>
              Refund <strong>#{result.id}</strong> recorded for{" "}
              <strong style={{ color: "#b91c1c" }}>${result.total_amount.toFixed(2)}</strong>.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button onClick={onClose} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6 }}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <label style={{ fontSize: 13, display: "block", marginBottom: 4 }}>Receipt ID</label>
            <input
              type="number"
              value={receiptId}
              onChange={(e) => setReceiptId(e.target.value)}
              style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 6, marginBottom: 12 }}
              placeholder="e.g. 12"
            />
            <label style={{ fontSize: 13, display: "block", marginBottom: 4 }}>Reason (optional)</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 6, marginBottom: 12 }}
            />
            {error && <p style={{ color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>{error}</p>}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={onClose} style={{ padding: "0.5rem 1rem", border: "1px solid #d1d5db", borderRadius: 6, background: "#fff" }}>
                Cancel
              </button>
              <button
                onClick={handleRefund}
                disabled={busy}
                style={{ padding: "0.5rem 1rem", background: busy ? "#9ca3af" : "#dc2626", color: "#fff", border: "none", borderRadius: 6 }}
              >
                {busy ? "Processing…" : "Issue refund"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
