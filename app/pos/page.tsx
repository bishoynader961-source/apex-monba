/**
 * POS checkout page (Phase 3, decimal-safe).
 *
 * - Requires authentication (redirects to /login otherwise).
 * - A hidden, always-focused input captures barcode-wedge scans (R3). Each scan
 *   resolves the product by barcode and adds it to the cart via `usePosStore`.
 * - Money is handled with integer-cents math (lib/decimalCurrency) — never float.
 * - Checkout enqueues offline on failure and replays via the merge-sync hub.
 */
"use client";

// Force dynamic rendering: this is an authenticated, client-only POS terminal.
// Static prerender triggers a Node-SSR `location is not defined` quirk in
// Next's bundled script loader, which this avoids.
export const dynamic = "force-dynamic";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useBarcodeScanner } from "@/hooks/useBarcodeScanner";
import { parseMoney, formatMoney, mulByQty, sumMoney } from "@/lib/decimalCurrency";
import { searchMedicines } from "@/lib/api/inventory";
import { searchPatients } from "@/lib/api/patients";
import { parseSigCode, ndcLookup } from "@/lib/api/dictionaries";
import { dispense as dispenseApi } from "@/lib/api/dispense";
import { useAuthStore, useCan } from "@/stores/authStore";
import { usePosStore } from "@/stores/posStore";
import { ManagerApprovalDialog } from "@/components/ManagerApprovalDialog";
import { OfflineSyncBanner } from "@/components/OfflineSyncBanner";
import { RefundDialog } from "@/components/RefundDialog";
import { SalesReportModal } from "@/components/SalesReportModal";
import { ShiftCloseDialog } from "@/components/ShiftCloseDialog";
import type { DispenseRead, PatientRead, ProductRead, SigCodeParseResult } from "@/types/contracts";

