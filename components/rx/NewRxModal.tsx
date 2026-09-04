"use client";

import { useState } from "react";

import { SearchableInput } from "@/components/rx/SearchableInput";
import { useRxStore } from "@/stores/rxStore";
import type { DdiAlert, Medicine, PatientRead, PrescriberRead, SigCodeRead } from "@/types/contracts";
import { DurAlertPanel } from "./DurAlertPanel";

export function NewRxModal() {
  const {
    activeModal, closeModal,
    selectedPatient, selectedDrug, selectedSigCode, selectedPrescriber,
    quantity, daysSupply, refillsAuthorized, fillDate,
    useInsurance, selectedInsurancePlan,
    lastDispenseResult, isProcessing, error,
    setPatient, setDrug, setSigCode, setPrescriber,
    setQuantity, setDaysSupply, setRefillsAuthorized, setFillDate,
    setUseInsurance,
    searchPatients, searchDrugs, parseSig, searchPrescribers,
    submitNewRx,
  } = useRxStore();

  const [patientQuery, setPatientQuery] = useState("");
  const [drugQuery, setDrugQuery] = useState("");
  const [sigQuery, setSigQuery] = useState("");
  const [prescriberQuery, setPrescriberQuery] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (activeModal !== "newRx") return null;

  const handleSubmit = async () => {
    try {
      const result = await submitNewRx();
      setSubmitted(true);
      setPatientQuery("");
      setDrugQuery("");
      setSigQuery("");
      setPrescriberQuery("");
    } catch {
      // error is set in store
    }
  };

  const handleClose = () => {
    closeModal();
    setSubmitted(false);
    setPatientQuery("");
    setDrugQuery("");
    setSigQuery("");
    setPrescriberQuery("");
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={handleClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-white">New Prescription</h2>
          <button onClick={handleClose} className="text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {submitted && lastDispenseResult ? (
          /* Success Result */
          <div className="p-6">
            <div className="rounded-lg bg-emerald-900/30 border border-emerald-700/40 p-4 mb-4">
              <div className="text-emerald-300 font-semibold mb-1">Prescription Created</div>
              <div className="text-white text-lg font-mono">Rx #{lastDispenseResult.rx_number}</div>
              <div className="text-sm text-gray-400 mt-1">
                {lastDispenseResult.product_name} &mdash; Qty {lastDispenseResult.quantity} &mdash; Sig: {lastDispenseResult.sig_code}
              </div>
              {lastDispenseResult.days_supply && (
                <div className="text-sm text-gray-400">Days Supply: {lastDispenseResult.days_supply}</div>
              )}
            </div>
            <DurAlertPanel
              allergyFlags={lastDispenseResult.allergy_flags}
              ddiAlerts={lastDispenseResult.ddi_alerts}
              duplicateTherapy={lastDispenseResult.duplicate_therapy}
            />
            <div className="flex justify-end mt-4">
              <button onClick={handleClose} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium">
                Done
              </button>
            </div>
          </div>
        ) : (
          /* Entry Form */
          <div className="p-6 flex flex-col gap-4">
            {/* Patient */}
            <SearchableInput<PatientRead>
              label="Patient"
              placeholder="Type name or DOB..."
              value={selectedPatient ? `${selectedPatient.name} (${selectedPatient.dob})` : patientQuery}
              onChange={(q) => { setPatientQuery(q); if (!q) setPatient(null); }}
              onSelect={(p) => { setPatient(p); setPatientQuery(""); }}
              onSearch={searchPatients}
              required
              renderItem={(p) => (
                <div>
                  <span className="font-medium">{p.name}</span>
                  <span className="text-gray-400 ml-2">DOB: {p.dob}</span>
                  {p.insurance_plan_id && <span className="text-emerald-400 ml-2">(Ins)</span>}
                </div>
              )}
            />
            {selectedPatient && (
              <div className="text-xs text-gray-500 -mt-2 ml-1">
                Patient #{selectedPatient.id} &mdash; {selectedPatient.name}
              </div>
            )}

            {/* Drug */}
            <SearchableInput<Medicine>
              label="Drug / NDC"
              placeholder="Type drug name or NDC..."
              value={selectedDrug ? `${selectedDrug.name}${selectedDrug.strength ? ` ${selectedDrug.strength}` : ""}` : drugQuery}
              onChange={(q) => { setDrugQuery(q); if (!q) setDrug(null); }}
              onSelect={(d) => { setDrug(d); setDrugQuery(""); }}
              onSearch={searchDrugs}
              required
              renderItem={(d) => (
                <div>
                  <span className="font-medium">{d.name}</span>
                  {d.strength && <span className="text-gray-400 ml-1">{d.strength}</span>}
                  {d.form && <span className="text-gray-500 ml-1">{d.form}</span>}
                  {d.ndc_code && <span className="text-gray-600 ml-2 font-mono text-xs">{d.ndc_code}</span>}
                </div>
              )}
            />
            {selectedDrug && (
              <div className="text-xs text-gray-500 -mt-2 ml-1">
                NDC: {selectedDrug.ndc_code || "N/A"} &mdash; Price: ${Number(selectedDrug.price).toFixed(2)}
              </div>
            )}

            {/* Sig Code */}
            <SearchableInput<SigCodeRead>
              label="Sig Code"
              placeholder="e.g. BID, TID, QD..."
              value={selectedSigCode ? `${selectedSigCode.code} — ${selectedSigCode.full_text}` : sigQuery}
              onChange={(q) => { setSigQuery(q); if (!q) setSigCode(null); }}
              onSelect={(s) => { setSigCode(s); setSigQuery(""); }}
              onSearch={async (q) => {
                const result = await parseSig(q);
                return result ? [result] : [];
              }}
              required
              renderItem={(s) => (
                <div>
                  <span className="font-mono font-bold">{s.code}</span>
                  <span className="text-gray-400 ml-2">{s.full_text}</span>
                  <span className="text-gray-600 ml-2 text-xs">
                    Lang: {s.language} | DA: {s.days_accumulated} | Off: {s.offset}
                  </span>
                </div>
              )}
            />
            {selectedSigCode && (
              <div className="text-xs text-gray-500 -mt-2 ml-1">
                {selectedSigCode.full_text} (D.A.={selectedSigCode.days_accumulated}, Offset={selectedSigCode.offset})
              </div>
            )}

            {/* Quantity + Days Supply + Refills */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-400 uppercase tracking-wider font-medium mb-1">
                  Quantity <span className="text-red-400">*</span>
                </label>
                <input
                  type="number"
                  min={1}
                  value={quantity || ""}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 uppercase tracking-wider font-medium mb-1">
                  Days Supply
                </label>
                <input
                  type="number"
                  min={0}
                  value={daysSupply ?? ""}
                  onChange={(e) => setDaysSupply(e.target.value ? Number(e.target.value) : null)}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 uppercase tracking-wider font-medium mb-1">
                  Refills Authorized
                </label>
                <input
                  type="number"
                  min={0}
                  value={refillsAuthorized}
                  onChange={(e) => setRefillsAuthorized(Number(e.target.value))}
                  className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
                />
              </div>
            </div>

            {/* Fill Date */}
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider font-medium mb-1">
                Fill Date
              </label>
              <input
                type="date"
                value={fillDate}
                onChange={(e) => setFillDate(e.target.value)}
                className="bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
              />
            </div>

            {/* Prescriber */}
            <SearchableInput<PrescriberRead>
              label="Prescriber"
              placeholder="Type prescriber name or NPI..."
              value={selectedPrescriber ? `${selectedPrescriber.first_name} ${selectedPrescriber.last_name}` : prescriberQuery}
              onChange={(q) => { setPrescriberQuery(q); if (!q) setPrescriber(null); }}
              onSelect={(p) => { setPrescriber(p); setPrescriberQuery(""); }}
              onSearch={searchPrescribers}
              renderItem={(p) => (
                <div>
                  <span className="font-medium">{p.first_name} {p.last_name}</span>
                  {p.npi && <span className="text-gray-400 ml-2">NPI: {p.npi}</span>}
                  {p.phone && <span className="text-gray-500 ml-2">{p.phone}</span>}
                </div>
              )}
            />

            {/* Insurance */}
            {selectedInsurancePlan && (
              <div className="flex items-center gap-3 bg-white/5 rounded-lg p-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={useInsurance}
                    onChange={(e) => setUseInsurance(e.target.checked)}
                    className="rounded"
                  />
                  Use Insurance
                </label>
                <span className="text-gray-400 text-sm">
                  {selectedInsurancePlan.plan_name}
                  {selectedInsurancePlan.copay_amount !== "0" && ` — Copay: $${selectedInsurancePlan.copay_amount}`}
                </span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="rounded-lg bg-red-900/30 border border-red-700/40 p-3 text-sm text-red-300">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 mt-2">
              <button
                onClick={handleClose}
                className="px-4 py-2 border border-gray-600 text-gray-300 rounded-lg text-sm hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={isProcessing || !selectedPatient || !selectedDrug || !selectedSigCode || quantity <= 0}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium"
              >
                {isProcessing ? "Submitting..." : "Submit Rx"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
