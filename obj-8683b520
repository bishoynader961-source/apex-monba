"use client";

import { useEffect, useState, useMemo } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useI18n } from "@/components/I18nProvider";
import { useAuthStore, useCan } from "@/stores/authStore";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import type { PrescriberCreate, PrescriberRead } from "@/types/contracts";
import * as prescribersApi from "@/lib/api/prescribers";

const EMPTY_FORM: PrescriberCreate = {
  first_name: "",
  last_name: "",
  npi: "",
  dea_number: "",
  state_license: "",
  phone: "",
  fax: "",
  email: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  zip: "",
  quick_code: "",
};

export default function PrescribersPage() {
  const canRead = useCan("patients.read");
  const canWrite = useCan("patients.write");
  const user = useAuthStore((s) => s.user);
  const { t } = useI18n();

  const [prescribers, setPrescribers] = useState<PrescriberRead[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<PrescriberCreate>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (canRead) loadPrescribers();
  }, [canRead]);

  async function loadPrescribers() {
    setLoading(true);
    setError(null);
    try {
      const data = await prescribersApi.listPrescribers({ search: search || undefined });
      setPrescribers(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load prescribers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(loadPrescribers, 300);
    return () => clearTimeout(timer);
  }, [search]);

  function openCreate() {
    setForm({ ...EMPTY_FORM });
    setEditingId(null);
    setShowForm(true);
  }

  function openEdit(p: PrescriberRead) {
    setForm({
      first_name: p.first_name,
      last_name: p.last_name,
      npi: p.npi ?? "",
      dea_number: p.dea_number ?? "",
      state_license: p.state_license ?? "",
      phone: p.phone ?? "",
      fax: p.fax ?? "",
      email: p.email ?? "",
      address_line1: p.address_line1 ?? "",
      address_line2: p.address_line2 ?? "",
      city: p.city ?? "",
      state: p.state ?? "",
      zip: p.zip ?? "",
      quick_code: p.quick_code ?? "",
    });
    setEditingId(p.id);
    setShowForm(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      if (editingId) {
        await prescribersApi.updatePrescriber(editingId, form);
      } else {
        await prescribersApi.createPrescriber(form);
      }
      setShowForm(false);
      loadPrescribers();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save prescriber");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Are you sure you want to delete this prescriber?")) return;
    try {
      await prescribersApi.deletePrescriber(id);
      loadPrescribers();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete prescriber");
    }
  }

  const columns = useMemo<Column<PrescriberRead>[]>(() => [
    { key: "name", header: t("prescribers.colName"), render: (row: PrescriberRead) => `${row.last_name}, ${row.first_name}` },
    { key: "npi", header: t("prescribers.colNpi"), render: (row: PrescriberRead) => row.npi || "—" },
    { key: "dea_number", header: t("prescribers.colDea"), render: (row: PrescriberRead) => row.dea_number || "—" },
    { key: "phone", header: t("prescribers.colPhone"), render: (row: PrescriberRead) => row.phone || "—" },
    { key: "email", header: t("prescribers.colEmail"), render: (row: PrescriberRead) => row.email || "—" },
    { key: "city", header: t("prescribers.colCity"), render: (row: PrescriberRead) => row.city || "—" },
    { key: "state", header: t("prescribers.colState"), render: (row: PrescriberRead) => row.state || "—" },
  ], [t]);

  if (!canRead) {
    return (
      <DashboardLayout>
        <div className="text-gray-600 dark:text-gray-400">You do not have permission to view prescribers.</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-6 max-w-[1200px] mx-auto">
        <div className="flex justify-between items-center mb-5">
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">{t("prescribers.title")}</h1>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder={t("prescribers.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-800 rounded-md w-[280px] bg-[#0d0d20] text-gray-800 dark:text-gray-100"
            />
            {canWrite && (
              <button
                onClick={openCreate}
                className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-md hover:bg-blue-700"
              >
                {t("prescribers.addPrescriber")}
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="px-3 py-3 mb-4 bg-red-900/30 text-red-300 border border-red-800 rounded-md">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-10 text-gray-600 dark:text-gray-400">{t("prescribers.loading")}</div>
        ) : prescribers.length === 0 ? (
          <div className="text-center py-10 text-gray-600 dark:text-gray-400">
            {t("prescribers.noResults")} {canWrite && t("prescribers.addHint")}
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={prescribers}
            keyExtractor={(row) => row.id}
            loading={loading}
            emptyMessage={t("prescribers.noResults")}
            actions={canWrite ? {
              header: t("commonActions"),
              render: (row) => (
                <div className="flex gap-2">
                  <button onClick={() => openEdit(row)} className="text-xs text-blue-400 hover:text-blue-300">
                    {t("prescribers.edit")}
                  </button>
                  <button onClick={() => handleDelete(row.id)} className="text-xs text-red-400 hover:text-red-300">
                    {t("prescribers.delete")}
                  </button>
                </div>
              )
            } : undefined}
            className="bg-[#111] border border-gray-800"
          />
        )}

        {/* Create/Edit Modal */}
        {showForm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}
          >
            <div className="w-[600px] max-h-[80vh] overflow-y-auto rounded-xl bg-[#111] p-6 border border-gray-800 shadow-xl">
              <h2 className="text-lg font-bold mb-4 text-gray-800 dark:text-gray-100">
                {editingId ? t("prescribers.modalEdit") : t("prescribers.modalAdd")}
              </h2>

              <div className="grid grid-cols-2 gap-3">
                <FormField label={t("prescribers.fieldFirstName")} value={form.first_name} onChange={(v) => setForm({ ...form, first_name: v })} />
                <FormField label={t("prescribers.fieldLastName")} value={form.last_name} onChange={(v) => setForm({ ...form, last_name: v })} />
                <FormField label={t("prescribers.fieldNpi")} value={form.npi ?? ""} onChange={(v) => setForm({ ...form, npi: v })} />
                <FormField label={t("prescribers.fieldDeaNumber")} value={form.dea_number ?? ""} onChange={(v) => setForm({ ...form, dea_number: v })} />
                <FormField label={t("prescribers.fieldStateLicense")} value={form.state_license ?? ""} onChange={(v) => setForm({ ...form, state_license: v })} />
                <FormField label={t("prescribers.fieldQuickCode")} value={form.quick_code ?? ""} onChange={(v) => setForm({ ...form, quick_code: v })} />
                <FormField label={t("prescribers.fieldPhone")} value={form.phone ?? ""} onChange={(v) => setForm({ ...form, phone: v })} />
                <FormField label={t("prescribers.fieldFax")} value={form.fax ?? ""} onChange={(v) => setForm({ ...form, fax: v })} />
                <FormField label={t("prescribers.fieldEmail")} value={form.email ?? ""} onChange={(v) => setForm({ ...form, email: v })} fullWidth />
                <FormField label={t("prescribers.fieldAddressLine1")} value={form.address_line1 ?? ""} onChange={(v) => setForm({ ...form, address_line1: v })} fullWidth />
                <FormField label={t("prescribers.fieldAddressLine2")} value={form.address_line2 ?? ""} onChange={(v) => setForm({ ...form, address_line2: v })} fullWidth />
                <FormField label={t("prescribers.fieldCity")} value={form.city ?? ""} onChange={(v) => setForm({ ...form, city: v })} />
                <FormField label={t("prescribers.fieldStateLabel")} value={form.state ?? ""} onChange={(v) => setForm({ ...form, state: v })} />
                <FormField label={t("prescribers.fieldZip")} value={form.zip ?? ""} onChange={(v) => setForm({ ...form, zip: v })} />
              </div>

              <div className="flex justify-end gap-2 mt-5">
                <button
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-sm text-gray-300 bg-gray-800 rounded-md hover:bg-gray-700"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !form.first_name || !form.last_name}
                  className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? t("common.saving") : editingId ? t("prescribers.update") : t("prescribers.create")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

function FormField({ label, value, onChange, fullWidth }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  fullWidth?: boolean;
}) {
  return (
    <div className={`flex flex-col gap-1 ${fullWidth ? "col-span-2" : ""}`}>
      <label className="text-xs font-semibold text-gray-600 dark:text-gray-400" htmlFor="page-field-1">{label}</label>
      <input id="page-field-1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-2 py-1.5 text-[13px] border border-gray-800 rounded-md w-full bg-[#0d0d20] text-gray-800 dark:text-gray-100"
      />
    </div>
  );
}
