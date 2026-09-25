"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";

export function ReverseRxModal() {
  const {
    activeModal, closeModal,
    lastDispenseResult, isProcessing, error,
    reverseDispense,
  } = useRxStore();

  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);

  if (activeModal !== "reverseRx") return null;

  const handleReverse = async () => {
    if (!lastDispenseResult) return;
    try {
      await reverseDispense(lastDispenseResult.id, reason || "No reason provided");
      setDone(true);
    } catch {
      // error in store
    }
  };

  const handleClose = () => {
    closeModal();
    setReason("");
    setDone(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Reverse (Void) Prescription</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {!lastDispenseResult && !done ? (
          <div className="p-6 text-center text-gray-500">
            <p>No prescription loaded. Submit or look up an Rx first, then reopen Reverse.</p>
            <button onClick={handleClose} className="mt-4 px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5">
              Close
            </button>
          </div>
        ) : done ? (
          <div className="p-6">
            <div className="rounded-lg bg-amber-900/30 border border-amber-700/40 p-4 mb-4">
              <div className="text-amber-300 font-semibold">Prescription Voided</div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                Rx has been reversed. Inventory has been restocked.
              </div>
            </div>
            <div className="flex justify-end">
              <button onClick={handleClose} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6 flex flex-col gap-4">
            <div className="rounded-lg bg-red-900/20 border border-red-700/30 p-3 text-sm text-red-300">
              <strong>Warning:</strong> This will void the prescription and restock the inventory.
              This action cannot be undone.
            </div>

            <div className="bg-white/5 rounded-lg p-3 text-sm">
              <div className="text-gray-600 dark:text-gray-400">Rx #<span className="font-mono text-gray-900 dark:text-white">{lastDispenseResult!.rx_number}</span></div>
              <div className="text-gray-600 dark:text-gray-400 mt-1">{lastDispenseResult!.product_name} &mdash; Qty: {lastDispenseResult!.quantity}</div>
            </div>

            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="reverserxmodal-field-1">
                Reason for Reversal
              </label>
              <textarea id="reverserxmodal-field-1"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Enter reason..."
                rows={3}
                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none resize-none"
              />
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
                onClick={() => void handleReverse()}
                disabled={isProcessing || !lastDispenseResult}
                className="px-6 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
              >
                {isProcessing ? "Voiding..." : "Confirm Void"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
