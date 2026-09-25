"use client";

import React, { useState } from "react";
import { encryptString, decryptString } from "@/lib/offlineCrypto";
import { getOfflinePassphrase } from "@/lib/offlineKey";
import type { CardTransactionPayload } from "@/types/contracts";

interface CardInfoModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (info: CardTransactionPayload) => void;
}

export const CardInfoModal: React.FC<CardInfoModalProps> = ({ open, onClose, onSubmit }) => {
  const [authRef, setAuthRef] = useState("");
  const [network, setNetwork] = useState("");
  const [lastFour, setLastFour] = useState("");
  const [error, setError] = useState<string | null>(null);

  const validate = () => {
    const regex = /^[A-Z0-9]{6,12}$/;
    if (!regex.test(authRef)) return "Authorization reference must be 6‑12 uppercase alphanumeric characters.";
    if (!/^[0-9]{4}$/.test(lastFour)) return "Last four digits must be exactly 4 numbers.";
    if (!network) return "Card network is required.";
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errMsg = validate();
    if (errMsg) {
      setError(errMsg);
      return;
    }
    const payload: CardTransactionPayload = {
      amount: "0", // amount will be patched by POS checkout flow later
      auth_reference: authRef,
      card_network: network,
      last_four: lastFour,
      timestamp: new Date().toISOString(),
    };
    onSubmit(payload);
    onClose();
    setAuthRef("");
    setNetwork("");
    setLastFour("");
    setError(null);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-gray-800 p-6 rounded-lg w-full max-w-md shadow-xl">
        <h2 className="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">Card Terminal Details</h2>
        {error && <p className="text-red-400 mb-2">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="cardinfomodal-field-1">Auth Reference</label>
            <input id="cardinfomodal-field-1"
              type="text"
              value={authRef}
              onChange={e => setAuthRef(e.target.value.toUpperCase())}
              className="w-full rounded-md bg-gray-900 border border-gray-600 px-3 py-2 text-sm text-gray-100"
              placeholder="e.g. AB12CD34"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="cardinfomodal-field-2">Card Network</label>
            <input id="cardinfomodal-field-2"
              type="text"
              value={network}
              onChange={e => setNetwork(e.target.value)}
              className="w-full rounded-md bg-gray-900 border border-gray-600 px-3 py-2 text-sm text-gray-100"
              placeholder="Visa, MasterCard, etc."
            />
          </div>
          <div>
            <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="cardinfomodal-field-3">Last Four Digits</label>
            <input id="cardinfomodal-field-3"
              type="text"
              value={lastFour}
              onChange={e => setLastFour(e.target.value.replace(/\D/g, ""))}
              maxLength={4}
              className="w-full rounded-md bg-gray-900 border border-gray-600 px-3 py-2 text-sm text-gray-100"
              placeholder="1234"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-700 text-gray-300 rounded-md hover:bg-gray-600">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
};
