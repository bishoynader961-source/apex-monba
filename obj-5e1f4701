"use client";

import { useEffect, useState } from "react";

import { useCan } from "@/stores/authStore";
import { useEpcsStore, useEpcs, useEpcsTotal, useEpcsLoading, useEpcsError, useEpcsFilters } from "@/stores/epcsStore";
import * as epcsApi from "@/lib/api/epcs";
import {
  EPCS_STATUS_TRANSITIONS,
  EPCS_STATUS_VALUES,
} from "@/types/contracts";
import type {
  EPCSPrescriptionRead,
  EPCSPrescriptionCreate,
  EPCSPrescriptionUpdate,
  EPCSSignRequest,
  EPCSTransmitRequest,
} from "@/types/contracts";
import { useI18n } from "@/components/I18nProvider";

const PAGE_SIZE = 50;

function DiagnosisSection({ diagnosisCodes, setDiagnosisCodes, t }: { diagnosisCodes: string[]; setDiagnosisCodes: (codes: string[]) => void; t: (key: string) => string }) {
  const addDiagnosis = () => setDiagnosisCodes([...diagnosisCodes, ""]);
  const removeDiagnosis = (idx: number) => setDiagnosisCodes(diagnosisCodes.filter((_, i) => i !== idx));

  return (
    <div>
      <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">{t("epcs.fieldDiagnosis")}</label>
      <div className="space-y-2">
        {diagnosisCodes.map((code, idx) => (
          <div key={idx} className="flex gap-2">
            <input
              type="text"
              placeholder={t("epcs.icd10Placeholder")}
              value={code}
              onChange={(e) => setDiagnosisCodes(diagnosisCodes.map((c, i) => i === idx ? e.target.value : c))}
              className="flex-1 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
            {diagnosisCodes.length > 1 && (
              <button
                type="button"
                onClick={() => setDiagnosisCodes(diagnosisCodes.filter((_, i) => i !== idx))}
                className="text-red-400 hover:text-red-300 text-sm"
              >
                ×
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={addDiagnosis}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
        >
          + {t("epcs.addDiagnosis")}
        </button>
      </div>
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "bg-gray-700 text-gray-300 border-gray-600/40",
  PENDING_SIGNATURE: "bg-yellow-900/30 text-yellow-400 border-yellow-600/40",
  SIGNED: "bg-green-900/30 text-green-400 border-green-600/40",
  TRANSMITTED: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  REJECTED: "bg-red-900/30 text-red-400 border-red-600/40",
  ARCHIVED: "bg-purple-900/30 text-purple-400 border-purple-600/40",
};

const SCHEDULE_COLORS: Record<string, string> = {
  "C-II": "bg-red-900/30 text-red-400 border-red-600/40",
  "C-III": "bg-orange-900/30 text-orange-400 border-orange-600/40",
  "C-IV": "bg-yellow-900/30 text-yellow-400 border-yellow-600/40",
  "C-V": "bg-green-900/30 text-green-400 border-green-600/40",
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-gray-700 text-gray-300";
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${color}`}>
      {status}
    </span>
  );
}

function ScheduleBadge({ schedule }: { schedule: string }) {
  const color = SCHEDULE_COLORS[schedule] ?? "bg-gray-700 text-gray-300";
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${color}`}>
      {schedule}
    </span>
  );
}

function ActionMenu({
  epcs,
  onTransition,
  onSign,
  onTransmit,
  canSign,
  canTransmit,
}: {
  epcs: EPCSPrescriptionRead;
  onTransition: (id: number, status: string) => Promise<any>;
  onSign: (rx: EPCSPrescriptionRead) => Promise<any>;
  onTransmit: (id: number) => Promise<any>;
  canSign: boolean;
  canTransmit: boolean;
}) {
  const [open, setOpen] = useState(false);
  const currentStatus = epcs.status;
  const allowed = EPCS_STATUS_TRANSITIONS[currentStatus as keyof typeof EPCS_STATUS_TRANSITIONS] || [];

  if (allowed.length === 0) {
    return <span className="text-gray-500 text-xs">—</span>;
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="text-blue-400 hover:text-blue-300 text-xs font-medium"
      >
        {currentStatus} ▼
      </button>
      {open && (
        <>
          <div className="absolute right-0 top-full mt-1 z-20 bg-gray-800 border border-gray-700 rounded-md shadow-lg min-w-[160px]">
            {allowed.map((status) => (
              <button
                key={status}
                onClick={() => {
                  onTransition(epcs.id, status);
                  setOpen(false);
                }}
                className="w-full px-3 py-2 text-left text-sm text-gray-100 hover:bg-gray-700"
              >
                {status}
              </button>
            ))}
            {epcs.status === "SIGNED" && canTransmit && (
              <button
                onClick={() => { onTransmit(epcs.id); setOpen(false); }}
                className="w-full px-3 py-2 text-left text-sm text-blue-400 hover:bg-gray-700"
              >
                Transmit
              </button>
            )}
            {epcs.status === "PENDING_SIGNATURE" && canSign && (
              <button
                onClick={() => { onSign(epcs); setOpen(false); }}
                className="w-full px-3 py-2 text-left text-sm text-green-400 hover:bg-gray-700"
              >
                Sign (2FA)
              </button>
            )}
            <div className="border-t border-gray-700" />
            <button
              onClick={() => setOpen(false)}
              className="w-full px-3 py-2 text-left text-sm text-gray-400 hover:bg-gray-700"
            >
              Cancel
            </button>
          </div>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} aria-hidden="true" />
        </>
      )}
    </div>
  );
}

export function EpcsDashboard() {
  const { t } = useI18n();
  const canRead = useCan("epcs.read");
  const canWrite = useCan("epcs.write");
  const canReview = useCan("epcs.review");
  const canSign = useCan("epcs.sign");
  const canTransmit = useCan("epcs.transmit");

  const items = useEpcs();
  const total = useEpcsTotal();
  const isLoading = useEpcsLoading();
  const error = useEpcsError();
  const filters = useEpcsFilters();
  const { fetchEpcs, setFilters, createEpcs, transitionStatus, signEpcs, transmitEpcs, setSelectedEpcs } = useEpcsStore();

  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EPCSPrescriptionRead | null>(null);
  const [signTarget, setSignTarget] = useState<EPCSPrescriptionRead | null>(null);

  // Load on mount
  useEffect(() => {
    if (canRead) {
      fetchEpcs();
    }
  }, [canRead, fetchEpcs]);

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  const paginated = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleCreateSubmit = async (payload: EPCSPrescriptionCreate) => {
    await createEpcs(payload);
    setCreateOpen(false);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    // Note: Delete not implemented in API yet - would need to add DELETE endpoint
    setDeleteTarget(null);
  };

  const handleSign = async (rx: EPCSPrescriptionRead) => {
    setSignTarget(rx);
  };

  const handleTransmit = async (id: number) => {
    // For transmitting, we need the pharmacy info
    const payload: EPCSTransmitRequest = {
      prescription_id: id,
      pharmacy_npi: undefined,
      pharmacy_ncpdp: undefined,
      transmit_method: "ncpdp_script",
    };
    await transmitEpcs(id, payload);
  };

  if (!canRead) {
    return <p className="text-sm text-gray-600 dark:text-gray-400">{t("epcs.noPermission")}</p>;
  }

  return (
    <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 border-b border-gray-800">
        <h2 className="text-xl font-bold">{t("epcs.title")}</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            disabled={!canWrite}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
          >
            {t("epcs.newPrescription")}
          </button>
        </div>
      </header>

      {error && <p className="px-4 py-2 text-sm text-red-400">{error}</p>}

      {/* Filters */}
      <div className="p-4 border-b border-gray-800 grid grid-cols-1 sm:grid-cols-4 gap-3">
        <select
          value={filters.status ?? ""}
          onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">{t("epcs.allStatus")}</option>
          <option value="DRAFT">{t("epcs.statusDraft")}</option>
          <option value="PENDING_SIGNATURE">{t("epcs.statusPendingSignature")}</option>
          <option value="SIGNED">{t("epcs.statusSigned")}</option>
          <option value="TRANSMITTED">{t("epcs.statusTransmitted")}</option>
          <option value="REJECTED">{t("epcs.statusRejected")}</option>
          <option value="ARCHIVED">{t("epcs.statusArchived")}</option>
        </select>
        <select
          value={filters.schedule ?? ""}
          onChange={(e) => setFilters({ ...filters, schedule: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">{t("epcs.allSchedules")}</option>
          <option value="C-II">{t("epcs.scheduleC2")}</option>
          <option value="C-III">{t("epcs.scheduleC3")}</option>
          <option value="C-IV">{t("epcs.scheduleC4")}</option>
          <option value="C-V">{t("epcs.scheduleC5")}</option>
        </select>
        <input
          type="text"
          placeholder={t("epcs.searchProduct")}
          value={filters.product_name ?? ""}
          onChange={(e) => setFilters({ ...filters, product_name: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="date"
          value={filters.start_date ?? ""}
          onChange={(e) => setFilters({ ...filters, start_date: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-[900px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colId")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colPatient")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colPrescriber")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colDrug")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colSchedule")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-700 dark:text-gray-300">{t("epcs.colQty")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-700 dark:text-gray-300">{t("epcs.colStatus")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colCreated")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("epcs.colActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                  {t("epcs.loading")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                  {t("epcs.noPrescriptions")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.map((epcs) => (
              <tr key={epcs.id} className="hover:bg-gray-800/50">
                <td className="px-4 py-3 font-mono text-blue-400">{epcs.id}</td>
                <td className="px-4 py-3 truncate max-w-[180px]">{epcs.patient_name}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400 truncate max-w-[140px]">{epcs.prescriber_name}</td>
                <td className="px-4 py-3 truncate max-w-[200px]">{epcs.product_name}</td>
                <td className="px-4 py-3 text-center">
                  <ScheduleBadge schedule={epcs.schedule} />
                </td>
                <td className="px-4 py-3 text-center">{epcs.quantity}</td>
                <td className="px-4 py-3 text-center">
                  <StatusBadge status={epcs.status} />
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{epcs.created_at.slice(0, 10)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
<ActionMenu
                      epcs={epcs}
                      onTransition={transitionStatus}
                      onSign={handleSign}
                      onTransmit={handleTransmit}
                      canSign={canSign}
                      canTransmit={canTransmit}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="px-4 py-3 border-t border-gray-800 flex items-center justify-between">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          Page {page} of {totalPages} • {total} {t("epcs.prescriptions")}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            Prev
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>

      {/* Modals */}
      {createOpen && (
        <CreateEpcsModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => setCreateOpen(false)}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          item={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
          type="epcs"
        />
      )}

      {signTarget && (
        <SignEpcsModal
          rx={signTarget}
          onClose={() => setSignTarget(null)}
          onSuccess={() => setSignTarget(null)}
        />
      )}
    </div>
  );
}

function SignEpcsModal({
  rx,
  onClose,
  onSuccess,
}: {
  rx: EPCSPrescriptionRead;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const { t } = useI18n();
  const signEpcs = useEpcsStore((s) => s.signEpcs);
  const [prescriberId, setPrescriberId] = useState(String(rx.prescriber_id ?? ""));
  const [otpCode, setOtpCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prescriberId || !otpCode) {
      setError("Prescriber ID and OTP code are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await signEpcs(rx.id, {
        prescription_id: rx.id,
        prescriber_id: Number(prescriberId),
        otp_code: otpCode,
      });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1a2e] border border-gray-700 rounded-lg w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">EPCS 2FA Signing</h3>
          <button onClick={onClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-lg">×</button>
        </div>
        <form onSubmit={(e) => void handleSubmit(e)} className="p-5 space-y-4">
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Sign Rx #{rx.id} — {rx.product_name} ({rx.schedule})
          </p>
          {error && (
            <div className="bg-red-600/15 border border-red-600/30 text-red-400 text-xs px-3 py-2 rounded">
              {error}
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-1">Prescriber ID</label>
            <input id="epcsdashboard-field-1"
              type="number"
              value={prescriberId}
              onChange={(e) => setPrescriberId(e.target.value)}
              className="w-full bg-[#0d0d20] border border-gray-700 rounded px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Prescriber ID"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-2">TOTP Code (from authenticator)</label>
            <input id="epcsdashboard-field-2"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
              className="w-full bg-[#0d0d20] border border-gray-700 rounded px-3 py-2 text-sm text-gray-800 dark:text-gray-100 tracking-widest font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="000000"
              required
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !prescriberId || !otpCode}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded transition-colors disabled:opacity-40"
            >
              {saving ? "Signing..." : "Sign Prescription"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CreateEpcsModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diagnosisCodes, setDiagnosisCodes] = useState<string[]>([""]);
  const [form, setForm] = useState({
    patient_id: "",
    prescriber_id: "",
    product_name: "",
    ndc_code: "",
    schedule: "C-II",
    quantity: 1,
    days_supply: 30,
    sig_code: "QD",
    refills: 0,
    daw_code: "00",
    notes: "",
    diagnosis_codes: [],
  });

  const addDiagnosis = () => setDiagnosisCodes([...diagnosisCodes, ""]);
  const removeDiagnosis = (idx: number) => setDiagnosisCodes(diagnosisCodes.filter((_, i) => i !== idx));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.patient_id || !form.prescriber_id || !form.product_name) {
      setError(t("epcs.requiredFields"));
      return;
    }
    if (form.schedule === "C-II" && form.refills > 0) {
      setError(t("epcs.c2NoRefills"));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await epcsApi.createEpcsPrescription({
        patient_id: Number(form.patient_id),
        prescriber_id: Number(form.prescriber_id),
        product_name: form.product_name.trim(),
        ndc_code: form.ndc_code || undefined,
        schedule: form.schedule as "C-II" | "C-III" | "C-IV" | "C-V",
        quantity: Number(form.quantity),
        days_supply: Number(form.days_supply),
        sig_code: form.sig_code,
        diagnosis_codes: form.diagnosis_codes,
        refills: Number(form.refills),
        daw_code: form.daw_code,
        notes: form.notes,
      });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-3xl rounded-lg bg-gray-800 p-6 shadow-xl max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("epcs.newPrescription")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <DiagnosisSection diagnosisCodes={diagnosisCodes} setDiagnosisCodes={setDiagnosisCodes} t={t} />
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-3">{t("epcs.fieldPatient")}</label>
              <input id="epcsdashboard-field-3"
                type="number"
                placeholder={t("epcs.patientIdPlaceholder")}
                value={form.patient_id}
                onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-4">{t("epcs.fieldPrescriber")}</label>
              <input id="epcsdashboard-field-4"
                type="number"
                placeholder={t("epcs.prescriberIdPlaceholder")}
                value={form.prescriber_id}
                onChange={(e) => setForm({ ...form, prescriber_id: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-5">{t("epcs.fieldDrug")}</label>
              <input id="epcsdashboard-field-5"
                type="text"
                value={form.product_name}
                onChange={(e) => setForm({ ...form, product_name: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-6">{t("epcs.fieldNdc")}</label>
              <input id="epcsdashboard-field-6"
                type="text"
                value={form.ndc_code}
                onChange={(e) => setForm({ ...form, ndc_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-7">{t("epcs.fieldSchedule")}</label>
              <select id="epcsdashboard-field-7"
                value={form.schedule}
                onChange={(e) => setForm({ ...form, schedule: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              >
                <option value="C-II">{t("epcs.scheduleC2")}</option>
                <option value="C-III">{t("epcs.scheduleC3")}</option>
                <option value="C-IV">{t("epcs.scheduleC4")}</option>
                <option value="C-V">{t("epcs.scheduleC5")}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-8">{t("epcs.fieldQuantity")}</label>
              <input id="epcsdashboard-field-8"
                type="number"
                min="1"
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-9">{t("epcs.fieldDaysSupply")}</label>
              <input id="epcsdashboard-field-9"
                type="number"
                min="1"
                value={form.days_supply}
                onChange={(e) => setForm({ ...form, days_supply: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-10">{t("epcs.fieldSig")}</label>
              <input id="epcsdashboard-field-10"
                type="text"
                value={form.sig_code}
                onChange={(e) => setForm({ ...form, sig_code: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-11">{t("epcs.fieldRefills")}</label>
              <input id="epcsdashboard-field-11"
                type="number"
                min="0"
                max="5"
                value={form.refills}
                onChange={(e) => setForm({ ...form, refills: Number(e.target.value) })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-12">{t("epcs.fieldDaw")}</label>
              <input id="epcsdashboard-field-12"
                type="text"
                value={form.daw_code}
                onChange={(e) => setForm({ ...form, daw_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>

          <DiagnosisSection diagnosisCodes={diagnosisCodes} setDiagnosisCodes={setDiagnosisCodes} t={t} />

          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="epcsdashboard-field-13">{t("epcs.fieldNotes")}</label>
            <textarea id="epcsdashboard-field-13"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button type="button" onClick={onClose} disabled={saving} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-70">
              {saving ? "Creating..." : t("epcs.create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DeleteConfirmModal({ item, onClose, onConfirm, type }: { item: EPCSPrescriptionRead; onClose: () => void; onConfirm: () => Promise<void>; type: "epcs" }) {
  const { t } = useI18n();
  const [submitting, setSubmitting] = useState(false);

  const handleConfirm = async () => {
    setSubmitting(true);
    try {
      await onConfirm();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-sm rounded-lg bg-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2">{t("epcs.deleteTitle")}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          <span className="font-medium">{item.product_name}</span> {t("epcs.deleteConfirm")}
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-70"
          >
            {submitting ? "Deleting..." : t("epcs.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}