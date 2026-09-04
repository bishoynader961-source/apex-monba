"use client";

import { useEffect, useState } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useI18n } from "@/components/I18nProvider";
import { useAuthStore, useCan } from "@/stores/authStore";
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

  if (!canRead) {
    return (
      <DashboardLayout>
        <div className="text-gray-400">You do not have permission to view prescribers.</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-6 max-w-[1200px] mx-auto">
        <div className="flex justify-between items-center mb-5">
          <h1 className="text-2xl font-bold text-gray-100">{t("prescribers.title")}</h1>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder={t("prescribers.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-800 rounded-md w-[280px] bg-[#0d0d20] text-gray-100"
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
          <div className="text-center py-10 text-gray-400">{t("prescribers.loading")}</div>
        ) : prescribers.length === 0 ? (
          <div className="text-center py-10 text-gray-400">
            {t("prescribers.noResults")} {canWrite && t("prescribers.addHint")}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b-2 border-gray-800 text-left">
                  <th className="px-3 py-2">{t("prescribers.colName")}</th>
                  <th className="px-3 py-2">{t("prescribers.colNpi")}</th>
                  <th className="px-3 py-2">{t("prescribers.colDea")}</th>
                  <th className="px-3 py-2">{t("prescribers.colPhone")}</th>
                  <th className="px-3 py-2">{t("prescribers.colEmail")}</th>
                  <th className="px-3 py-2">{t("prescribers.colCity")}</th>
                  <th className="px-3 py-2">{t("prescribers.colState")}</th>
                  {canWrite && <th className="px-3 py-2">{t("commonActions")}</th>}
                </tr>
              </thead>
              <tbody>
                {prescribers.map((p) => (
                  <tr key={p.id} className="border-b border-gray-800">
                    <td className="px-3 py-2 font-medium text-gray-100">
                      {p.last_name}, {p.first_name}
                    </td>
                    <td className="px-3 py-2 font-mono text-gray-300">{p.npi || "—"}</td>
                    <td className="px-3 py-2 font-mono text-gray-300">{p.dea_number || "—"}</td>
                    <td className="px-3 py-2 text-gray-300">{p.phone || "—"}</td>
                    <td className="px-3 py-2 text-gray-300">{p.email || "—"}</td>
                    <td className="px-3 py-2 text-gray-300">{p.city || "—"}</td>
                    <td className="px-3 py-2 text-gray-300">{p.state || "—"}</td>
                    {canWrite && (
                      <td className="px-3 py-2">
                        <button
                          onClick={() => openEdit(p)}
                          className="mr-2 px-2 py-1 text-xs text-blue-400 border border-gray-700 rounded hover:bg-gray-800"
                        >
                          {t("prescribers.edit")}
                        </button>
                        <button
                          onClick={() => handleDelete(p.id)}
                          className="px-2 py-1 text-xs text-red-400 border border-red-900 rounded hover:bg-red-900/30"
                        >
                          {t("prescribers.delete")}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Create/Edit Modal */}
        {showForm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}
          >
            <div className="w-[600px] max-h-[80vh] overflow-y-auto rounded-xl bg-[#111] p-6 border border-gray-800 shadow-xl">
              <h2 className="text-lg font-bold mb-4 text-gray-100">
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
      <label className="text-xs font-semibold text-gray-400">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-2 py-1.5 text-[13px] border border-gray-800 rounded-md w-full bg-[#0d0d20] text-gray-100"
      />
    </div>
  );
}
