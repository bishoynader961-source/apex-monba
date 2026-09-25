"use client";

import { useEffect, useState, useCallback } from "react";
import { useI18n } from "@/components/I18nProvider";
import * as excelApi from "@/lib/api/excel";
import type {
  ExcelImportResult,
  ExcelImportAnalyzeResult,
  ExcelImportPreviewResult,
  ExcelImportPreviewRow,
  ExcelImportCommitResult,
} from "@/types/contracts";

const PAGE_SIZE = 20;

interface ImportWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function ImportWizard({ onClose, onSuccess }: ImportWizardProps) {
  const { t } = useI18n();
  const [step, setStep] = useState<"file" | "mapping" | "preview" | "committing">("file");
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [analysis, setAnalysis] = useState<ExcelImportAnalyzeResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ExcelImportPreviewResult | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [committing, setCommitting] = useState(false);
  const [generateLabels, setGenerateLabels] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExcelImportCommitResult | null>(null);

  const resetWizard = useCallback(() => {
    setStep("file");
    setFile(null);
    setFileName("");
    setAnalysis(null);
    setMapping({});
    setDefaults({});
    setPreview(null);
    setPreviewPage(1);
    setError(null);
    setResult(null);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const validTypes = [".xlsx", ".xls", ".csv"];
    const ext = fileName.toLowerCase().slice(fileName.lastIndexOf("."));
    if (!validTypes.includes(ext)) {
      alert("Please select an .xlsx, .xls, or .csv file.");
      return;
    }
    setFile(f);
    setFileName(f.name);
    setError(null);
    setStep("mapping");
    analyzeFile(f);
  };

  const analyzeFile = async (file: File) => {
    try {
      const result = await excelApi.analyzeImport(file);
      setAnalysis(result);
      // Auto-apply mapping
      setMapping(result.mapping);
      // Set defaults for required fields
      const newDefaults: Record<string, string> = {};
      for (const field of result.db_fields) {
        if (field.required && field.default !== null && field.default !== undefined) {
          setDefaults((prev) => ({ ...prev, [field.key]: String(field.default) }));
        }
      }
      setStep("mapping");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze file.");
    }
  };

  const generatePreview = useCallback(async () => {
    if (!file || !analysis) return;
    try {
      const result = await excelApi.previewImport(file, mapping, defaults, 20);
      setPreview(result);
      setPreviewPage(1);
      setStep("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate preview.");
    }
  }, [file, mapping, defaults]);

  const handleMappingChange = (field: string, colIndex: number) => {
    setMapping((prev) => {
      const next = { ...prev };
      if (colIndex >= 0) {
        next[field] = colIndex;
      } else {
        delete next[field];
      }
      return next;
    });
  };

  const handleDefaultChange = (field: string, value: string) => {
    setDefaults((prev) => ({ ...prev, [field]: value }));
  };

  const handleCommit = async () => {
    if (!file) return;
    setCommitting(true);
    try {
      const result = await excelApi.commitImport(file, mapping, defaults, generateLabels);
      setResult(result);
      setStep("committing");
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to commit import.");
    } finally {
      setCommitting(false);
    }
  };

  const totalPages = preview ? Math.ceil((preview.total_rows || 0) / 20) : 1;
  const paginatedRows = preview
    ? preview.rows.slice((previewPage - 1) * 20, previewPage * 20)
    : [];

  if (!file) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div className="w-full max-w-2xl rounded-lg bg-gray-800 p-6 shadow-xl max-h-[90vh] overflow-y-auto">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("excel.importWizard")}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t("excel.uploadInstruction")}</p>
          <div className="border-2 border-dashed border-gray-600 rounded-lg p-8 text-center">
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              id="file-input"
              onChange={handleFileChange}
            />
            <label htmlFor="file-input" className="cursor-pointer">
              <div className="text-gray-600 dark:text-gray-400 mb-2">{t("excel.dragDrop")}</div>
              <button
                type="button"
                onClick={() => document.getElementById("file-input")?.click()}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
              >
                {t("excel.selectFile")}
              </button>
            </label>
          </div>
          <p className="text-xs text-gray-500 mt-4 text-center">
            {t("excel.supportedFormats")}
          </p>
        </div>
      </div>
    );
  }

  if (step === "mapping") {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div className="w-full max-w-4xl rounded-lg bg-gray-800 p-6 shadow-xl max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t("excel.mappingStep")}</h2>
            <button onClick={() => setStep("file")} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
          </div>
          {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t("excel.mappingInstruction")}</p>
          <div className="space-y-3 max-h-[60vh] overflow-y-auto">
            {analysis?.db_fields.map((field) => (
              <div key={field.key} className="grid grid-cols-[1fr_auto_auto] gap-3 items-center">
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">{field.label} {field.required && <span className="text-red-400">*</span>}</label>
                <div className="flex gap-2">
                  <select
                    value={mapping[field.key] !== undefined ? mapping[field.key] : ""}
                    onChange={(e) => handleMappingChange(field.key, e.target.value === "" ? -1 : parseInt(e.target.value, 10))}
                    className="flex-1 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                  >
                    <option value="-1">{t("excel.mapIgnore")}</option>
                    {analysis?.headers.map((h, i) => (
                      <option key={i} value={i}>{analysis.headers[i]}</option>
                    ))}
                  </select>
                  {field.required && (
                    <span className="text-red-400 text-xs">{t("excel.requiredField")}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <button onClick={() => setStep("file")} disabled={!analysis} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.back")}</button>
            <button onClick={generatePreview} disabled={!analysis} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50">
              {t("excel.preview")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (step === "preview") {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div className="w-full max-w-6xl rounded-lg bg-gray-800 p-6 shadow-xl max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t("excel.previewTitle")}</h2>
            <button onClick={() => setStep("mapping")} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
          </div>
          {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-800/60">
                <tr>
                  {analysis?.db_fields.map((field) => (
                    <th key={field.key} className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">
                      {field.label} {field.required && <span className="text-red-400">*</span>}
                    </th>
                  ))}
                  <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">{t("excel.missing")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {paginatedRows.map((row, idx) => (
                  <tr key={row.row_index} className={row._missing_required?.length ? "bg-red-900/20" : idx % 2 === 0 ? "bg-gray-800/50" : "bg-gray-900/50"}>
                    {analysis?.db_fields.map((field) => (
                      <td key={field.key} className="px-3 py-2 text-sm text-gray-800 dark:text-gray-200 truncate max-w-[150px]">
                        {String(row[field.key] ?? "—")}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-center">
                      {row._missing_required?.length > 0 && (
                        <span className="text-red-400 text-xs">{row._missing_required.join(", ")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-between items-center mt-4">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Page {previewPage} of {totalPages} • {preview?.total_rows} {t("excel.rows")}
            </div>
            <div className="flex gap-2">
              <button onClick={() => setPreviewPage(p => Math.max(1, p - 1))} disabled={previewPage <= 1} className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700 disabled:opacity-50">{t("common.prev")}</button>
              <button onClick={() => setPreviewPage(p => Math.min(totalPages, p + 1))} disabled={previewPage >= totalPages} className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700 disabled:opacity-50">{t("common.next")}</button>
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button onClick={() => setStep("mapping")} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.back")}</button>
          <div className="flex items-center gap-2">
            <input
              id="generate-labels-toggle"
              type="checkbox"
              checked={generateLabels}
              onChange={(e) => setGenerateLabels(e.target.checked)}
              className="h-4 w-4 accent-green-600"
            />
            <label htmlFor="generate-labels-toggle" className="text-sm text-gray-600 dark:text-gray-300 select-none cursor-pointer">
              Generate Labels on Import
            </label>
          </div>
          <button onClick={handleCommit} disabled={committing} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50">
            {committing ? t("excel.committing") : t("excel.commit")}
          </button>
          </div>
        </div>
      </div>
    );
  }

  if (step === "committing") {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div className="w-full max-w-md rounded-lg bg-gray-800 p-6 shadow-xl text-center">
          <div className="animate-spin text-green-400 text-4xl mb-4">⟳</div>
          <p className="text-lg text-gray-800 dark:text-gray-100">{t("excel.committing")}</p>
          {result && <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{result.message}</p>}
        </div>
      </div>
    );
  }

  return null;
}