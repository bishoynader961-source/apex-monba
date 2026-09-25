"use client";

import { useState, useRef, useCallback } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useRouter } from "next/navigation";
import { RouteGuard } from "@/components/RouteGuard";
import {
  analyzeImport,
  previewImport,
  commitImport,
  exportInventoryExcel,
} from "@/lib/api/excel";
import type {
  ExcelImportAnalyzeResult,
  ExcelImportDbField,
  ExcelImportCommitResult,
} from "@/types/contracts";
import {
  Upload,
  Download,
  FileSpreadsheet,
  FileText,
  CheckCircle,
  AlertTriangle,
  X,
  ChevronRight,
  ChevronLeft,
  Eye,
  Check,
  ArrowRight,
} from "lucide-react";

const STEP_DEFS = [
  { key: "upload", label: "Upload", icon: Upload },
  { key: "map", label: "Map Columns", icon: ArrowRight },
  { key: "validate", label: "Preview", icon: Eye },
  { key: "import", label: "Import", icon: Check },
] as const;

type StepKey = (typeof STEP_DEFS)[number]["key"];

const INPUT_STYLE =
  "w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm";

export default function BulkImportPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
const canRead = useCan("bulkImport.read");
const canWrite = useCan("inventory.write");

  const [step, setStep] = useState<StepKey>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [analyze, setAnalyze] = useState<ExcelImportAnalyzeResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[] | null>(null);
  const [importResult, setImportResult] = useState<ExcelImportCommitResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const stepIdx = STEP_DEFS.findIndex((s) => s.key === step);

  if (!isAuthenticated()) {
    if (typeof window !== "undefined") router.replace("/login");
    return null;
  }

  const resetWizard = () => {
    setStep("upload");
    setFile(null);
    setAnalyze(null);
    setMapping({});
    setDefaults({});
    setPreviewRows(null);
    setImportResult(null);
    setError(null);
  };

  const handleFile = useCallback(async (f: File) => {
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!["csv", "xlsx", "xls"].includes(ext ?? "")) {
      setError("Unsupported file type. Please use .csv, .xlsx, or .xls files.");
      return;
    }
    setFile(f);
    setError(null);
    setLoading(true);
    try {
      const result = await analyzeImport(f);
      setAnalyze(result);
      setMapping(result.mapping);
      const defs: Record<string, string> = {};
      result.db_fields.forEach((field: ExcelImportDbField) => {
        if (field.default !== null && field.default !== undefined) {
          defs[field.key] = String(field.default);
        }
      });
      setDefaults(defs);
      setStep("map");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze file");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) void handleFile(f);
    },
    [handleFile]
  );

  const handlePreview = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await previewImport(file, mapping, defaults, 10);
      setPreviewRows(result.rows);
      setStep("validate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await commitImport(file, mapping, defaults);
      setImportResult(result);
      setStep("import");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    try {
      const blob = await exportInventoryExcel();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `inventory_export_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  };

  const handleMapChange = (dbField: string, colIdx: number) => {
    setMapping((prev) => ({ ...prev, [dbField]: colIdx }));
  };

  const handleUnmap = (dbField: string) => {
    setMapping((prev) => {
      const next = { ...prev };
      delete next[dbField];
      return next;
    });
  };

  const requiredFields = analyze?.db_fields.filter((f) => f.required) ?? [];
  const optionalFields = analyze?.db_fields.filter((f) => !f.required) ?? [];
  const mappedRequired = requiredFields.filter((f) => mapping[f.key] !== undefined);
  const allRequiredMapped = mappedRequired.length === requiredFields.length;

  return (
    <DashboardLayout>
      <RouteGuard permission="bulkImport.read">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <FileSpreadsheet className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Smart Import Wizard</h1>
        </div>

        {/* ── Step Indicator ── */}
        <div className="flex items-center gap-2 mb-8">
          {STEP_DEFS.map((s, i) => {
            const Icon = s.icon;
            const isActive = s.key === step;
            const isDone = i < stepIdx;
            return (
              <div key={s.key} className="flex items-center gap-2">
                {i > 0 && (
                  <div className={`w-8 h-px ${isDone ? "bg-blue-500" : "bg-gray-700"}`} />
                )}
                <div
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-blue-600/20 text-blue-400 border border-blue-500/40"
                      : isDone
                        ? "bg-green-600/15 text-green-400 border border-green-600/30"
                        : "bg-white/5 text-gray-500 border border-gray-700"
                  }`}
                >
                  {isDone ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Icon className="w-3.5 h-3.5" />
                  )}
                  {s.label}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="bg-red-600/15 border border-red-600/30 text-red-400 px-4 py-2.5 rounded-lg text-sm mb-6 flex justify-between items-center">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ── Step: Upload ── */}
        {step === "upload" && (
          <div>
            <div
              className={`border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center transition-colors ${
                dragging
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 hover:border-gray-500 bg-[#1a1a2e]"
              }`}
              onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
              onDragOver={(e) => { e.preventDefault(); }}
              onDrop={handleDrop}
            >
              {loading ? (
                <div className="flex flex-col items-center text-blue-400">
                  <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
                  <p className="text-sm font-medium">Analyzing file...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center text-gray-600 dark:text-gray-400">
                  <Upload className="w-12 h-12 mb-4 text-gray-500" />
                  <p className="text-base font-medium mb-1 text-gray-700 dark:text-gray-300">
                    Drag & Drop your inventory file
                  </p>
                  <p className="text-xs text-gray-500 mb-6">
                    Supports .csv, .xlsx, .xls — The wizard will auto-detect columns
                  </p>
                  <div className="flex gap-3">
                    <input
                      ref={fileRef}
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void handleFile(f);
                        if (fileRef.current) fileRef.current.value = "";
                      }}
                    />
                    <button
                      onClick={() => fileRef.current?.click()}
                      className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium transition-colors"
                    >
                      <FileSpreadsheet className="w-4 h-4" /> Choose File
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Export section */}
            <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 mt-6">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-2">Export Inventory</h3>
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-4">
                Download your current inventory as an Excel file for editing.
              </p>
              <button
                onClick={() => void handleExport()}
                disabled={loading || !canRead}
                className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Download className="w-4 h-4" /> Export to Excel
              </button>
            </div>
          </div>
        )}

        {/* ── Step: Map Columns ── */}
        {step === "map" && analyze && (
          <div>
            <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 mb-6">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-1">
                File: {file?.name}
              </h3>
              <p className="text-xs text-gray-600 dark:text-gray-400">
                {analyze.row_count} rows detected &middot; {analyze.headers.length} columns
              </p>
            </div>

            {/* Required fields */}
            <div className="mb-6">
              <h3 className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
                Required Fields
              </h3>
              <div className="space-y-2">
                {requiredFields.map((field) => (
                  <div key={field.key} className="flex items-center gap-3 bg-[#1a1a2e] border border-gray-800 rounded-lg px-4 py-2.5">
                    <div className="w-36">
                      <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{field.label}</span>
                      <span className="text-red-400 ml-1">*</span>
                    </div>
                    <ArrowRight className="w-4 h-4 text-gray-600" />
                    <select
                      value={mapping[field.key] ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val === "") {
                          handleUnmap(field.key);
                        } else {
                          handleMapChange(field.key, parseInt(val, 10));
                        }
                      }}
                      className={`flex-1 rounded border px-3 py-1.5 text-sm bg-black/40 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                        mapping[field.key] !== undefined
                          ? "border-gray-600 text-gray-200"
                          : "border-red-500/50 text-red-400"
                      }`}
                    >
                      <option value="">-- Select column --</option>
                      {analyze.headers.map((h, idx) => (
                        <option key={idx} value={idx}>
                          {h} (col {idx + 1})
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* Optional fields */}
            <div className="mb-6">
              <h3 className="text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-3">
                Optional Fields
              </h3>
              <div className="space-y-2">
                {optionalFields.map((field) => (
                  <div key={field.key} className="flex items-center gap-3 bg-[#1a1a2e] border border-gray-800 rounded-lg px-4 py-2.5">
                    <div className="w-36">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{field.label}</span>
                    </div>
                    <ArrowRight className="w-4 h-4 text-gray-600" />
                    <select
                      value={mapping[field.key] ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val === "") {
                          handleUnmap(field.key);
                        } else {
                          handleMapChange(field.key, parseInt(val, 10));
                        }
                      }}
                      className="flex-1 rounded border border-gray-700 px-3 py-1.5 text-sm bg-black/40 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">-- Skip --</option>
                      {analyze.headers.map((h, idx) => (
                        <option key={idx} value={idx}>
                          {h} (col {idx + 1})
                        </option>
                      ))}
                    </select>
                    {field.default !== null && field.default !== undefined && (
                      <span className="text-xs text-gray-500 shrink-0">
                        Default: {String(field.default)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Unmatched columns */}
            {analyze.unmatched.length > 0 && (
              <div className="bg-yellow-600/10 border border-yellow-600/20 rounded-lg p-4 mb-6">
                <p className="text-xs font-medium text-yellow-400 mb-1">
                  Unmapped columns ({analyze.unmatched.length})
                </p>
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  {analyze.unmatched.map(([idx, name]) => name).join(", ")} — these columns will be ignored.
                </p>
              </div>
            )}

            {/* Navigation */}
            <div className="flex justify-between items-center">
              <button
                onClick={() => { setStep("upload"); setFile(null); setAnalyze(null); }}
                className="flex items-center gap-1.5 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-white text-sm transition-colors"
              >
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
              <button
                onClick={() => void handlePreview()}
                disabled={!allRequiredMapped || loading}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
                Preview Import
              </button>
            </div>
          </div>
        )}

        {/* ── Step: Validate / Preview ── */}
        {step === "validate" && previewRows && (
          <div>
            <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 mb-6">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-1">
                Preview (first {previewRows.length} rows)
              </h3>
              <p className="text-xs text-gray-600 dark:text-gray-400">
                Review mapped data before committing. Rows with missing required fields will be skipped.
              </p>
            </div>

            {/* Preview table */}
            <div className="overflow-x-auto mb-6 border border-gray-800 rounded-lg">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#0d0d20] border-b border-gray-800">
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-600 dark:text-gray-400">#</th>
                    {requiredFields.map((f) => (
                      <th key={f.key} className="px-3 py-2 text-left text-xs font-medium text-gray-700 dark:text-gray-300">
                        {f.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, i) => {
                    const missing = (row as Record<string, unknown>)._missing_required as string[] | undefined;
                    const hasError = missing && missing.length > 0;
                    return (
                      <tr
                        key={i}
                        className={`border-b border-gray-800/50 ${hasError ? "bg-red-600/10" : ""}`}
                      >
                        <td className="px-3 py-2 text-gray-500">{(row as Record<string, unknown>).row_index as number}</td>
                        {requiredFields.map((f) => (
                          <td key={f.key} className="px-3 py-2">
                            <span className={`${hasError && missing?.includes(f.key) ? "text-red-400" : "text-gray-200"}`}>
                              {String((row as Record<string, unknown>)[f.key] ?? "")}
                            </span>
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Navigation */}
            <div className="flex justify-between items-center">
              <button
                onClick={() => setStep("map")}
                className="flex items-center gap-1.5 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-white text-sm transition-colors"
              >
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
              <button
                onClick={() => void handleCommit()}
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-40"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Commit Import
              </button>
            </div>
          </div>
        )}

        {/* ── Step: Import Results ── */}
        {step === "import" && importResult && (
          <div>
            <div className="bg-green-600/10 border border-green-600/30 rounded-lg p-6 mb-6">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle className="w-6 h-6 text-green-500" />
                <h3 className="text-lg font-semibold text-green-400">Import Complete</h3>
              </div>
              <div className="grid grid-cols-2 gap-6 text-sm">
                <div className="bg-[#0d0d20] rounded-lg p-4 border border-gray-800">
                  <span className="text-xs text-gray-600 dark:text-gray-400 block mb-1">Inserted</span>
                  <span className="text-2xl font-bold text-green-400">{importResult.inserted}</span>
                </div>
                <div className="bg-[#0d0d20] rounded-lg p-4 border border-gray-800">
                  <span className="text-xs text-gray-600 dark:text-gray-400 block mb-1">Skipped</span>
                  <span className="text-2xl font-bold text-amber-400">{importResult.skipped}</span>
                </div>
              </div>
              {importResult.errors.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Errors:</p>
                  <ul className="text-xs text-red-400 space-y-1 max-h-40 overflow-y-auto bg-[#0d0d20] rounded-lg p-3 border border-gray-800">
                    {importResult.errors.map((err: string, i: number) => (
                      <li key={i}>• {err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex justify-between items-center">
              <button
                onClick={resetWizard}
                className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium transition-colors"
              >
                Import Another File
              </button>
              <button
                onClick={() => router.push("/dashboard/inventory")}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium transition-colors"
              >
                View Inventory <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}
