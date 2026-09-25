"use client";

import { useState } from "react";
import { checkDrugInteractions } from "@/lib/api/drugInteractions";
import type { DrugInteractionResult } from "@/types/contracts";

interface Props {
  drugNames: string[];
}

const SEVERITY_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  contraindicated: { border: "border-red-600", bg: "bg-red-50 dark:bg-red-900/20", text: "text-red-600 dark:text-red-400" },
  severe: { border: "border-orange-600", bg: "bg-orange-50 dark:bg-orange-900/20", text: "text-orange-600 dark:text-orange-400" },
  moderate: { border: "border-amber-600", bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-600 dark:text-amber-400" },
  mild: { border: "border-green-600", bg: "bg-green-50 dark:bg-green-900/20", text: "text-green-600 dark:text-green-400" },
};

export default function InteractionChecker({ drugNames }: Props) {
  const [results, setResults] = useState<DrugInteractionResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);

  const handleCheck = async () => {
    if (drugNames.length < 2) return;
    setLoading(true);
    try {
      setResults(await checkDrugInteractions(drugNames));
      setChecked(true);
    } catch {
      setResults([]);
    }
    setLoading(false);
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900/50">
      <div className="flex justify-between items-center mb-2">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 m-0">Drug Interactions</h4>
        <button
          onClick={() => void handleCheck()}
          disabled={loading || drugNames.length < 2}
          className="px-2.5 py-1 text-xs rounded border-none bg-violet-600 text-white disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer hover:bg-violet-700 transition-colors"
        >
          {loading ? "Checking…" : "Check Interactions"}
        </button>
      </div>

      {checked && results.length === 0 && (
        <div className="text-xs text-green-600 dark:text-green-400 py-1">
          ✓ No known interactions found
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-1.5">
          {results.map((r, i) => {
            const severity = SEVERITY_COLORS[r.severity] ?? SEVERITY_COLORS.moderate;
            return (
              <div
                key={i}
                className={`p-2 rounded text-xs border-l-3 ${severity.border} ${severity.bg} bg-white dark:bg-gray-800`}
              >
                <div className="flex justify-between mb-1">
                  <span className="font-semibold text-gray-900 dark:text-gray-100">{r.drug_a} ↔ {r.drug_b}</span>
                  <span className="text-[10px] font-bold uppercase {severity.text}">
                    {r.severity}
                  </span>
                </div>
                {r.description && <div className="text-gray-700 dark:text-gray-300">{r.description}</div>}
                {r.recommendation && (
                  <div className="text-gray-500 dark:text-gray-400 italic mt-1">→ {r.recommendation}</div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {checked && drugNames.length < 2 && (
        <div className="text-xs text-gray-500 dark:text-gray-400 py-1">
          Add at least 2 medications to check interactions
        </div>
      )}
    </div>
  );
}
