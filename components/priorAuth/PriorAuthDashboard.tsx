"use client";

import { useEffect, useState } from "react";

import { useCan } from "@/stores/authStore";
import { usePriorAuthStore, usePriorAuths, usePATotal, usePALoading, usePAError, usePAFilters } from "@/stores/priorAuthStore";
import * as priorAuthApi from "@/lib/api/priorAuth";
import type { PriorAuthRead, PriorAuthCreate, PriorAuthUpdate, PriorAuthStatusTransition, PriorAuthFilters } from "@/types/contracts";
import { useI18n } from "@/components/I18nProvider";

const PAGE_SIZE = 50;

const STATUS_COLORS: Record<string, string> = {
  SUBMITTED: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  PENDING_REVIEW: "bg-yellow-900/30 text-yellow-400 border-yellow-600/40",
  APPROVED: "bg-green-900/30 text-green-400 border-green-600/40",
  DENIED: "bg-red-900/30 text-red-400 border-red-600/40",
  EXPIRED: "bg-gray-700 text-gray-400 border-gray-600/40",
  WITHDRAWN: "bg-purple-900/30 text-purple-400 border-purple-600/40",
};

const VALID_TRANSITIONS: Record<string, string[]> = {
  SUBMITTED: ["PENDING_REVIEW", "WITHDRAWN"],
  PENDING_REVIEW: ["APPROVED", "DENIED", "WITHDRAWN"],
  APPROVED: ["EXPIRED"],
  DENIED: ["SUBMITTED"],
  EXPIRED: ["SUBMITTED"],
  WITHDRAWN: ["SUBMITTED"],
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-gray-700 text-gray-300";
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${color}`}>
      {status}
    </span>
  );
}

function ActionMenu({
  pa,
  onTransition,
  onWithdraw,
  canReview,
  canWrite,
}: {
  pa: PriorAuthRead;
  onTransition: (id: number, payload: PriorAuthStatusTransition) => Promise<void>;
  onWithdraw: (id: number) => Promise<PriorAuthRead>;
  canReview: boolean;
  canWrite: boolean;
}) {
  const [open, setOpen] = useState(false);
  const currentStatus = pa.status;
  const allowed = canReview ? (VALID_TRANSITIONS[currentStatus] || []) : [];

  if (allowed.length === 0 && !canWrite) {
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
                  const payload: PriorAuthStatusTransition = { status: status as any };
                  if (status === "APPROVED") {
                    const authNum = prompt("Enter Prior Auth Number:");
                    if (!authNum) { setOpen(false); return; }
                    const days = prompt("Approval duration (days):", "365");
                    if (!days) { setOpen(false); return; }
                    payload.prior_auth_number = authNum;
                    payload.approval_duration_days = parseInt(days, 10);
                  }
                  if (status === "DENIED") {
                    const reason = prompt("Denial reason:");
                    if (!reason) { setOpen(false); return; }
                    payload.denial_reason = reason;
                  }
                  onTransition(pa.id, payload);
                  setOpen(false);
                }}
                className="w-full px-3 py-2 text-left text-sm text-gray-100 hover:bg-gray-700"
              >
                {status}
              </button>
            ))}
            {canWrite && allowed.includes("WITHDRAWN") && (
              <button
                onClick={() => { onWithdraw(pa.id); setOpen(false); }}
                className="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-gray-700"
              >
                Withdraw
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

export function PriorAuthDashboard() {
  const { t } = useI18n();
  const canRead = useCan("prior_auth.read");
  const canWrite = useCan("prior_auth.write");
  const canReview = useCan("prior_auth.review");

  const items = usePriorAuths();
  const total = usePATotal();
  const isLoading = usePALoading();
  const error = usePAError();
  const filters = usePAFilters();
  const { fetchPAs, setFilters, createPA, transitionStatus, withdrawPA, setSelectedPA } = usePriorAuthStore();

  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<PriorAuthRead | null>(null);
  const [reviewPayload, setReviewPayload] = useState<PriorAuthStatusTransition>({
    status: "PENDING_REVIEW",
    reviewer_notes: "",
    denial_reason: "",
    approval_duration_days: 365,
    prior_auth_number: "",
  });

  // Load on mount
  useEffect(() => {
    if (canRead) {
      fetchPAs();
    }
  }, [canRead, fetchPAs]);

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
  const paginated = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleCreateSubmit = async (payload: PriorAuthCreate) => {
    await createPA(payload);
    setCreateOpen(false);
  };

  const handleReviewSubmit = async () => {
    if (!reviewTarget) return;
    try {
      await transitionStatus(reviewTarget.id, reviewPayload);
      setReviewOpen(false);
      setReviewTarget(null);
    } catch (err) {
      console.error("Transition failed:", err);
    }
  };

  const handleWithdraw = async (id: number) => {
    if (!confirm("Withdraw this PA request?")) return;
    await withdrawPA(id);
  };

  if (!canRead) {
    return <p className="text-sm text-gray-600 dark:text-gray-400">{t("priorAuth.noPermission")}</p>;
  }

  return (
    <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 border-b border-gray-800">
        <h2 className="text-xl font-bold">{t("priorAuth.title")}</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setCreateOpen(true)}
            disabled={!canWrite}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
          >
            {t("priorAuth.newRequest")}
          </button>
        </div>
      </header>

      {error && <p className="px-4 py-2 text-sm text-red-400">{error}</p>}

      {/* Filters */}
      <div className="p-4 border-b border-gray-800 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <select
          value={filters.status ?? ""}
          onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">{t("priorAuth.allStatus")}</option>
          <option value="SUBMITTED">{t("priorAuth.statusSubmitted")}</option>
          <option value="PENDING_REVIEW">{t("priorAuth.statusPendingReview")}</option>
          <option value="APPROVED">{t("priorAuth.statusApproved")}</option>
          <option value="DENIED">{t("priorAuth.statusDenied")}</option>
          <option value="EXPIRED">{t("priorAuth.statusExpired")}</option>
          <option value="WITHDRAWN">{t("priorAuth.statusWithdrawn")}</option>
        </select>
        <input
          type="text"
          placeholder={t("priorAuth.searchProduct")}
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
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colId")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colPatient")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colPrescriber")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colDrug")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colQty")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colStatus")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colSubmitted")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.colActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                  {t("priorAuth.loading")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                  {t("priorAuth.noRequests")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.map((pa) => (
              <tr key={pa.id} className="hover:bg-gray-800/50">
                <td className="px-4 py-3 font-mono text-blue-400">{pa.id}</td>
                <td className="px-4 py-3 truncate max-w-[180px]">{pa.patient_name}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400 truncate max-w-[140px]">{pa.prescriber_name}</td>
                <td className="px-4 py-3 truncate max-w-[200px]">{pa.product_name}</td>
                <td className="px-4 py-3 text-center">{pa.quantity}</td>
                <td className="px-4 py-3 text-center">
                  <StatusBadge status={pa.status} />
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{pa.submitted_at.slice(0, 10)}</td>
                <td className="px-4 py-3">
                  <ActionMenu
                    pa={pa}
                    onTransition={async (id, payload) => {
                      await transitionStatus(id, payload);
                    }}
                    onWithdraw={withdrawPA}
                    canReview={canReview}
                    canWrite={canWrite}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="px-4 py-3 border-t border-gray-800 flex items-center justify-between">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          Page {page} of {totalPages} • {total} {t("priorAuth.requests")}
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
        <CreatePAModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

function CreatePAModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diagnosisCodes, setDiagnosisCodes] = useState<string[]>([""]);
  const [priorTherapy, setPriorTherapy] = useState<string[]>([""]);
  const [form, setForm] = useState({
    patient_id: "",
    prescriber_id: "",
    product_name: "",
    ndc_code: "",
    quantity: 1,
    days_supply: 30,
    sig_code: "QD",
    clinical_rationale: "",
    insurance_plan_id: "",
  });

  const addDiagnosis = () => setDiagnosisCodes([...diagnosisCodes, ""]);
  const removeDiagnosis = (idx: number) => setDiagnosisCodes(diagnosisCodes.filter((_, i) => i !== idx));
  const addPriorTherapy = () => setPriorTherapy([...priorTherapy, ""]);
  const removePriorTherapy = (idx: number) => setPriorTherapy(priorTherapy.filter((_, i) => i !== idx));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.patient_id || !form.prescriber_id || !form.product_name || !form.clinical_rationale.trim()) {
      setError(t("priorAuth.requiredFields"));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await priorAuthApi.createPriorAuth({
        patient_id: Number(form.patient_id),
        prescriber_id: Number(form.prescriber_id),
        product_name: form.product_name.trim(),
        ndc_code: form.ndc_code || undefined,
        quantity: Number(form.quantity),
        days_supply: Number(form.days_supply),
        sig_code: form.sig_code,
        diagnosis_codes: diagnosisCodes.filter((c) => c.trim()),
        clinical_rationale: form.clinical_rationale.trim(),
        prior_therapy_failed: priorTherapy.filter((p) => p.trim()),
        insurance_plan_id: form.insurance_plan_id ? Number(form.insurance_plan_id) : undefined,
        payer_specific_data: {},
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
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("priorAuth.newRequest")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-1">{t("priorAuth.fieldPatient")}</label>
              <input id="priorauthdashboard-field-1"
                type="number"
                placeholder={t("priorAuth.patientIdPlaceholder")}
                value={form.patient_id}
                onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-2">{t("priorAuth.fieldPrescriber")}</label>
              <input id="priorauthdashboard-field-2"
                type="number"
                placeholder={t("priorAuth.prescriberIdPlaceholder")}
                value={form.prescriber_id}
                onChange={(e) => setForm({ ...form, prescriber_id: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-3">{t("priorAuth.fieldDrug")}</label>
              <input id="priorauthdashboard-field-3"
                type="text"
                value={form.product_name}
                onChange={(e) => setForm({ ...form, product_name: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-4">{t("priorAuth.fieldNdc")}</label>
              <input id="priorauthdashboard-field-4"
                type="text"
                value={form.ndc_code}
                onChange={(e) => setForm({ ...form, ndc_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-5">{t("priorAuth.fieldQuantity")}</label>
              <input id="priorauthdashboard-field-5"
                type="number"
                min="1"
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-6">{t("priorAuth.fieldDaysSupply")}</label>
              <input id="priorauthdashboard-field-6"
                type="number"
                min="1"
                value={form.days_supply}
                onChange={(e) => setForm({ ...form, days_supply: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-7">{t("priorAuth.fieldSig")}</label>
              <input id="priorauthdashboard-field-7"
                type="text"
                value={form.sig_code}
                onChange={(e) => setForm({ ...form, sig_code: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-8">{t("priorAuth.fieldInsurancePlan")}</label>
              <input id="priorauthdashboard-field-8"
                type="number"
                placeholder="ID"
                value={form.insurance_plan_id}
                onChange={(e) => setForm({ ...form, insurance_plan_id: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="priorauthdashboard-field-9">{t("priorAuth.fieldRationale")}</label>
            <textarea id="priorauthdashboard-field-9"
              value={form.clinical_rationale}
              onChange={(e) => setForm({ ...form, clinical_rationale: e.target.value })}
              rows={4}
              required
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>

          <div className="border-t border-gray-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.diagnosisCodes")}</h3>
              <button
                type="button"
                onClick={addDiagnosis}
                className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                + {t("priorAuth.addDiagnosis")}
              </button>
            </div>
            {diagnosisCodes.map((code, idx) => (
              <div key={idx} className="flex gap-2 mb-2">
                <input
                  type="text"
                  placeholder={t("priorAuth.icd10Placeholder")}
                  value={code}
                  onChange={(e) => setDiagnosisCodes(diagnosisCodes.map((c, i) => i === idx ? e.target.value : c))}
                  className="flex-1 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                {diagnosisCodes.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeDiagnosis(idx)}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="border-t border-gray-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("priorAuth.priorTherapy")}</h3>
              <button
                type="button"
                onClick={() => setPriorTherapy([...priorTherapy, ""])}
                className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                + {t("priorAuth.addTherapy")}
              </button>
            </div>
            {priorTherapy.map((therapy, idx) => (
              <div key={idx} className="flex gap-2 mb-2">
                <input
                  type="text"
                  placeholder={t("priorAuth.drugNamePlaceholder")}
                  value={therapy}
                  onChange={(e) => setPriorTherapy(priorTherapy.map((t, i) => i === idx ? e.target.value : t))}
                  className="flex-1 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                {priorTherapy.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setPriorTherapy(priorTherapy.filter((_, i) => i !== idx))}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button type="button" onClick={onClose} disabled={saving} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-70">
              {saving ? "Creating..." : t("priorAuth.create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}