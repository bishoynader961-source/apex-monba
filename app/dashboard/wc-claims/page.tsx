"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, useMemo } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useI18n } from "@/components/I18nProvider";
import { useAuthStore, useCan } from "@/stores/authStore";
import type { WCClaimCreate, WCClaimRead } from "@/types/contracts";
import * as wcApi from "@/lib/api/wc";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";

const STATUS_OPTIONS = ["open", "pending_approval", "approved", "denied", "closed"] as const;
const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-100 text-blue-800",
  pending_approval: "bg-yellow-100 text-yellow-800",
  approved: "bg-green-100 text-green-800",
  denied: "bg-red-100 text-red-800",
  closed: "bg-gray-100 text-gray-600",
};

const EMPTY_FORM: WCClaimCreate = {
  patient_id: 0,
  claim_number: "",
  carrier_id: "",
  carrier_name: "",
  injury_date: "",
  injury_description: "",
  employer_name: "",
  employer_address: "",
  employer_phone: "",
  status: "open",
  total_charges: "0",
  insurance_paid: "0",
  patient_responsibility: "0",
  notes: "",
};

export default function WCClaimsPage() {
  const searchParams = useSearchParams();
  const patientIdFilter = searchParams.get("patient_id");
  const canRead = useCan("patients.read");
  const canWrite = useCan("patients.write");
  const user = useAuthStore((s) => s.user);
  const { t } = useI18n();

  const [claims, setClaims] = useState<WCClaimRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<WCClaimCreate>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (canRead) loadClaims();
  }, [canRead, statusFilter, patientIdFilter]);

  async function loadClaims() {
    setLoading(true);
    setError(null);
    try {
      const data = await wcApi.listWCClaims({
        status: statusFilter || undefined,
        patient_id: patientIdFilter ? Number(patientIdFilter) : undefined,
      });
      setClaims(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load WC claims");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadClaims();
  }, [statusFilter, patientIdFilter]);

  function openCreate() {
    setEditingId(null);
    setForm({ ...EMPTY_FORM, patient_id: patientIdFilter ? Number(patientIdFilter) : (claims[0]?.patient_id ?? 0) });
    setShowForm(true);
  }

  function openEdit(claim: WCClaimRead) {
    setEditingId(claim.id);
    setForm({
      patient_id: claim.patient_id,
      claim_number: claim.claim_number,
      carrier_id: claim.carrier_id ?? "",
      carrier_name: claim.carrier_name ?? "",
      injury_date: claim.injury_date ?? "",
      injury_description: claim.injury_description ?? "",
      employer_name: claim.employer_name ?? "",
      employer_address: claim.employer_address ?? "",
      employer_phone: claim.employer_phone ?? "",
      status: claim.status,
      total_charges: claim.total_charges ?? "0",
      insurance_paid: claim.insurance_paid ?? "0",
      patient_responsibility: claim.patient_responsibility ?? "0",
      notes: claim.notes ?? "",
    });
    setShowForm(true);
  }

  async function handleSave() {
    if (!form.claim_number.trim() || !form.patient_id) return;
    setSaving(true);
    try {
      if (editingId) {
        await wcApi.updateWCClaim(editingId, form);
      } else {
        await wcApi.createWCClaim(form);
      }
      setShowForm(false);
      await loadClaims();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this WC claim?")) return;
    try {
      await wcApi.deleteWCClaim(id);
      await loadClaims();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  }

  const columns = useMemo<Column<WCClaimRead>[]>(() => [
    { key: "claim_number", header: t("wcClaims.colClaimNumber"), render: (row: WCClaimRead) => row.claim_number },
    { key: "patient_id", header: t("wcClaims.colPatientId"), render: (row: WCClaimRead) => row.patient_id },
    { key: "carrier_name", header: t("wcClaims.colCarrier"), render: (row: WCClaimRead) => row.carrier_name || "—" },
    { key: "injury_date", header: t("wcClaims.colInjuryDate"), render: (row: WCClaimRead) => row.injury_date || "—" },
    { key: "status", header: t("wcClaims.colStatus"), render: (row: WCClaimRead) => (
      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[row.status ?? "open"] ?? "bg-gray-800 text-gray-400"}`}>
        {(row.status ?? "open").replace("_", " ")}
      </span>
    )},
    { key: "total_charges", header: t("wcClaims.colCharges"), render: (row: WCClaimRead) => Number(row.total_charges).toFixed(2), className: "text-right" },
    { key: "insurance_paid", header: t("wcClaims.colInsurancePaid"), render: (row: WCClaimRead) => Number(row.insurance_paid).toFixed(2), className: "text-right" },
    { key: "patient_responsibility", header: t("wcClaims.colPatientResp"), render: (row: WCClaimRead) => Number(row.patient_responsibility).toFixed(2), className: "text-right" },
], [t]);

  return (
    <DashboardLayout>
      <RouteGuard permission="wc.read">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-800 dark:text-gray-100">{t("wcClaims.title")}</h1>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-1">{t("wcClaims.filterByStatus")}</label>
        <select id="page-field-1"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100"
        >
          <option value="">{t("wcClaims.statusAll")}</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </select>
        {canWrite && (
          <button onClick={openCreate} className="ml-auto rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
            {t("wcClaims.newClaim")}
          </button>
        )}
      </div>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">{t("wcClaims.loading")}</p>
      ) : claims.length === 0 ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">{t("wcClaims.noResults")}</p>
) : (
          <DataTable
            columns={columns}
            data={claims}
            keyExtractor={(row) => row.id}
            loading={loading}
            emptyMessage={t("wcClaims.noResults")}
            actions={canWrite ? {
              header: t("commonActions"),
              render: (row) => (
                <div className="flex gap-2">
                  <button onClick={() => openEdit(row)} className="text-blue-400 hover:underline">{t("wcClaims.edit")}</button>
                  <button onClick={() => handleDelete(row.id)} className="text-red-400 hover:underline">{t("wcClaims.delete")}</button>
                </div>
              )
            } : undefined}
            className="bg-[#111] border border-gray-800"
          />
        )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-lg bg-[#111] border border-gray-800 p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-bold text-gray-800 dark:text-gray-100">{editingId ? t("wcClaims.modalEdit") : t("wcClaims.modalNew")}</h2>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-2">{t("wcClaims.fieldPatientId")}</label>
                  <input id="page-field-2" type="number" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.patient_id || ""} onChange={(e) => setForm((f) => ({ ...f, patient_id: Number(e.target.value) }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-3">{t("wcClaims.fieldClaimNumber")}</label>
                  <input id="page-field-3" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.claim_number} onChange={(e) => setForm((f) => ({ ...f, claim_number: e.target.value }))} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-4">{t("wcClaims.fieldCarrierName")}</label>
                  <input id="page-field-4" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.carrier_name ?? ""} onChange={(e) => setForm((f) => ({ ...f, carrier_name: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-5">{t("wcClaims.fieldCarrierId")}</label>
                  <input id="page-field-5" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.carrier_id ?? ""} onChange={(e) => setForm((f) => ({ ...f, carrier_id: e.target.value }))} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-6">{t("wcClaims.fieldInjuryDate")}</label>
                  <input id="page-field-6" type="date" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.injury_date ?? ""} onChange={(e) => setForm((f) => ({ ...f, injury_date: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-7">{t("wcClaims.fieldStatus")}</label>
                  <select id="page-field-7" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                    {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-8">{t("wcClaims.fieldInjuryDescription")}</label>
                <textarea id="page-field-8" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" rows={2} value={form.injury_description ?? ""} onChange={(e) => setForm((f) => ({ ...f, injury_description: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-9">{t("wcClaims.fieldEmployerName")}</label>
                  <input id="page-field-9" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.employer_name ?? ""} onChange={(e) => setForm((f) => ({ ...f, employer_name: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-10">{t("wcClaims.fieldEmployerPhone")}</label>
                  <input id="page-field-10" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.employer_phone ?? ""} onChange={(e) => setForm((f) => ({ ...f, employer_phone: e.target.value }))} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-11">{t("wcClaims.fieldTotalCharges")}</label>
                  <input id="page-field-11" type="number" step="0.01" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.total_charges ?? "0"} onChange={(e) => setForm((f) => ({ ...f, total_charges: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-12">{t("wcClaims.fieldInsurancePaid")}</label>
                  <input id="page-field-12" type="number" step="0.01" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.insurance_paid ?? "0"} onChange={(e) => setForm((f) => ({ ...f, insurance_paid: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-13">{t("wcClaims.fieldPatientResponsibility")}</label>
                  <input id="page-field-13" type="number" step="0.01" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" value={form.patient_responsibility ?? "0"} onChange={(e) => setForm((f) => ({ ...f, patient_responsibility: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor="page-field-14">{t("wcClaims.fieldNotes")}</label>
                <textarea id="page-field-14" className="mt-1 w-full rounded border border-gray-800 bg-[#0d0d20] px-2 py-1 text-sm text-gray-800 dark:text-gray-100" rows={2} value={form.notes ?? ""} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setShowForm(false)} className="rounded border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800">{t("common.cancel")}</button>
              <button onClick={() => void handleSave()} disabled={saving || !form.claim_number.trim()} className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? t("common.saving") : t("common.save")}
              </button>
            </div>
          </div>
        </div>
      )}
      </RouteGuard>
    </DashboardLayout>
  );
}
