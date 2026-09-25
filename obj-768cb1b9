"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";
import type { DispenseRead } from "@/types/contracts";

export function EditRxModal() {
  const {
    activeModal, closeModal,
    lastDispenseResult, isProcessing, error,
    quantity, daysSupply, refillsAuthorized, fillDate,
    selectedSigCode,
    setQuantity, setDaysSupply, setRefillsAuthorized, setFillDate, setSigCode,
    parseSig, editDispense,
  } = useRxStore();

  const [sigQuery, setSigQuery] = useState("");
  const [editTarget, setEditTarget] = useState<DispenseRead | null>(null);
  const [saved, setSaved] = useState(false);

  if (activeModal !== "editRx") return null;

  const target = editTarget ?? lastDispenseResult;

  const handleLoad = () => {
    if (lastDispenseResult) {
      setEditTarget(lastDispenseResult);
      setQuantity(lastDispenseResult.quantity);
      setDaysSupply(lastDispenseResult.days_supply ?? null);
      setRefillsAuthorized(lastDispenseResult.refills_authorized);
      setFillDate(lastDispenseResult.fill_date);
      setSigQuery(lastDispenseResult.sig_code);
    }
  };

  // Auto-load on open
  if (!editTarget && lastDispenseResult && !saved) {
    handleLoad();
  }

  const handleSave = async () => {
    if (!target) return;
    try {
      await editDispense(target.id);
      setSaved(true);
    } catch {
      // error in store
    }
  };

  const handleClose = () => {
    closeModal();
    setEditTarget(null);
    setSaved(false);
    setSigQuery("");
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Edit Prescription</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {!target ? (
          <div className="p-6 text-center text-gray-500">
            <p>No prescription loaded. Submit or look up an Rx first, then reopen Edit.</p>
            <button onClick={handleClose} className="mt-4 px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5">
              Close
            </button>
          </div>
        ) : saved ? (
          <div className="p-6">
            <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/40 p-4 mb-4">
              <div className="text-emerald-300 font-semibold">Prescription Updated</div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Changes saved for Rx #{target.rx_number}</div>
            </div>
            <div className="flex justify-end">
              <button onClick={handleClose} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6 flex flex-col gap-4">
            <div className="text-sm text-gray-600 dark:text-gray-400 bg-white/5 rounded-lg p-3">
              Editing Rx #{target.rx_number} &mdash; {target.product_name}
            </div>

            {/* Sig Code */}
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="editrxmodal-field-1">
                Sig Code
              </label>
              <input id="editrxmodal-field-1"
                type="text"
                value={sigQuery}
                onChange={(e) => { setSigQuery(e.target.value); }}
                onBlur={async () => { if (sigQuery) await parseSig(sigQuery); }}
                placeholder="e.g. BID"
                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none font-mono"
              />
              {selectedSigCode && (
                <div className="text-xs text-gray-500 mt-1">{selectedSigCode.full_text}</div>
              )}
            </div>

            {/* Quantity + Days Supply */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="editrxmodal-field-2">
                  Quantity
                </label>
                <input id="editrxmodal-field-2"
                  type="number"
                  min={1}
                  value={quantity || ""}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="editrxmodal-field-3">
                  Days Supply
                </label>
                <input id="editrxmodal-field-3"
                  type="number"
                  min={0}
                  value={daysSupply ?? ""}
                  onChange={(e) => setDaysSupply(e.target.value ? Number(e.target.value) : null)}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
            </div>

            {/* Refills + Fill Date */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="editrxmodal-field-4">
                  Refills Authorized
                </label>
                <input id="editrxmodal-field-4"
                  type="number"
                  min={0}
                  value={refillsAuthorized}
                  onChange={(e) => setRefillsAuthorized(Number(e.target.value))}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="editrxmodal-field-5">
                  Fill Date
                </label>
                <input id="editrxmodal-field-5"
                  type="date"
                  value={fillDate}
                  onChange={(e) => setFillDate(e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
            </div>

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
                onClick={() => void handleSave()}
                disabled={isProcessing || !target}
                className="px-6 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
              >
                {isProcessing ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
