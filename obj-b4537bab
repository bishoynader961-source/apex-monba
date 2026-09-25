"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { getReceiptPrint } from "@/lib/api/pos";
import type { ReceiptPrintResponse } from "@/types/contracts";

interface ReceiptPrintPreviewProps {
  receiptId: number;
  open: boolean;
  onClose: () => void;
}

type Tab = "preview" | "thermal";

export function ReceiptPrintPreview({ receiptId, open, onClose }: ReceiptPrintPreviewProps) {
  const { t } = useI18n();
  const [data, setData] = useState<ReceiptPrintResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("preview");

  useEffect(() => {
    if (!open) return;
    setData(null);
    setError(null);
    setActiveTab("preview");
    setLoading(true);
    getReceiptPrint(receiptId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load receipt"))
      .finally(() => setLoading(false));
  }, [open, receiptId]);

  const handlePrint = () => {
    const printArea = document.getElementById("receipt-print-area");
    if (!printArea) return;
    const originalDisplay = printArea.style.display;
    printArea.style.display = "block";
    window.print();
    printArea.style.display = originalDisplay;
  };

  const handleDownload = () => {
    if (!data) return;
    const blob = new Blob([data.receipt_text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.receipt_number}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {t("pos.printPreview")}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-gray-800 shrink-0">
          <button
            onClick={() => setActiveTab("preview")}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === "preview"
                ? "text-blue-400 border-b-2 border-blue-500"
                : "text-gray-400 hover:text-gray-300"
            }}`}
          >
            {t("pos.tabPreview")}
          </button>
          <button
            onClick={() => setActiveTab("thermal")}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === "thermal"
                ? "text-blue-400 border-b-2 border-blue-500"
                : "text-gray-400 hover:text-gray-300"
            }}`}
          >
            {t("pos.tabThermal")}
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          {loading && (
            <div className="flex items-center justify-center py-8 text-sm text-gray-600 dark:text-gray-400">
              <svg className="animate-spin h-5 w-5 text-gray-600 dark:text-gray-400 mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.22L10.17 16 4 9.83 6 8v9.22z"></path>
              </svg>
              {t("common.loading")}
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-900/20 border border-red-900/50 rounded-md">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          {!loading && !error && data && (
            <>
              {/* Print-only area — visible during window.print() */}
              <div
                id="receipt-print-area"
                className="hidden print:block print:visible"
                dangerouslySetInnerHTML={{ __html: data.printable_html }}
              />

              {activeTab === "preview" && (
                <div
                  id="receipt-preview-content"
                  className="pharmacy-receipt-preview"
                  dangerouslySetInnerHTML={{ __html: data.printable_html }}
                />
              )}

              {activeTab === "thermal" && (
                <pre className="whitespace-pre-wrap font-mono text-sm text-gray-700 dark:text-gray-300 bg-[#0d0d20] border border-gray-800 rounded-md p-4 overflow-x-auto">
                  {data.receipt_text}
                </pre>
              )}
            </>
          )}
        </div>

        {/* Footer with action buttons */}
        {!loading && !error && data && (
          <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-800 shrink-0">
            <button
              onClick={handleDownload}
              className="px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md font-medium transition-colors"
            >
              {t("pos.downloadText")}
            </button>
            <button
              onClick={handlePrint}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors"
            >
              {t("pos.print")}
            </button>
          </div>
        )}

        {/* Always-available close button */}
        <div className="px-5 py-3 border-t border-gray-800 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md font-medium transition-colors"
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
