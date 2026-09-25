"use client";

import { useState } from "react";

import { calculatePrice, listPriceCodes } from "@/lib/api/dictionaries";
import type { Medicine, PriceCodeRead } from "@/types/contracts";
import { useRxStore } from "@/stores/rxStore";
import { SearchableInput } from "@/components/rx/SearchableInput";

export function PriceCheckModal() {
  const { activeModal, closeModal, searchDrugs } = useRxStore();
  const [drug, setDrug] = useState<Medicine | null>(null);
  const [drugQuery, setDrugQuery] = useState("");
  const [priceCode, setPriceCode] = useState<PriceCodeRead | null>(null);
  const [priceCodeQuery, setPriceCodeQuery] = useState("");
  const [acquisitionCost, setAcquisitionCost] = useState("");
  const [result, setResult] = useState<{ computed_price: string; clamped: boolean } | null>(null);
  const [loading, setLoading] = useState(false);

  if (activeModal !== "priceCheck") return null;

  const handleCalculate = async () => {
    if (!priceCode || !acquisitionCost) return;
    setLoading(true);
    try {
      const r = await calculatePrice(priceCode.id, Number(acquisitionCost));
      setResult(r);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    closeModal();
    setDrug(null);
    setDrugQuery("");
    setPriceCode(null);
    setPriceCodeQuery("");
    setAcquisitionCost("");
    setResult(null);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Price Check</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          <SearchableInput<Medicine>
            label="Drug"
            placeholder="Search drug..."
            value={drug ? drug.name : drugQuery}
            onChange={(q) => { setDrugQuery(q); if (!q) setDrug(null); }}
            onSelect={(d) => { setDrug(d); setDrugQuery(""); }}
            onSearch={searchDrugs}
            renderItem={(d) => (
              <div>
                <span className="font-medium">{d.name}</span>
                {d.strength && <span className="text-gray-600 dark:text-gray-400 ml-1">{d.strength}</span>}
              </div>
            )}
          />

          <SearchableInput<PriceCodeRead>
            label="Price Code"
            placeholder="Search price code..."
            value={priceCode ? `${priceCode.code} — ${priceCode.description}` : priceCodeQuery}
            onChange={(q) => { setPriceCodeQuery(q); if (!q) setPriceCode(null); }}
            onSelect={(pc) => { setPriceCode(pc); setPriceCodeQuery(""); }}
            onSearch={async (q) => {
              const all = await listPriceCodes();
              return all.filter((pc) =>
                pc.code.toLowerCase().includes(q.toLowerCase()) ||
                pc.description.toLowerCase().includes(q.toLowerCase()),
              );
            }}
            renderItem={(pc) => (
              <div>
                <span className="font-mono font-bold">{pc.code}</span>
                <span className="text-gray-600 dark:text-gray-400 ml-2">{pc.description}</span>
              </div>
            )}
          />

          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1" htmlFor="pricecheckmodal-field-1">
              Acquisition Cost
            </label>
            <input id="pricecheckmodal-field-1"
              type="number"
              step="0.01"
              min={0}
              value={acquisitionCost}
              onChange={(e) => setAcquisitionCost(e.target.value)}
              placeholder="0.00"
              className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
            />
          </div>

          {result && (
            <div className="bg-white/5 rounded-lg p-4 text-center">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Computed Price</div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">${Number(result.computed_price).toFixed(2)}</div>
              {result.clamped && (
                <div className="text-xs text-amber-400 mt-1">Price was clamped to min/max range</div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-3 mt-2">
            <button
              onClick={handleClose}
              className="px-4 py-2 border border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-white/5"
            >
              Close
            </button>
            <button
              onClick={() => void handleCalculate()}
              disabled={loading || !priceCode || !acquisitionCost}
              className="px-6 py-2 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
            >
              {loading ? "Calculating..." : "Calculate"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
