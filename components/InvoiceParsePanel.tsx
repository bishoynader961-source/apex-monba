"use client";

import { useState, useRef } from "react";
import { parseInvoiceText, parseInvoiceFile, type ParsedItem } from "@/lib/api/invoiceParse";
import { recognizeText } from "@/lib/ocr";

interface Props {
  onItemsParsed?: (items: ParsedItem[]) => void;
}

export default function InvoiceParsePanel({ onItemsParsed }: Props) {
  const [text, setText] = useState("");
  const [items, setItems] = useState<ParsedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ocrProgress, setOcrProgress] = useState<number | null>(null);
  const [ocrResult, setOcrResult] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);

  const handleParseText = async () => {
    if (!text.trim()) return;
    setLoading(true); setError(null);
    try {
      const res = await parseInvoiceText(text);
      setItems(res.items);
      onItemsParsed?.(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parse failed");
    }
    setLoading(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true); setError(null);
    try {
      const res = await parseInvoiceFile(file);
      setItems(res.items);
      onItemsParsed?.(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parse failed");
    }
    setLoading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleOcrUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true); setError(null); setOcrProgress(0); setOcrResult(null);
    try {
      const result = await recognizeText(file, (p) => setOcrProgress(p));
      setOcrResult(result.text);
      setText(result.text);
      setOcrProgress(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OCR failed");
      setOcrProgress(null);
    }
    setLoading(false);
    if (imageRef.current) imageRef.current.value = "";
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 16, background: "var(--bg-card)" }}>
      <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "var(--fg)" }}>Invoice Parser</h3>
      <p style={{ fontSize: 12, color: "var(--fg-muted)", marginBottom: 8 }}>
        Paste invoice text, upload a .txt/.csv file, or scan an image (OCR) to extract medication data.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"Paste invoice text here...\n\nExample:\n1. Amoxicillin 500mg Capsules\n   Qty: 100 boxes\n   Batch: AMX-2026-X8\n   Expiry: 2028-12-01"}
        rows={6}
        style={{ width: "100%", padding: 8, fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, fontFamily: "monospace", resize: "vertical", background: "var(--bg-input)", color: "var(--fg)", boxSizing: "border-box" as const }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button
          onClick={() => void handleParseText()}
          disabled={loading || !text.trim()}
          style={{ padding: "6px 14px", fontSize: 12, background: "var(--primary)", color: "var(--primary-fg)", border: "none", borderRadius: 4, cursor: loading ? "wait" : "pointer", opacity: loading || !text.trim() ? 0.6 : 1 }}
        >
          {loading ? "Parsing..." : "Parse Text"}
        </button>
        <span style={{ fontSize: 12, color: "var(--fg-muted)" }}>or</span>
        <input ref={fileRef} type="file" accept=".txt,.csv" onChange={() => void handleFileUpload} style={{ display: "none" }} />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={loading}
          style={{ padding: "6px 14px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, cursor: loading ? "wait" : "pointer", background: "var(--bg-input)", color: "var(--fg)" }}
        >
          Upload File
        </button>
        <span style={{ fontSize: 12, color: "var(--fg-muted)" }}>or</span>
        <input ref={imageRef} type="file" accept="image/*" onChange={() => void handleOcrUpload} style={{ display: "none" }} />
        <button
          onClick={() => imageRef.current?.click()}
          disabled={loading}
          style={{ padding: "6px 14px", fontSize: 12, border: "1px solid var(--primary)", borderRadius: 4, cursor: loading ? "wait" : "pointer", background: "var(--bg-input)", color: "var(--primary)" }}
        >
          {ocrProgress !== null ? `Scanning... ${ocrProgress}%` : "Scan Image (OCR)"}
        </button>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--danger)", marginTop: 6 }}>{error}</div>}
      {ocrResult && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 12, color: "var(--fg-muted)", cursor: "pointer" }}>View OCR extracted text</summary>
          <pre style={{ fontSize: 11, padding: 8, background: "var(--bg-input)", border: "1px solid var(--border)", borderRadius: 4, marginTop: 4, whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto", color: "var(--fg)" }}>{ocrResult}</pre>
        </details>
      )}
      {items.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "var(--success)", marginBottom: 6 }}>{items.length} item(s) parsed</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={{ textAlign: "left", padding: "4px 6px", color: "var(--fg-muted)" }}>Product</th>
                  <th style={{ textAlign: "left", padding: "4px 6px", color: "var(--fg-muted)" }}>Ingredient</th>
                  <th style={{ textAlign: "left", padding: "4px 6px", color: "var(--fg-muted)" }}>Dosage</th>
                  <th style={{ textAlign: "right", padding: "4px 6px", color: "var(--fg-muted)" }}>Qty</th>
                  <th style={{ textAlign: "left", padding: "4px 6px", color: "var(--fg-muted)" }}>Batch</th>
                  <th style={{ textAlign: "left", padding: "4px 6px", color: "var(--fg-muted)" }}>Expiry</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "4px 6px", fontWeight: 600, color: "var(--fg)" }}>{item.product_name}</td>
                    <td style={{ padding: "4px 6px", color: "var(--fg)" }}>{item.active_ingredient}</td>
                    <td style={{ padding: "4px 6px", color: "var(--fg)" }}>{item.dosage_concentration}</td>
                    <td style={{ padding: "4px 6px", textAlign: "right", color: "var(--fg)" }}>{item.quantity_received}</td>
                    <td style={{ padding: "4px 6px", fontFamily: "monospace", color: "var(--fg)" }}>{item.batch_number}</td>
                    <td style={{ padding: "4px 6px", color: "var(--fg)" }}>{item.expiration_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
