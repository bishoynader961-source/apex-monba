"use client";

import { useState } from "react";

import { checkEligibility } from "@/lib/api/insurance";
import { useRxStore } from "@/stores/rxStore";
import type { EligibilityCheckResult } from "@/types/contracts";

export function EligibilityModal() {
  const { activeModal, closeModal, selectedPatient, searchPatients } = useRxStore();
  const [result, setResult] = useState<EligibilityCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [patientQuery, setPatientQuery] = useState("");
  const [patientId, setPatientId] = useState<number | null>(null);

  if (activeModal !== "eligibility") return null;

  const handleCheck = async () => {
    if (!patientId) return;
    setLoading(true);
    try {
      const r = await checkEligibility(patientId);
      setResult(r);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    closeModal();
    setResult(null);
    setPatientQuery("");
    setPatientId(null);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Insurance Eligibility Check</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          <div>
            <label htmlFor="rx-elig-patient-id" className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1">
              Patient ID
            </label>
            <div className="flex gap-2">
              <input
                id="rx-elig-patient-id"
                type="number"
                value={patientId ?? patientQuery}
                onChange={(e) => {
                  const v = e.target.value;
                  if (/^\d*$/.test(v)) {
                    setPatientId(v ? Number(v) : null);
                    setPatientQuery(v);
                  }
                }}
                placeholder="Enter patient ID..."
                className="flex-1 bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none font-mono"
              />
              <button
                onClick={() => void handleCheck()}
                disabled={loading || !patientId}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white rounded-lg text-sm"
              >
                {loading ? "Checking..." : "Check"}
              </button>
            </div>
          </div>

          {result && (
            <div className="bg-white/5 rounded-lg p-4 text-sm space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${result.eligible ? "bg-emerald-600" : "bg-red-600"}`}>
                  {result.eligible ? "ELIGIBLE" : "NOT ELIGIBLE"}
                </span>
                <span className="text-gray-600 dark:text-gray-400">{result.patient_name}</span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-gray-600 dark:text-gray-400">Plan:</span> {result.plan_name || "None"}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Status:</span> {result.active ? "Active" : "Inactive"}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Copay Tier:</span> {result.copay_tier || "N/A"}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Copay:</span> ${Number(result.copay_amount).toFixed(2)}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Deductible:</span> ${Number(result.deductible).toFixed(2)}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Remaining:</span> ${Number(result.deductible_remaining).toFixed(2)}</div>
                <div><span className="text-gray-600 dark:text-gray-400">Co-Insurance:</span> {result.coinsurance_pct}%</div>
                <div><span className="text-gray-600 dark:text-gray-400">Coverage:</span> {result.coverage_percentage}%</div>
              </div>

              <div className="mt-2 text-xs text-gray-500 italic">{result.message}</div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleClose}
              className="px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
