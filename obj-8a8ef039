"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";

export function TransferRxModal() {
  const {
    activeModal, closeModal,
    lastDispenseResult, isProcessing, error,
    transferDispense,
  } = useRxStore();

  const [pharmacyName, setPharmacyName] = useState("");
  const [pharmacyPhone, setPharmacyPhone] = useState("");
  const [transferType, setTransferType] = useState<"outgoing" | "incoming">("outgoing");
  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);

  if (activeModal !== "transferRx") return null;

  const handleTransfer = async () => {
    if (!lastDispenseResult) return;
    try {
      await transferDispense(
        lastDispenseResult.id,
        pharmacyName,
        pharmacyPhone,
        transferType,
        reason || "No reason provided",
      );
      setDone(true);
    } catch {
      // error in store
    }
  };

  const handleClose = () => {
    closeModal();
    setPharmacyName("");
    setPharmacyPhone("");
    setTransferType("outgoing");
    setReason("");
    setDone(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Transfer Prescription</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {!lastDispenseResult && !done ? (
          <div className="p-6 text-center text-gray-500">
            <p>No prescription loaded. Submit or look up an Rx first, then reopen Transfer.</p>
            <button onClick={handleClose} className="mt-4 px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5">
              Close
            </button>
          </div>
        ) : done ? (
          <div className="p-6">
            <div className="rounded-lg bg-sky-900/30 border border-sky-700/40 p-4 mb-4">
              <div className="text-sky-300 font-semibold">Prescription Transferred</div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {transferType === "outgoing" ? "Transferred to" : "Received from"} {pharmacyName}
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
            <div className="bg-white/5 rounded-lg p-3 text-sm">
              <div className="text-gray-600 dark:text-gray-400">Rx #<span className="font-mono text-gray-900 dark:text-white">{lastDispenseResult!.rx_number}</span></div>
              <div className="text-gray-600 dark:text-gray-400 mt-1">{lastDispenseResult!.product_name} &mdash; Qty: {lastDispenseResult!.quantity}</div>
            </div>

            {/* Transfer Type */}
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1">
                Transfer Direction
              </label>
              <div className="flex gap-3">
                <button
                  onClick={() => setTransferType("outgoing")}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${
                    transferType === "outgoing"
                      ? "bg-sky-600 border-sky-500 text-white"
                      : "border-gray-600 text-gray-400 hover:bg-white/5"
                  }`}
                >
                  Transfer Out
                </button>
                <button
                  onClick={() => setTransferType("incoming")}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${
                    transferType === "incoming"
                      ? "bg-emerald-600 border-emerald-500 text-white"
                      : "border-gray-600 text-gray-400 hover:bg-white/5"
                  }`}
                >
                  Transfer In
                </button>
              </div>
            </div>

            {/* Pharmacy Info */}
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="transferrxmodal-field-1">
                {transferType === "outgoing" ? "Transfer To Pharmacy" : "Transfer From Pharmacy"}
              </label>
              <input id="transferrxmodal-field-1"
                type="text"
                value={pharmacyName}
                onChange={(e) => setPharmacyName(e.target.value)}
                placeholder="Pharmacy name..."
                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="transferrxmodal-field-2">
                Pharmacy Phone
              </label>
              <input id="transferrxmodal-field-2"
                type="tel"
                value={pharmacyPhone}
                onChange={(e) => setPharmacyPhone(e.target.value)}
                placeholder="(555) 555-5555"
                className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
              />
            </div>

            {/* Reason */}
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="transferrxmodal-field-3">
                Reason for Transfer
              </label>
              <textarea id="transferrxmodal-field-3"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Enter reason..."
                rows={2}
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
                onClick={() => void handleTransfer()}
                disabled={isProcessing || !lastDispenseResult || !pharmacyName}
                className="px-6 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
              >
                {isProcessing ? "Transferring..." : "Confirm Transfer"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
