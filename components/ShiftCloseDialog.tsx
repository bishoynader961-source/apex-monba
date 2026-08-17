"use client";

import { useState } from "react";

import { ManagerApprovalDialog } from "@/components/ManagerApprovalDialog";
import { DiscrepanciesPanel } from "@/components/DiscrepanciesPanel";
import { usePosStore } from "@/stores/posStore";

interface Props {
  open: boolean;
  onClose: () => void;
}

// Shift-close: a manager-authorised summary of the terminal session, surfacing
// pending offline sales that must reconcile before the till is closed.
export function ShiftCloseDialog({ open, onClose }: Props) {
  const [approving, setApproving] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const offlineCount = usePosStore((s) => s.offlineCount);

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
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6 }}>
            Close shift
          </button>
        </div>
      </div>
    </div>
  );
}
