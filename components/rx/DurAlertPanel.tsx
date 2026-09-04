"use client";

import type { DdiAlert } from "@/types/contracts";

interface Props {
  allergyFlags: string[];
  ddiAlerts: DdiAlert[];
  duplicateTherapy: string[];
}

export function DurAlertPanel({ allergyFlags, ddiAlerts, duplicateTherapy }: Props) {
  const hasAny = allergyFlags.length > 0 || ddiAlerts.length > 0 || duplicateTherapy.length > 0;
  if (!hasAny) {
    return (
      <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/40 p-3 text-sm text-emerald-300">
        No clinical alerts — all checks passed.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {allergyFlags.length > 0 && (
        <div className="rounded-lg bg-amber-900/30 border border-amber-700/40 p-3 text-sm">
          <div className="font-semibold text-amber-300 mb-1">Allergy Flags</div>
          {allergyFlags.map((a, i) => (
            <div key={i} className="text-amber-200">{a}</div>
          ))}
        </div>
      )}
      {ddiAlerts.length > 0 && (
        <div className="rounded-lg bg-red-900/30 border border-red-700/40 p-3 text-sm">
          <div className="font-semibold text-red-300 mb-1">Drug-Drug Interactions</div>
          {ddiAlerts.map((d, i) => (
            <div key={i} className="flex items-start gap-2 text-red-200">
              <span className={`shrink-0 text-xs font-bold px-1.5 py-0.5 rounded ${
                d.severity === "high" ? "bg-red-600" : d.severity === "moderate" ? "bg-amber-600" : "bg-yellow-600"
              }`}>
                {d.severity.toUpperCase()}
              </span>
              <span>{d.warning}</span>
            </div>
          ))}
        </div>
      )}
      {duplicateTherapy.length > 0 && (
        <div className="rounded-lg bg-orange-900/30 border border-orange-700/40 p-3 text-sm">
          <div className="font-semibold text-orange-300 mb-1">Duplicate Therapy</div>
          {duplicateTherapy.map((t, i) => (
            <div key={i} className="text-orange-200">{t}</div>
          ))}
        </div>
      )}
    </div>
  );
}
