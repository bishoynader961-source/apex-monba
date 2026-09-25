"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";
import type { DispenseRead } from "@/types/contracts";
import { DurAlertPanel } from "./DurAlertPanel";

export function RefillModal() {
  const {
    activeModal, closeModal,
    lastDispenseResult, isProcessing, error,
    fetchDispenseByRx, submitRefill,
    setDrug, setSigCode, setQuantity, setDaysSupply, setRefillsAuthorized,
    setPatient,
  } = useRxStore();

  const [rxQuery, setRxQuery] = useState("");
  const [foundDispense, setFoundDispense] = useState<DispenseRead | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  if (activeModal !== "refill") return null;

  const handleLookup = async () => {
    if (!rxQuery.trim()) return;
    setLookupError(null);
    setFoundDispense(null);
    try {
      const result = await fetchDispenseByRx(rxQuery.trim());
      if (result) {
        setFoundDispense(result);
        // Pre-populate store with original data
        setQuantity(result.quantity);
        setDaysSupply(result.days_supply ?? null);
        setRefillsAuthorized(result.refills_authorized);
      } else {
        setLookupError(`No prescription found for Rx #${rxQuery.trim()}`);
      }
    } catch {
      setLookupError(`No prescription found for Rx #${rxQuery.trim()}`);
    }
  };

  const handleRefill = async () => {
    if (!foundDispense) return;
    setSubmitted(true);
    try {
      await submitRefill(foundDispense.id);
    } catch {
      setSubmitted(false);
    }
  };

  const handleClose = () => {
    closeModal();
    setRxQuery("");
    setFoundDispense(null);
    setLookupError(null);
    setSubmitted(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Refill Prescription</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {submitted && lastDispenseResult ? (
          <div className="p-6">
            <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/40 p-4 mb-4">
              <div className="text-emerald-300 font-semibold mb-1">Refill Processed</div>
              <div className="text-gray-900 dark:text-white text-lg font-mono">Rx #{lastDispenseResult.rx_number}</div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                Refill #{lastDispenseResult.refill_count} of {lastDispenseResult.refills_authorized}
              </div>
            </div>
            <DurAlertPanel
              allergyFlags={lastDispenseResult.allergy_flags}
              ddiAlerts={lastDispenseResult.ddi_alerts}
              duplicateTherapy={lastDispenseResult.duplicate_therapy}
            />
            <div className="flex justify-end mt-4">
              <button onClick={handleClose} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6 flex flex-col gap-4">
            {/* Rx Lookup */}
            <div>
              <label htmlFor="rx-refill-number" className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1">
                Rx Number
              </label>
              <div className="flex gap-2">
                <input
                  id="rx-refill-number"
                  type="text"
                  value={rxQuery}
                  onChange={(e) => setRxQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void handleLookup()}
                  placeholder="Enter Rx number..."
                  className="flex-1 bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none font-mono"
                />
                <button
                  onClick={() => void handleLookup()}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm"
                >
                  Lookup
                </button>
              </div>
            </div>

            {lookupError && (
              <div className="text-sm text-red-400">{lookupError}</div>
            )}

            {/* Original Rx Details */}
            {foundDispense && (
              <div className="bg-white/5 rounded-lg p-4 text-sm">
                <div className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-2">Original Prescription</div>
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-gray-600 dark:text-gray-400">Drug:</span> {foundDispense.product_name}</div>
                  <div><span className="text-gray-600 dark:text-gray-400">Sig:</span> {foundDispense.sig_code}</div>
                  <div><span className="text-gray-600 dark:text-gray-400">Qty:</span> {foundDispense.quantity}</div>
                  <div><span className="text-gray-600 dark:text-gray-400">Days Supply:</span> {foundDispense.days_supply ?? "N/A"}</div>
                  <div><span className="text-gray-600 dark:text-gray-400">Refills Used:</span> {foundDispense.refill_count} / {foundDispense.refills_authorized}</div>
                  <div><span className="text-gray-600 dark:text-gray-400">Last Fill:</span> {foundDispense.last_fill_date ?? foundDispense.fill_date}</div>
                </div>
                {foundDispense.refill_count >= foundDispense.refills_authorized && (
                  <div className="mt-2 text-amber-400 text-xs font-semibold">
                    No refills remaining for this prescription.
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="rounded-lg bg-red-900/30 border border-red-700/40 p-3 text-sm text-red-300">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-3 mt-2">
              <button
                onClick={handleClose}
                className="px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleRefill()}
                disabled={isProcessing || !foundDispense || foundDispense.refill_count >= foundDispense.refills_authorized}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
              >
                {isProcessing ? "Processing..." : "Submit Refill"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
