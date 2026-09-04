"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Printer } from "lucide-react";

/**
 * Label Print Preview route — /print-label
 *
 * Accepts query params:
 *   ?name=<drug name>
 *   &barcode=<internal_unique_barcode>
 *   &vendor=<vendor name>
 *   &expiry=<YYYY-MM-DD>
 *   &price=<price>
 *   &pharmacy=<pharmacy name>
 *
 * Renders a precise thermal-label layout (2×1 in) styled with @media print CSS.
 * Tauri can open this route in a native window for pixel-perfect hardware printing.
 */

function LabelContent() {
  const params = useSearchParams();
  const name = params.get("name") ?? "Unknown Drug";
  const barcode = params.get("barcode") ?? "";
  const vendor = params.get("vendor") ?? "";
  const expiry = params.get("expiry") ?? "";
  const price = params.get("price") ?? "";
  const pharmacy = params.get("pharmacy") ?? "Pharmacy Suite";

  const handlePrint = () => window.print();

  return (
    <>
      {/* Print Controls — hidden in print mode */}
      <div className="no-print fixed top-4 right-4 z-50 flex gap-3">
        <button
          id="btn-print-label"
          onClick={handlePrint}
          className="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium shadow-lg transition-colors text-sm"
        >
          <Printer className="w-4 h-4" />
          Print Label
        </button>
      </div>

      {/* Screen preview wrapper — centers the label on screen */}
      <div className="no-print min-h-screen bg-gray-900 flex items-center justify-center p-10">
        <div className="bg-white rounded shadow-2xl" style={{ width: "2in", padding: "0.05in" }}>
          <LabelBody
            name={name}
            barcode={barcode}
            vendor={vendor}
            expiry={expiry}
            price={price}
            pharmacy={pharmacy}
          />
        </div>
      </div>

      {/* Print-only label — rendered directly at the top of the page for the printer */}
      <div className="print-only">
        <LabelBody
          name={name}
          barcode={barcode}
          vendor={vendor}
          expiry={expiry}
          price={price}
          pharmacy={pharmacy}
        />
      </div>

      <style>{`
        /* Thermal label: 2in × 1in */
        @media print {
          @page {
            size: 2in 1in;
            margin: 0;
          }
          html, body {
            margin: 0;
            padding: 0;
            background: white;
          }
          .no-print { display: none !important; }
          .print-only { display: block !important; }
        }
        .print-only { display: none; }
      `}</style>
    </>
  );
}

interface LabelBodyProps {
  name: string;
  barcode: string;
  vendor: string;
  expiry: string;
  price: string;
  pharmacy: string;
}

function LabelBody({ name, barcode, vendor, expiry, price, pharmacy }: LabelBodyProps) {
  return (
    <div
      style={{
        width: "2in",
        height: "1in",
        fontFamily: "Arial, Helvetica, sans-serif",
        fontSize: "7pt",
        color: "#000",
        padding: "0.05in",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        overflow: "hidden",
        background: "white",
      }}
    >
      {/* Pharmacy header */}
      <div style={{ textAlign: "center", borderBottom: "0.5pt solid #000", paddingBottom: "2pt", marginBottom: "2pt" }}>
        <span style={{ fontWeight: "bold", fontSize: "7.5pt", letterSpacing: "0.3pt" }}>{pharmacy}</span>
      </div>

      {/* Drug name */}
      <div style={{ fontWeight: "bold", fontSize: "8pt", lineHeight: 1.2, maxHeight: "18pt", overflow: "hidden" }}>
        {name}
      </div>

      {/* Barcode representation — text fallback (real barcode rendering needs a lib) */}
      <div style={{ textAlign: "center", margin: "2pt 0" }}>
        <div style={{
          fontFamily: "monospace",
          fontSize: "11pt",
          letterSpacing: "1.5pt",
          lineHeight: 1,
          border: "0.5pt solid #888",
          padding: "1pt 2pt",
          display: "inline-block",
          background: "#fff",
        }}>
          ||||| {barcode} |||||
        </div>
        <div style={{ fontSize: "5.5pt", letterSpacing: "0.5pt", marginTop: "1pt", color: "#333" }}>
          {barcode}
        </div>
      </div>

      {/* Footer meta */}
      <div style={{ display: "flex", justifyContent: "space-between", borderTop: "0.5pt solid #ccc", paddingTop: "2pt" }}>
        {vendor && <span>Vendor: {vendor}</span>}
        {expiry && <span>Exp: {expiry}</span>}
        {price && <span>${parseFloat(price).toFixed(2)}</span>}
      </div>
    </div>
  );
}

export default function LabelPrintPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gray-900 flex items-center justify-center text-gray-400">
        Loading label…
      </div>
    }>
      <LabelContent />
    </Suspense>
  );
}
