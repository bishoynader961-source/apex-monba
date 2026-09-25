"use client";

import { useState } from "react";

import { useRxStore } from "@/stores/rxStore";
import type { Medicine } from "@/types/contracts";

export function DrugEducationModal() {
  const { activeModal, closeModal, searchDrugs } = useRxStore();
  const [drug, setDrug] = useState<Medicine | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Medicine[]>([]);
  const [loading, setLoading] = useState(false);

  if (activeModal !== "drugEducation") return null;

  const handleSearch = async () => {
    if (query.length < 1) return;
    setLoading(true);
    try {
      const items = await searchDrugs(query);
      setResults(items);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    closeModal();
    setDrug(null);
    setQuery("");
    setResults([]);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Drug Education</h2>
          <button onClick={handleClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          <div>
            <label htmlFor="rx-edu-drug-search" className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1">
              Search Drug
            </label>
            <div className="flex gap-2">
              <input
                id="rx-edu-drug-search"
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setDrug(null); }}
                onKeyDown={(e) => e.key === "Enter" && void handleSearch()}
                placeholder="Type drug name..."
                className="flex-1 bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
              />
              <button
                onClick={() => void handleSearch()}
                disabled={loading}
                className="px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-sm"
              >
                {loading ? "..." : "Search"}
              </button>
            </div>
          </div>

          {/* Results list */}
          {!drug && results.length > 0 && (
            <div className="bg-gray-800 border border-gray-700 rounded-lg max-h-40 overflow-y-auto">
              {results.map((d) => (
                <button
                  key={d.id}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-teal-600/20 border-b border-gray-700/50 last:border-0"
                  onClick={() => { setDrug(d); setResults([]); }}
                >
                  <span className="font-medium">{d.name}</span>
                  {d.strength && <span className="text-gray-600 dark:text-gray-400 ml-1">{d.strength}</span>}
                  {d.form && <span className="text-gray-500 ml-1">{d.form}</span>}
                </button>
              ))}
            </div>
          )}

          {/* Drug Info Card */}
          {drug && (
            <div className="bg-white/5 rounded-lg p-4 text-sm space-y-2">
              <div className="text-lg font-semibold text-gray-900 dark:text-white">{drug.name}</div>
              {drug.strength && <div><span className="text-gray-600 dark:text-gray-400">Strength:</span> {drug.strength}</div>}
              {drug.form && <div><span className="text-gray-600 dark:text-gray-400">Form:</span> {drug.form}</div>}
              {drug.ndc_code && <div><span className="text-gray-600 dark:text-gray-400">NDC:</span> <span className="font-mono">{drug.ndc_code}</span></div>}
              {drug.manufacturer_name && <div><span className="text-gray-600 dark:text-gray-400">Manufacturer:</span> {drug.manufacturer_name}</div>}
              {drug.therapeutic_class && <div><span className="text-gray-600 dark:text-gray-400">Therapeutic Class:</span> {drug.therapeutic_class}</div>}
              {drug.dea_schedule && <div><span className="text-gray-600 dark:text-gray-400">DEA Schedule:</span> {drug.dea_schedule}</div>}
              {drug.is_generic ? <div className="text-emerald-400">Generic</div> : <div className="text-gray-500">Brand</div>}
              {drug.is_controlled ? <div className="text-amber-400">Controlled Substance</div> : null}
            </div>
          )}

          <div className="flex justify-end gap-3">
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
