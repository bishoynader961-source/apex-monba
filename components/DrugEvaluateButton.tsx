"use client";

import { useState } from "react";
import { AlertTriangle, ShieldCheck, Info, Loader2, X, Lock, Stethoscope } from "lucide-react";

type EvalStatus = "safe" | "warning" | "severe";

interface EvaluateResult {
  status: EvalStatus;
  message: string;
  interactions: string[];
  source: string;
  cached: boolean;
}

interface DrugEvaluateButtonProps {
  drugName: string;
  ndc?: string;
  /** Called after a safe/warning evaluation completes — allows dispense to proceed. */
  onSafe?: () => void;
  /** Called when dispense must be blocked (severe interaction). */
  onSevere?: () => void;
  className?: string;
}

function apiHeaders() {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

const STATUS_CONFIG: Record<EvalStatus, {
  icon: React.FC<{ className?: string }>;
  labelClass: string;
  modalBorder: string;
  titleClass: string;
  label: string;
}> = {
  safe: {
    icon: ShieldCheck,
    labelClass: "bg-green-900/30 text-green-400 border-green-600/30",
    modalBorder: "border-green-600/40",
    titleClass: "text-green-400",
    label: "Safe to Dispense",
  },
  warning: {
    icon: Info,
    labelClass: "bg-yellow-900/30 text-yellow-400 border-yellow-600/30",
    modalBorder: "border-yellow-600/40",
    titleClass: "text-yellow-400",
    label: "Clinical Warning",
  },
  severe: {
    icon: AlertTriangle,
    labelClass: "bg-red-900/30 text-red-400 border-red-600/30",
    modalBorder: "border-red-600/40",
    titleClass: "text-red-400",
    label: "Severe Interaction — Dispense Locked",
  },
};

export function DrugEvaluateButton({
  drugName,
  ndc,
  onSafe,
  onSevere,
  className = "",
}: DrugEvaluateButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<EvaluateResult | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [pharmacistAcknowledged, setPharmacistAcknowledged] = useState(false);

  const evaluate = async () => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/v1/drugs/evaluate", {
        method: "POST",
        headers: apiHeaders(),
        body: JSON.stringify({ drug_name: drugName, ndc: ndc ?? null }),
      });
      if (!res.ok) throw new Error("Evaluation failed");
      const data: EvaluateResult = await res.json();
      setResult(data);
      setPharmacistAcknowledged(false);
      setShowModal(true);
      if (data.status === "severe") {
        onSevere?.();
      }
    } catch {
      alert("Drug evaluation service unavailable. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcknowledgeAndProceed = () => {
    setPharmacistAcknowledged(true);
    setShowModal(false);
    onSafe?.();
  };

  const handleClose = () => {
    setShowModal(false);
    if (result?.status === "safe") onSafe?.();
  };

  return (
    <>
      <button
        id={`btn-evaluate-drug-${drugName.replace(/\s+/g, "-").toLowerCase()}`}
        onClick={evaluate}
        disabled={isLoading || !drugName}
        className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium border border-blue-600/40 text-blue-400 hover:bg-blue-600/10 rounded-md transition-colors disabled:opacity-50 ${className}`}
      >
        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Stethoscope className="w-3.5 h-3.5" />
        )}
        {isLoading ? "Evaluating…" : "Evaluate Drug"}
      </button>

      {showModal && result && (() => {
        const cfg = STATUS_CONFIG[result.status];
        const StatusIcon = cfg.icon;
        return (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div
              className={`bg-[#1a1a2e] border-2 ${cfg.modalBorder} rounded-xl p-6 w-full max-w-lg shadow-2xl`}
              role="alertdialog"
              aria-modal="true"
              aria-label={cfg.label}
            >
              {/* Title */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg border ${cfg.labelClass}`}>
                    <StatusIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className={`text-lg font-bold ${cfg.titleClass}`}>{cfg.label}</h2>
                    <p className="text-xs text-gray-500">
                      Drug: <span className="text-gray-300 font-medium">{drugName}</span>
                      {ndc && <> · NDC: <span className="text-gray-300">{ndc}</span></>}
                      {result.cached && <> · <span className="text-blue-400">cached</span></>}
                    </p>
                  </div>
                </div>
                {result.status !== "severe" && (
                  <button onClick={handleClose} className="text-gray-500 hover:text-gray-300">
                    <X className="w-5 h-5" />
                  </button>
                )}
              </div>

              {/* Message */}
              <p className="text-sm text-gray-300 mb-4 leading-relaxed">{result.message}</p>

              {/* Interactions */}
              {result.interactions.length > 0 && (
                <ul className="mb-4 space-y-2">
                  {result.interactions.map((interaction, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-400">
                      <AlertTriangle className="w-3.5 h-3.5 text-yellow-500 flex-shrink-0 mt-0.5" />
                      {interaction}
                    </li>
                  ))}
                </ul>
              )}

              {/* Severe — lock dispense unless manually acknowledged */}
              {result.status === "severe" && !pharmacistAcknowledged && (
                <div className="p-3 bg-red-900/20 border border-red-600/30 rounded-md mb-4 flex items-center gap-2">
                  <Lock className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <p className="text-xs text-red-300">
                    Dispensing is locked. A pharmacist must manually acknowledge this warning to proceed.
                  </p>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3 mt-2">
                {result.status === "safe" && (
                  <button
                    onClick={handleClose}
                    className="flex-1 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium"
                  >
                    Proceed to Dispense
                  </button>
                )}
                {result.status === "warning" && (
                  <>
                    <button
                      onClick={handleClose}
                      className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleClose}
                      className="flex-1 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-md text-sm font-medium"
                    >
                      Acknowledge & Dispense
                    </button>
                  </>
                )}
                {result.status === "severe" && !pharmacistAcknowledged && (
                  <>
                    <button
                      onClick={() => { setShowModal(false); }}
                      className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm"
                    >
                      Cancel Dispense
                    </button>
                    <button
                      onClick={handleAcknowledgeAndProceed}
                      className="flex-1 py-2 bg-red-700 hover:bg-red-800 text-white rounded-md text-sm font-medium flex items-center justify-center gap-2"
                    >
                      <AlertTriangle className="w-4 h-4" /> Override — I Accept Responsibility
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </>
  );
}
