"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import { getPatientHistory } from "@/lib/api/patients";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { PatientHistoryEntry, PatientRead } from "@/types/contracts";

interface Props {
  open: boolean;
  patient: PatientRead;
  onClose: () => void;
}

export function PatientHistoryPanel({ open, patient, onClose }: Props) {
  const { t } = useI18n();
  const [entries, setEntries] = useState<PatientHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !patient) return;
    setLoading(true);
    setError(null);
    getPatientHistory(patient.id, 100)
      .then((data) => { setEntries(data); setLoading(false); })
      .catch((err) => { setError(String(err)); setLoading(false); });
  }, [open, patient]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111] border border-gray-800 rounded-xl w-[560px] max-h-[70vh] shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <div>
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              {t("pos.patientHistory") ?? "Purchase History"}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">{patient.name}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-6 text-sm text-gray-500 text-center">Loading…</div>
          )}
          {error && (
            <div className="p-6 text-sm text-red-400 text-center">{error}</div>
          )}
          {!loading && entries.length === 0 && (
            <div className="p-6 text-sm text-gray-500 text-center">
              {t("pos.noPurchaseHistory") ?? "No purchase history found"}
            </div>
          )}
          {!loading && entries.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-600 dark:text-gray-400 border-b border-gray-800">
                  <th className="px-4 py-2 font-medium">{t("pos.colReceipt") ?? "Receipt"}</th>
                  <th className="px-4 py-2 font-medium">{t("pos.colDate") ?? "Date"}</th>
                  <th className="px-4 py-2 font-medium text-right">{t("pos.colAmount") ?? "Amount"}</th>
                  <th className="px-4 py-2 font-medium">{t("pos.colPayment") ?? "Payment"}</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.receipt_id} className="border-b border-gray-800/50 hover:bg-[#1a1a2e] transition-colors">
                    <td className="px-4 py-2.5 text-gray-800 dark:text-gray-200 font-medium">{e.receipt_number}</td>
                    <td className="px-4 py-2.5 text-gray-600 dark:text-gray-400">
                      {e.timestamp ? new Date(e.timestamp).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right text-green-400 font-medium">
                      ${formatMoney(parseMoney(e.total_amount))}
                    </td>
                    <td className="px-4 py-2.5 text-gray-600 dark:text-gray-400">{e.payment_method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-800 shrink-0">
          <span className="text-xs text-gray-500">
            {entries.length} {entries.length === 1 ? "receipt" : "receipts"}
          </span>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-200 transition-colors"
          >
            {t("common.close") ?? "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
