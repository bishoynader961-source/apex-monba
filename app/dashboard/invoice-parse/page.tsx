"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  parseInvoiceText,
  parseInvoiceFile,
  getHardwareStatus,
  parseInvoiceHybrid,
  type ParsedItem,
  type HardwareStatus,
  type HybridParseResponse,
  type HybridLineItem,
} from "@/lib/api/invoiceParse";
import { OcrUploadDropzone } from "@/components/OcrUploadDropzone";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useRouter } from "next/navigation";
import {
  FileText,
  Upload,
  ScanLine,
  Cpu,
  AlertTriangle,
  CheckCircle,
  Loader2,
  UploadCloud,
  X,
  Gauge,
  Table,
} from "lucide-react";

const INPUT_STYLE =
  "w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono resize-y";

const TIER_COLORS: Record<string, string> = {
  capable: "text-green-400 bg-green-400/10 border-green-500/30",
  constrained: "text-amber-400 bg-amber-400/10 border-amber-500/30",
  incompatible: "text-red-400 bg-red-400/10 border-red-500/30",
};

const TIER_LABELS: Record<string, string> = {
  capable: "Capable",
  constrained: "Constrained",
  incompatible: "Incompatible",
};

export default function InvoiceParsePage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canWrite = useCan("inventory.write");

  const [text, setText] = useState("");
  const [items, setItems] = useState<ParsedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"text" | "file" | "ocr" | "hybrid">("text");
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Hybrid OCR state ──
  const [hwStatus, setHwStatus] = useState<HardwareStatus | null>(null);
  const [hwLoading, setHwLoading] = useState(false);
  const [hybridMode, setHybridMode] = useState<"auto" | "hybrid" | "tesseract_only">("auto");
  const [hybridResult, setHybridResult] = useState<HybridParseResponse | null>(null);
  const [hybridLoading, setHybridLoading] = useState(false);
  const [hybridDragging, setHybridDragging] = useState(false);
  const [hybridFile, setHybridFile] = useState<File | null>(null);
  const hybridInputRef = useRef<HTMLInputElement>(null);

  if (!isAuthenticated()) {
    if (typeof window !== "undefined") router.replace("/login");
    return null;
  }

  // ── Fetch hardware status when hybrid tab is selected ──
  const fetchHardwareStatus = useCallback(async () => {
    if (hwStatus) return;
    setHwLoading(true);
    try {
      const status = await getHardwareStatus();
      setHwStatus(status);
      setHybridMode(status.recommended_mode);
    } catch {
      // Silently handle — user can still try hybrid OCR
    } finally {
      setHwLoading(false);
    }
  }, [hwStatus]);

  useEffect(() => {
    if (activeTab === "hybrid") {
      void fetchHardwareStatus();
    }
  }, [activeTab, fetchHardwareStatus]);

  // ── Existing handlers ──
  const handleParseText = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await parseInvoiceText(text);
      setItems(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parse failed");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await parseInvoiceFile(file);
      setItems(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parse failed");
    } finally {
      setLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleOcrExtract = (result: { text: string; confidence: number; needs_review: boolean }) => {
    setText(result.text);
    if (result.text.trim()) {
      setLoading(true);
      parseInvoiceText(result.text)
        .then((res) => setItems(res.items))
        .catch((err) => setError(err instanceof Error ? err.message : "Parse failed"))
        .finally(() => setLoading(false));
    }
  };

  // ── Hybrid OCR handlers ──
  const handleHybridUpload = useCallback(async (file: File) => {
    if (!file.type.startsWith("image/")) {
      setError("Please upload an image file (PNG, JPG, TIFF).");
      return;
    }
    setHybridFile(file);
    setHybridLoading(true);
    setError(null);
    setHybridResult(null);
    try {
      const res = await parseInvoiceHybrid(file, hybridMode);
      setHybridResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hybrid OCR failed");
    } finally {
      setHybridLoading(false);
    }
  }, [hybridMode]);

  const handleHybridDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setHybridDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        void handleHybridUpload(e.dataTransfer.files[0]);
      }
    },
    [handleHybridUpload],
  );

  const handleHybridDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setHybridDragging(true);
  }, []);

  const handleHybridDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setHybridDragging(false);
  }, []);

  const handleHybridFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleHybridUpload(file);
    },
    [handleHybridUpload],
  );

  // ── Tabs ──
  const tabs = [
    { key: "text" as const, label: "Paste Text", icon: FileText },
    { key: "file" as const, label: "Upload File", icon: Upload },
    { key: "ocr" as const, label: "Scan Image", icon: ScanLine },
    { key: "hybrid" as const, label: "Hybrid OCR", icon: Cpu },
  ];

  return (
    <DashboardLayout>
      <RouteGuard permission="invoiceParse.read">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <FileText className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Invoice Parser</h1>
        </div>

        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Paste invoice text, upload a file, scan an image, or use the hybrid OCR pipeline to extract medication data into your inventory.
        </p>

        {/* Tab Bar */}
        <div className="flex gap-1 mb-4 bg-[#1a1a2e] border border-gray-800 rounded-lg p-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 flex-1 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5">
          {/* ── Text Tab ── */}
          {activeTab === "text" && (
            <div className="space-y-4">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={"Paste invoice text here...\n\nExample:\n1. Amoxicillin 500mg Capsules\n   Qty: 100 boxes\n   Batch: AMX-2026-X8\n   Expiry: 2028-12-01"}
                rows={8}
                className={INPUT_STYLE}
              />
              <button
                onClick={() => void handleParseText()}
                disabled={loading || !text.trim()}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
              >
                {loading ? "Parsing..." : "Parse Text"}
              </button>
            </div>
          )}

          {/* ── File Tab ── */}
          {activeTab === "file" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">Upload a .txt or .csv invoice file to extract medication data.</p>
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.csv"
                onChange={() => void handleFileUpload}
                className="hidden"
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Upload className="w-4 h-4" />
                {loading ? "Uploading..." : "Choose File"}
              </button>
            </div>
          )}

          {/* ── OCR Tab ── */}
          {activeTab === "ocr" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Drag and drop an invoice image. The 4-tier OCR cascade will automatically extract text with confidence scoring.
              </p>
              <OcrUploadDropzone onExtract={handleOcrExtract} />
            </div>
          )}

          {/* ── Hybrid OCR Tab ── */}
          {activeTab === "hybrid" && (
            <div className="space-y-5">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Hardware-aware dual-engine OCR. PaddleOCR extracts tabular line items (GPU-accelerated) while Tesseract grabs flat metadata (CPU). The system auto-selects the best mode based on your hardware.
              </p>

              {/* Hardware Status Card */}
              {hwLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Evaluating hardware...
                </div>
              ) : hwStatus ? (
                <div className="bg-[#0d0d20] border border-gray-800 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Gauge className="w-4 h-4 text-blue-500" />
                      <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Hardware Profile</h4>
                    </div>
                    <span className={`px-2.5 py-0.5 text-xs font-medium rounded-full border ${TIER_COLORS[hwStatus.tier]}`}>
                      {TIER_LABELS[hwStatus.tier]}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-gray-500">GPU</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">
                        {hwStatus.gpu_available ? hwStatus.gpu_name || "Detected" : "None"}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">VRAM</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">{hwStatus.gpu_vram_gb.toFixed(1)} GB</p>
                    </div>
                    <div>
                      <span className="text-gray-500">RAM</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">{hwStatus.ram_total_gb.toFixed(1)} GB</p>
                    </div>
                    <div>
                      <span className="text-gray-500">CPU Threads</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">{hwStatus.cpu_threads}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <AlertTriangle className="w-3 h-3" />
                  Could not detect hardware. OCR will use CPU-only mode.
                </div>
              )}

              {/* Mode Selector */}
              <div className="space-y-2">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">OCR Mode</span>
                <div className="flex gap-2">
                  {(["auto", "hybrid", "tesseract_only"] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setHybridMode(m)}
                      className={`flex-1 px-3 py-2 rounded-md text-xs font-medium border transition-colors ${
                        hybridMode === m
                          ? "bg-blue-600 border-blue-500 text-white"
                          : "border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                      }`}
                    >
                      {m === "auto" && "Auto (Recommended)"}
                      {m === "hybrid" && "Hybrid (Both Engines)"}
                      {m === "tesseract_only" && "Tesseract Only (Fast)"}
                    </button>
                  ))}
                </div>
                {hwStatus?.tier === "constrained" && hybridMode === "hybrid" && (
                  <div className="flex items-start gap-2 px-3 py-2 bg-amber-400/10 border border-amber-500/30 rounded-md text-xs text-amber-400">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    <span>
                      Running full hybrid OCR on constrained hardware will consume high CPU/RAM resources.
                      Do not run other heavy applications concurrently.
                    </span>
                  </div>
                )}
              </div>

              {/* Upload Zone */}
              <div
                className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center transition-colors ${
                  hybridDragging
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-gray-700 hover:border-gray-500 bg-[#0d0d20]"
                }`}
                onDragOver={handleHybridDragOver}
                onDragLeave={handleHybridDragLeave}
                onDrop={handleHybridDrop}
              >
                <input
                  ref={hybridInputRef}
                  type="file"
                  accept="image/*"
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  onChange={handleHybridFileInput}
                  disabled={hybridLoading}
                />

                {hybridLoading ? (
                  <div className="flex flex-col items-center text-blue-400">
                    <Loader2 className="w-10 h-10 mb-4 animate-spin" />
                    <p className="text-sm font-medium">Running hybrid OCR pipeline...</p>
                    <p className="text-xs text-gray-500 mt-1">Evaluating hardware + extracting data</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center text-gray-600 dark:text-gray-400">
                    <UploadCloud className="w-10 h-10 mb-4 text-gray-500" />
                    <p className="text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                      Drag & Drop Invoice Image
                    </p>
                    <p className="text-xs">or click to browse files</p>
                  </div>
                )}
              </div>

              {/* Hybrid OCR Result */}
              {hybridResult && (
                <div className="bg-[#0d0d20] border border-gray-800 rounded-lg p-4 space-y-4">
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Cpu className="w-4 h-4 text-blue-500" />
                      <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Hybrid OCR Result</h4>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>Engines: {hybridResult.engines_used.join(" + ")}</span>
                      <span>{hybridResult.processing_time_ms.toFixed(0)}ms</span>
                    </div>
                  </div>

                  {/* Confidence */}
                  <div className="grid grid-cols-3 gap-3">
                    {(["tesseract", "paddleocr", "overall"] as const).map((key) => (
                      <div key={key} className="text-center">
                        <span className="text-xs text-gray-500 capitalize">{key}</span>
                        <div className="mt-1">
                          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                hybridResult.confidence[key] >= 0.7
                                  ? "bg-green-500"
                                  : hybridResult.confidence[key] >= 0.4
                                    ? "bg-amber-500"
                                    : "bg-red-500"
                              }`}
                              style={{ width: `${Math.round(hybridResult.confidence[key] * 100)}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono text-gray-600 dark:text-gray-400">
                            {Math.round(hybridResult.confidence[key] * 100)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Invoice Metadata */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-gray-500">Invoice #</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">
                        {hybridResult.invoice_number || "—"}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Total</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">
                        {hybridResult.total_amount != null
                          ? `$${hybridResult.total_amount.toFixed(2)}`
                          : "—"}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Vendor</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">
                        {hybridResult.metadata.vendor || "—"}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Date</span>
                      <p className="text-gray-800 dark:text-gray-200 font-medium mt-0.5">
                        {hybridResult.metadata.date || "—"}
                      </p>
                    </div>
                  </div>

                  {/* Line Items Table */}
                  {hybridResult.line_items.length > 0 && (
                    <div>
                      <h5 className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                        Line Items ({hybridResult.line_items.length})
                      </h5>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-gray-800">
                              <th className="text-left px-3 py-1.5 text-gray-600 dark:text-gray-400 font-medium">Description</th>
                              <th className="text-right px-3 py-1.5 text-gray-600 dark:text-gray-400 font-medium">Qty</th>
                              <th className="text-right px-3 py-1.5 text-gray-600 dark:text-gray-400 font-medium">Unit Price</th>
                            </tr>
                          </thead>
                          <tbody>
                            {hybridResult.line_items.map((item, i) => (
                              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                                <td className="px-3 py-1.5 text-gray-800 dark:text-gray-100">{item.description}</td>
                                <td className="px-3 py-1.5 text-right text-gray-700 dark:text-gray-300">{item.quantity}</td>
                                <td className="px-3 py-1.5 text-right text-gray-700 dark:text-gray-300">${item.unit_price.toFixed(2)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Warnings */}
                  {hybridResult.warnings.length > 0 && (
                    <div className="space-y-1.5">
                      {hybridResult.warnings.map((w, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 px-3 py-2 bg-amber-400/10 border border-amber-500/30 rounded-md text-xs text-amber-400"
                        >
                          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Raw Text */}
                  {hybridResult.raw_text && (
                    <details className="group">
                      <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
                        View raw OCR text
                      </summary>
                      <pre className="mt-2 text-xs text-gray-600 dark:text-gray-400 bg-[#0a0a1a] rounded p-3 overflow-x-auto max-h-40 whitespace-pre-wrap">
                        {hybridResult.raw_text}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Error Display ── */}
          {error && (
            <div className="mt-4 px-4 py-2.5 bg-red-600/15 border border-red-600/30 text-red-400 rounded-lg text-sm flex justify-between items-center">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-xs">Dismiss</button>
            </div>
          )}
        </div>

        {/* ── Parsed Items Table (shared across text/file/ocr tabs) ── */}
        {items.length > 0 && (
          <div className="mt-6 bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Table className="w-4 h-4 text-green-500" />
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                  {items.length} item{items.length !== 1 ? "s" : ""} extracted
                </h3>
              </div>
              {canWrite && (
                <button
                  type="button"
                  onClick={() => alert("Import to Inventory not implemented yet")}
                  className="px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-md text-xs font-medium transition-colors"
                >
                  Import to Inventory
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Product</th>
                    <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Ingredient</th>
                    <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Dosage</th>
                    <th className="text-right px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Qty</th>
                    <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Batch</th>
                    <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Expiry</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => (
                    <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                      <td className="px-5 py-2.5 text-gray-800 dark:text-gray-100 font-medium">{item.product_name}</td>
                      <td className="px-5 py-2.5 text-gray-700 dark:text-gray-300">{item.active_ingredient}</td>
                      <td className="px-5 py-2.5 text-gray-700 dark:text-gray-300">{item.dosage_concentration}</td>
                      <td className="px-5 py-2.5 text-right text-gray-700 dark:text-gray-300">{item.quantity_received}</td>
                      <td className="px-5 py-2.5 font-mono text-gray-700 dark:text-gray-300">{item.batch_number}</td>
                      <td className="px-5 py-2.5 text-gray-700 dark:text-gray-300">{item.expiration_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}