export default function PosPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  const lines = usePosStore((s) => s.lines);
  const error = usePosStore((s) => s.error);
  const result = usePosStore((s) => s.result);
  const offlineCount = usePosStore((s) => s.offlineCount);
  const addLine = usePosStore((s) => s.addLine);
  const updateQty = usePosStore((s) => s.updateQty);
  const remove = usePosStore((s) => s.remove);
  const checkout = usePosStore((s) => s.checkout);
  const setError = usePosStore((s) => s.setError);
  const hydrate = usePosStore((s) => s.hydrate);
  const recordDrawer = usePosStore((s) => s.recordDrawer);
  const ensureShift = usePosStore((s) => s.ensureShift);
  const recoverable = usePosStore((s) => s.recoverable);
  const recoverCart = usePosStore((s) => s.recoverCart);
  const discardRecoverable = usePosStore((s) => s.discardRecoverable);

  // B5: permission-gated UI. `useCan` returns a stable boolean so these
  // components only re-render when the permission bit actually flips.
  const canRefund = useCan("pos.checkout");
  const canReports = useCan("inventory.reports");
  const canDispense = useCan("dispense.create");
  const [refundOpen, setRefundOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerAmount, setDrawerAmount] = useState("");
  const [drawerReason, setDrawerReason] = useState("");
  const [shiftOpen, setShiftOpen] = useState(false);

  // F5: Dispense / Rx integration — patient-link selector, SIG-code chip,
  // and a stable client_tx_id so retries don't double-deduct (LAN idempotency, #11).
  const [patientQuery, setPatientQuery] = useState("");
  const [patientResults, setPatientResults] = useState<PatientRead[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<PatientRead | null>(null);
  const [dispenseMode, setDispenseMode] = useState(false);
  const [sigResult, setSigResult] = useState<SigCodeParseResult | null>(null);
  const [dispenseError, setDispenseError] = useState<string | null>(null);
  const [dispenseResult, setDispenseResult] = useState<DispenseRead | null>(null);
  const [ndcError, setNdcError] = useState<string | null>(null);
  const clientTxIdRef = useRef<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const { scan: scanned } = useBarcodeScanner();

  // F5: Patient search debounce (300ms).
  const patientDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!patientQuery) {
      setPatientResults([]);
      return;
    }
    if (patientDebounceRef.current) clearTimeout(patientDebounceRef.current);
    patientDebounceRef.current = setTimeout(() => {
      void searchPatients(patientQuery)
        .then(setPatientResults)
        .catch(() => setPatientResults([]));
    }, 300);
    return () => {
      if (patientDebounceRef.current) clearTimeout(patientDebounceRef.current);
    };
  }, [patientQuery]);

  useEffect(() => {
    void hydrate();
    void ensureShift();
    inputRef.current?.focus();
    const onFocusLost = () => inputRef.current?.focus();
    window.addEventListener("focus", onFocusLost);
    return () => window.removeEventListener("focus", onFocusLost);
  }, [hydrate, ensureShift]);

  useEffect(() => {
    if (!scanned) return;
    void (async () => {
      setError(null);
      try {
        // F5: Try NDC lookup first (for prescription drugs not in POS catalog).
        // A (NDC fallback): if NDC returns found=false, surface inline "Add to Inventory?"
        // rather than silently blocking (see the ndcError state + inline action below).
        let product: ProductRead | null = null;
        try {
          const ndc = await ndcLookup(scanned);
          if (ndc.found && ndc.item) {
            // NDC found — treat as a matched medicine for the cart.
            product = {
              id: 0,
              name: ndc.item.drug_name ?? scanned,
              price: "0",
              manufacturer_barcode: ndc.q,
              internal_unique_barcode: "",
              status: "In Stock",
              expiry_date: ndc.item.expiration_date ?? "",
              manufacture_date: "",
              vendor_name: ndc.item.supplier ?? "",
              is_deleted: false,
            };
            // F5: In dispense mode, parse the barcode-as-SIG if it looks like a code.
            if (dispenseMode) {
              const sig = await parseSigCode(scanned);
              setSigResult(sig);
            }
          } else {
            // A: NDC not found in stock — fall back to medicine search, then
            // flag for inline "Add to Inventory?" action.
            setNdcError(scanned);
            const data = await searchMedicines(scanned);
            product = data[0] ?? null;
          }
        } catch {
          // NDC lookup failed/network error — fall back to medicine search.
          const data = await searchMedicines(scanned);
          product = data[0] ?? null;
        }

        if (!product) {
          setError(`No product found for barcode "${scanned}"`);
          return;
        }
        addLine(product);
        if (inputRef.current) {
          inputRef.current.value = "";
          inputRef.current.focus();
        }
      } catch (err: unknown) {
        setError((err instanceof Error && err.message) || "Lookup failed");
      }
    })();
  }, [scanned, addLine, setError, dispenseMode]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated()) return null;

  const net = formatMoney(
    sumMoney(lines.map((l) => mulByQty(parseMoney(l.unit_price), l.quantity))),
  );

  // F5: Dispense / Rx checkout. Generates a stable client_tx_id per submit
  // (LAN idempotency, #11) so a retry after network failure returns the cached
  // result instead of double-deducting stock.
  const handleDispenseCheckout = async () => {
    if (!selectedPatient || lines.length === 0) return;
    // Reuse the same tx_id across retries for this batch.
    if (!clientTxIdRef.current) clientTxIdRef.current = crypto.randomUUID();
    setDispenseError(null);
    setDispenseResult(null);
    try {
      const payload = {
        patient_id: selectedPatient.id,
        product_name: lines[0].product_name,
        ndc_code: "",
        sig_code: sigResult?.matched ? sigResult.code : "QD",
        quantity: lines.reduce((sum, l) => sum + l.quantity, 0),
        fill_date: new Date().toISOString().slice(0, 10),
        price_at_time: lines[0].unit_price,
        insurance_copay: "0",
        insurance_amount: "0",
        internal_barcode: "",
        cashier: useAuthStore.getState().user?.username ?? "",
        client_tx_id: clientTxIdRef.current,
      };
      const res = await dispenseApi(payload);
      setDispenseResult(res);
      setDispenseError(null);
      // Reset tx_id and SIG for the next transaction.
      clientTxIdRef.current = null;
      setSigResult(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Dispense failed";
      setDispenseError(msg);
      // Keep the same clientTxId across retries — do NOT reset clientTxIdRef.
    }
  };

  return (
    <main style={{ maxWidth: 780, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>POS Checkout</h1>
        <button onClick={() => logout()} style={{ fontSize: 13 }}>Logout</button>
      </header>

      <OfflineSyncBanner />

      {recoverable.length > 0 && (
        <div style={{ background: "#fef3c7", color: "#92400e", padding: "0.7rem 1rem", borderRadius: 6, marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <span>
            Recovered {recoverable.length} unsaved cart(s) from another terminal session (last active{" "}
            {new Date(recoverable[0].updatedAt).toLocaleTimeString()}).
          </span>
          <span style={{ display: "flex", gap: 8 }}>
            <button onClick={() => void recoverCart(recoverable[0].tabId)} style={{ padding: "0.4rem 0.8rem", background: "#d97706", color: "#fff", border: "none", borderRadius: 6 }}>
              Recover
            </button>
            <button onClick={() => void discardRecoverable(recoverable[0].tabId)} style={{ padding: "0.4rem 0.8rem", border: "1px solid #d1d5db", borderRadius: 6, background: "#fff" }}>
              Discard
            </button>
          </span>
        </div>
      )}

      <input
        ref={inputRef}
        type="text"
        autoComplete="off"
        style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
        tabIndex={-1}
      />
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>Scan a barcode — items auto-add to the cart.</p>

      {/* F5: Patient-link selector + Dispense / Rx toggle */}
      {canDispense && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <input
              type="text"
              placeholder="Search patient by name..."
              value={patientQuery}
              onChange={(e) => setPatientQuery(e.target.value)}
              style={{ flex: 1, padding: "6px 8px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6 }}
            />
            <button
              onClick={() => setDispenseMode(!dispenseMode)}
              style={{
                padding: "6px 12px",
                fontSize: 12,
                fontWeight: 600,
                border: "1px solid #d1d5db",
                borderRadius: 6,
                background: dispenseMode ? "#eff6ff" : "#fff",
                color: dispenseMode ? "#3b82f6" : "#6b7280",
                cursor: "pointer",
              }}
            >
              {dispenseMode ? "Rx Mode: ON" : "Rx Mode: OFF"}
            </button>
          </div>

          {patientResults.length > 0 && !selectedPatient && (
            <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, maxHeight: 120, overflowY: "auto", marginBottom: 4 }}>
              {patientResults.slice(0, 8).map((p) => (
                <div
                  key={p.id}
                  onClick={() => { setSelectedPatient(p); setPatientQuery(""); setPatientResults([]); }}
                  style={{ padding: "6px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f3f4f6" }}
                >
                  {p.name} — DOB: {p.dob} — {p.contact_phone || "no phone"}
                </div>
              ))}
            </div>
          )}

          {selectedPatient && (
            <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "8px 10px", background: "#eff6ff", borderRadius: 6, fontSize: 13 }}>
              <strong>Patient:</strong> {selectedPatient.name}
              <button onClick={() => setSelectedPatient(null)} style={{ marginLeft: "auto", color: "#dc2626", border: "none", background: "transparent", fontSize: 14, cursor: "pointer" }}>×</button>
            </div>
          )}

          {/* F5: SIG code chip — shows parsed instruction in dispense mode */}
          {sigResult?.matched && (
            <div style={{ padding: "6px 10px", background: "#dcfce8", borderRadius: 6, fontSize: 13, marginTop: 8 }}>
              SIG: <strong>{sigResult.code}</strong> → {sigResult.full_text}
            </div>
          )}

          {/* A: NDC not found in stock — inline "Add to Inventory?" action */}
          {ndcError && (
            <div style={{ padding: "8px 10px", background: "#fef3c7", borderRadius: 6, fontSize: 13, marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>NDC "{ndcError}" not found in stock.</span>
              <a
                href="/dashboard/inventory"
                style={{ color: "#3b82f6", fontSize: 12, fontWeight: 600 }}
                onClick={() => setNdcError(null)}
              >
                Add to Inventory?
              </a>
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{ background: "#fee2e2", color: "#991b2b", padding: "0.7rem 1rem", borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      <ul style={{ listStyle: "none", padding: 0, margin: 0, marginBottom: 16 }}>
        {lines.map((l) => (
          <li key={l.product_name} style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid #e5e7eb" }}>
            <div>
              <strong>{l.product_name}</strong> — ${formatMoney(parseMoney(l.unit_price))}
              <div style={{ fontSize: 12, color: "#6b7280" }}>qty: {l.quantity}</div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button onClick={() => updateQty(l.product_name, -1)}>-</button>
              <span>{l.quantity}</span>
              <button onClick={() => updateQty(l.product_name, 1)}>+</button>
              <button onClick={() => remove(l.product_name)} style={{ marginLeft: 8, color: "#dc2626" }}>×</button>
            </div>
          </li>
        ))}
      </ul>

      <footer style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setShiftOpen(true)} style={{ padding: "0.6rem 1rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}>
            Shift Close
          </button>
          <button onClick={() => setDrawerOpen(true)} style={{ padding: "0.6rem 1rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}>
            Cash Drop
          </button>
          {canRefund && (
            <button onClick={() => setRefundOpen(true)} style={{ padding: "0.6rem 1rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}>
              Refund
            </button>
          )}
          {canReports && (
            <button onClick={() => setReportOpen(true)} style={{ padding: "0.6rem 1rem", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}>
              Sales Report
            </button>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <strong style={{ fontSize: 18 }}>Total: ${net}</strong>
          {dispenseMode && selectedPatient && canDispense && (
            <button
              onClick={() => void handleDispenseCheckout()}
              disabled={lines.length === 0}
              style={{
                padding: "0.6rem 1.2rem",
                background: "#7c3aed",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 14,
                cursor: lines.length === 0 ? "default" : "pointer",
              }}
            >
              Dispense Rx
            </button>
          )}
          <button
            onClick={() => void checkout()}
            disabled={lines.length === 0}
            style={{
              padding: "0.6rem 1.2rem",
              background: "#16a34a",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 14,
              cursor: lines.length === 0 ? "default" : "pointer",
            }}
          >
            Checkout
          </button>
        </div>
      </footer>

      {drawerOpen && (
        <div style={{ background: "#f9fafb", borderRadius: 6, padding: 12, marginTop: 12 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>Cash Drawer Movement</h3>
          <label style={{ fontSize: 13 }}>Amount (positive = in, negative = out)</label>
          <input
            value={drawerAmount}
            onChange={(e) => setDrawerAmount(e.target.value)}
            inputMode="decimal"
            style={{ width: "100%", padding: 8, margin: "4px 0 8px", border: "1px solid #d1d5db", borderRadius: 6 }}
            placeholder="0.00"
          />
          <label style={{ fontSize: 13 }}>Reason</label>
          <input
            value={drawerReason}
            onChange={(e) => setDrawerReason(e.target.value)}
            style={{ width: "100%", padding: 8, margin: "4px 0 8px", border: "1px solid #d1d5db", borderRadius: 6 }}
          />
          <ManagerApprovalDialog
            open={drawerOpen}
            scope="drawer.move"
            title="Manager approval for cash drawer movement"
            onClose={() => setDrawerOpen(false)}
            onApproved={async (token) => {
              try {
                await recordDrawer(
                  { amount: drawerAmount || "0", reason: drawerReason || "cash drop" },
                  token,
                );
                setDrawerOpen(false);
                setDrawerAmount("");
                setDrawerReason("");
              } catch (err) {
                setError(err instanceof Error ? err.message : "Drawer movement failed");
              }
            }}
          />
        </div>
      )}

      <ShiftCloseDialog open={shiftOpen} onClose={() => setShiftOpen(false)} />
      <RefundDialog open={refundOpen} onClose={() => setRefundOpen(false)} />
      <SalesReportModal open={reportOpen} onClose={() => setReportOpen(false)} />

      {result && (
        <pre style={{ background: "#f3f4f6", padding: 12, borderRadius: 6, marginTop: 16, fontSize: 12, overflowX: "auto" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}

      {dispenseError && (
        <div style={{ background: "#fee2e2", color: "#991b2b", padding: "0.7rem 1rem", borderRadius: 6, marginTop: 12 }}>
          {dispenseError}
        </div>
      )}

      {dispenseResult?.allergy_flags && dispenseResult.allergy_flags.length > 0 && (
        <div style={{ background: "#fef3c7", color: "#92400e", padding: "0.7rem 1rem", borderRadius: 6, marginTop: 12, border: "1px solid #f59e0b" }}>
          <strong>Clinical Alert</strong>
          <ul style={{ margin: "0.25rem 0 0 1rem", paddingLeft: 0 }}>
            {dispenseResult.allergy_flags.map((flag: string, i: number) => (
              <li key={i}>{flag}</li>
            ))}
          </ul>
          <label style={{ display: "block", marginTop: 8, fontSize: 12 }}>
            <input type="checkbox" style={{ marginRight: 6 }} />
            Acknowledge — proceeding overrides the alert (logged to audit).
          </label>
        </div>
      )}

      {dispenseResult && (
        <pre style={{ background: "#dcfce8", padding: 12, borderRadius: 6, marginTop: 12, fontSize: 12, overflowX: "auto" }}>
          Dispense complete — ID: {dispenseResult.id} | Receipt: #{dispenseResult.receipt_id}
          {" "}
          {JSON.stringify(dispenseResult, null, 2)}
        </pre>
      )}
    </main>
  );
}
