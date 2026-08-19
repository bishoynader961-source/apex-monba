"use client";

import { useState } from "react";

import { ManagerApprovalDialog } from "@/components/ManagerApprovalDialog";
import { DiscrepanciesPanel } from "@/components/DiscrepanciesPanel";
import { closeShift, previewShift } from "@/lib/api/shift";
import { usePosStore } from "@/stores/posStore";

interface Props {
  open: boolean;
  onClose: () => void;
}

const VARIANCE_WARN = 2.0;

// Shift-close: a manager-authorised summary of the terminal session that
// reconciles the physically counted till against the system-expected cash (A1).
export function ShiftCloseDialog({ open, onClose }: Props) {
  const [approving, setApproving] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [counted, setCounted] = useState("");
  const [preview, setPreview] = useState<{ expected_cash: number } | null>(null);
  const [varianceGate, setVarianceGate] = useState(false);
  const [result, setResult] = useState<{
    expected_cash: number;
    counted_cash: number;
    variance: number;
    status: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const offlineCount = usePosStore((s) => s.offlineCount);
  const shiftId = usePosStore((s) => s.shiftId);
  const setShiftId = usePosStore((s) => s.setShiftId);

  if (!open) return null;

  if (!authorized) {
    return (
      <>
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 50 }}
          onClick={onClose}
        />
        <ManagerApprovalDialog
          open
          scope="shift.close"
          title="Manager approval to close shift"
          onClose={() => {
            setApproving(false);
            onClose();
          }}
          onApproved={() => setAuthorized(true)}
        />
      </>
    );
  }

  const countedNum = Number(counted);
  const expected = preview?.expected_cash ?? 0;
  const variance = preview ? Number((countedNum - expected).toFixed(2)) : 0;
  const isDiscrepancy = preview ? Math.abs(variance) > VARIANCE_WARN || variance < 0 : false;
  const canClose = preview !== null && !Number.isNaN(countedNum) && (!isDiscrepancy || varianceGate);

  const handleCalculate = async () => {
    setError(null);
    if (shiftId === null) {
      setError("No active shift on this terminal.");
      return;
    }
    try {
      const p = await previewShift(shiftId);
      setPreview({ expected_cash: Number(p.expected_cash) });
      setVarianceGate(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to preview shift");
    }
  };

  const handleClose = async () => {
    setError(null);
    if (shiftId === null) {
      setError("No active shift on this terminal.");
      return;
    }
    try {
      const r = await closeShift({ shift_id: shiftId, counted_cash: String(countedNum) });
      setResult({
        expected_cash: Number(r.expected_cash),
        counted_cash: Number(r.counted_cash),
        variance: Number(r.variance),
        status: r.status,
      });
      setShiftId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to close shift");
    }
  };

  if (result) {
    const bad = Math.abs(result.variance) > VARIANCE_WARN || result.variance < 0;
    return (
      <div
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
        onClick={onClose}
      >
        <div style={{ background: "#fff", borderRadius: 8, padding: 24, width: 420 }} onClick={(e) => e.stopPropagation()}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Shift Closed</h2>
          <table style={{ width: "100%", fontSize: 14, marginBottom: 12 }}>
            <tbody>
              <tr><td>Expected cash</td><td style={{ textAlign: "right" }}>${result.expected_cash.toFixed(2)}</td></tr>
              <tr><td>Counted cash</td><td style={{ textAlign: "right" }}>${result.counted_cash.toFixed(2)}</td></tr>
              <tr>
                <td>Variance</td>
                <td style={{ textAlign: "right", color: bad ? "#b91c1c" : "#16a34a", fontWeight: 700 }}>
                  ${result.variance.toFixed(2)}
                </td>
              </tr>
            </tbody>
          </table>
          {bad && (
            <p style={{ color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>
              Discrepancy recorded — a manager authorised this variance.
            </p>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={onClose} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6 }}>
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
      onClick={onClose}
    >
      <div style={{ background: "#fff", borderRadius: 8, padding: 24, width: 420 }} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Shift Close Summary</h2>
        <p style={{ fontSize: 14, marginBottom: 12 }}>
          {offlineCount > 0
            ? `${offlineCount} sale(s) are still queued offline and must sync before till reconciliation.`
            : "All sales are reconciled. You may close the shift."}
        </p>
        <div style={{ background: "#f9fafb", borderRadius: 6, padding: 12, marginBottom: 16 }}>
          <DiscrepanciesPanel />
        </div>

        <label style={{ fontSize: 13, display: "block", marginBottom: 4 }}>Counted cash ($)</label>
        <input
          type="number"
          step="0.01"
          value={counted}
          onChange={(e) => setCounted(e.target.value)}
          style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 6, marginBottom: 12 }}
        />

        {preview && (
          <div style={{ background: "#f0fdf4", borderRadius: 6, padding: 12, marginBottom: 12, fontSize: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Expected cash</span><span>${expected.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, color: isDiscrepancy ? "#b91c1c" : "#16a34a" }}>
              <span>Variance</span><span>${variance.toFixed(2)}</span>
            </div>
            {isDiscrepancy && !varianceGate && (
              <p style={{ color: "#b91c1c", fontSize: 13, marginTop: 8 }}>
                Variance exceeds tolerance or is negative — manager authorisation required.
              </p>
            )}
          </div>
        )}

        {error && <p style={{ color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          {preview === null ? (
            <button onClick={handleCalculate} style={{ padding: "0.5rem 1rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6 }}>
              Calculate
            </button>
          ) : isDiscrepancy && !varianceGate ? (
            <>
              <ManagerApprovalDialog
                open={approving}
                scope="shift.close.variance"
                title="Manager approval for till discrepancy"
                onClose={() => setApproving(false)}
                onApproved={() => {
                  setVarianceGate(true);
                  setApproving(false);
                }}
              />
              <button onClick={() => setApproving(true)} style={{ padding: "0.5rem 1rem", background: "#dc2626", color: "#fff", border: "none", borderRadius: 6 }}>
                Authorise discrepancy
              </button>
            </>
          ) : (
            <button
              onClick={handleClose}
              disabled={!canClose}
              style={{ padding: "0.5rem 1rem", background: canClose ? "#16a34a" : "#9ca3af", color: "#fff", border: "none", borderRadius: 6 }}
            >
              Close shift
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
