"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";
import type { DispenseRead } from "@/types/contracts";

export function FillsForRxModal() {
  const { activeModal, closeModal, fetchFillsByRx } = useRxStore();
  const [rxQuery, setRxQuery] = useState("");
  const [fills, setFills] = useState<DispenseRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  if (activeModal !== "fillsForRx") return null;

  const handleSearch = async () => {
    if (!rxQuery.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const results = await fetchFillsByRx(rxQuery.trim());
      setFills(results);
    } catch {
      setFills([]);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    closeModal();
    setRxQuery("");
    setFills([]);
    setSearched(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 shrink-0">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Fills for Rx</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        <div className="p-6 flex flex-col gap-4 flex-1 min-h-0">
          <div className="flex gap-2 shrink-0">
            <input
              type="text"
              value={rxQuery}
              onChange={(e) => setRxQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleSearch()}
              placeholder="Enter Rx number..."
              className="flex-1 bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none font-mono"
            />
            <button
              onClick={() => void handleSearch()}
              disabled={loading}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm"
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {searched && fills.length === 0 && !loading && (
              <div className="text-center text-gray-500 py-8 italic">No fills found for this Rx number.</div>
            )}
            {fills.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-700">
                    <th className="text-left py-2 px-2">Fill Date</th>
                    <th className="text-left py-2 px-2">Drug</th>
                    <th className="text-right py-2 px-2">Qty</th>
                    <th className="text-right py-2 px-2">Refill #</th>
                    <th className="text-right py-2 px-2">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.map((f) => (
                    <tr key={f.id} className="border-b border-gray-700/50 hover:bg-white/5">
                      <td className="py-2 px-2 font-mono">{f.fill_date}</td>
                      <td className="py-2 px-2">{f.product_name}</td>
                      <td className="py-2 px-2 text-right">{f.quantity}</td>
                      <td className="py-2 px-2 text-right">{f.refill_count}</td>
                      <td className="py-2 px-2 text-right">${Number(f.price_at_time).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="flex justify-end shrink-0">
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
