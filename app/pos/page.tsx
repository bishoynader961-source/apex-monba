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
import { useEffect, useRef } from "react";

import { useBarcodeScanner } from "@/hooks/useBarcodeScanner";
import { parseMoney, formatMoney, mulByQty, sumMoney } from "@/lib/decimalCurrency";
import { searchMedicines } from "@/lib/api/inventory";
import { useAuthStore } from "@/stores/authStore";
import { usePosStore } from "@/stores/posStore";
import { ManagerApprovalDialog } from "@/components/ManagerApprovalDialog";
import { OfflineSyncBanner } from "@/components/OfflineSyncBanner";
import { ShiftCloseDialog } from "@/components/ShiftCloseDialog";
import type { ProductRead } from "@/types/contracts";
import { useState } from "react";

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

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerAmount, setDrawerAmount] = useState("");
  const [drawerReason, setDrawerReason] = useState("");
  const [shiftOpen, setShiftOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const { scan: scanned } = useBarcodeScanner();

  useEffect(() => {
    void hydrate();
    inputRef.current?.focus();
    const onFocusLost = () => inputRef.current?.focus();
    window.addEventListener("focus", onFocusLost);
    return () => window.removeEventListener("focus", onFocusLost);
  }, [hydrate]);

  useEffect(() => {
    if (!scanned) return;
    void (async () => {
      setError(null);
      try {
        const data = await searchMedicines(scanned);
        const product = data[0] ?? null;
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
  }, [scanned, addLine, setError]);

  if (!isAuthenticated()) {
    router.replace("/login");
    return null;
  }

  const net = formatMoney(
    sumMoney(lines.map((l) => mulByQty(parseMoney(l.unit_price), l.quantity))),
  );

  return (
    <main style={{ maxWidth: 780, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>POS Checkout</h1>
        <button onClick={() => logout()} style={{ fontSize: 13 }}>Logout</button>
      </header>

      <OfflineSyncBanner />

      <input
        ref={inputRef}
        type="text"
        autoComplete="off"
        style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
        tabIndex={-1}
      />
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>Scan a barcode — items auto-add to the cart.</p>

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
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <strong style={{ fontSize: 18 }}>Total: ${net}</strong>
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

      {result && (
        <pre style={{ background: "#f3f4f6", padding: 12, borderRadius: 6, marginTop: 16, fontSize: 12, overflowX: "auto" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </main>
  );
}
