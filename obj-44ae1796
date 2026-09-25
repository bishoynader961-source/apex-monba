"use client";

import { useEffect, useState } from "react";

import { useCan } from "@/stores/authStore";
import { useCompoundStore, useCompounds, useCompoundLoading, useCompoundError } from "@/stores/compoundStore";
import * as compoundApi from "@/lib/api/compound";
import type {
  CompoundRead,
  CompoundIngredientRead,
  CompoundCreate,
  CompoundUpdate,
  CompoundIngredientCreate,
  CompoundDispenseRequest,
  CompoundPriceCalculationRequest,
  CompoundPriceCalculationResult,
} from "@/types/contracts";
import { useI18n } from "@/components/I18nProvider";
import { formatMoney, parseMoney, mulByQty } from "@/lib/decimalCurrency";

const PAGE_SIZE = 50;

export function CompoundDashboard() {
  const { t } = useI18n();
  const canRead = useCan("compounds.read");
  const canWrite = useCan("compounds.write");
  const canDispense = useCan("compounds.dispense");

  const compounds = useCompounds();
  const isLoading = useCompoundLoading();
  const error = useCompoundError();
  const { fetchCompounds, createCompound, updateCompound, deleteCompound, setSelectedCompound } = useCompoundStore();

  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<CompoundRead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CompoundRead | null>(null);
  const [dispenseOpen, setDispenseOpen] = useState(false);
  const [priceOpen, setPriceOpen] = useState(false);

  // Load on mount
  useEffect(() => {
    if (canRead) {
      fetchCompounds();
    }
  }, [canRead, fetchCompounds]);

  const totalPages = Math.ceil(compounds.length / PAGE_SIZE) || 1;
  const paginated = compounds.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleCreateSubmit = async (payload: CompoundCreate) => {
    await createCompound(payload);
    setCreateOpen(false);
  };

  const handleEditSubmit = async (payload: CompoundUpdate) => {
    if (!editTarget) return;
    await updateCompound(editTarget.id, payload);
    setEditTarget(null);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteCompound(deleteTarget.id);
    setDeleteTarget(null);
  };

  if (!canRead) {
    return <p className="text-sm text-gray-600 dark:text-gray-400">{t("compounds.noPermission")}</p>;
  }

  return (
    <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 border-b border-gray-800">
        <h2 className="text-xl font-bold">{t("compounds.title")}</h2>
        {canWrite && (
          <div className="flex gap-2">
            <button
              onClick={() => setCreateOpen(true)}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium"
            >
              {t("compounds.newFormula")}
            </button>
          </div>
        )}
      </header>

      {error && <p className="px-4 py-2 text-sm text-red-400">{error}</p>}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-[800px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colName")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colTotalQty")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colIngredients")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colSig")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colRefills")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colPrescriber")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("compounds.colActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  {t("compounds.loading")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  {t("compounds.noFormulas")}
                </td>
              </tr>
            )}
            {!isLoading && paginated.map((c) => (
              <tr key={c.id} className="hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white truncate max-w-[200px]">{c.name}</td>
                <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{c.total_quantity} {c.total_quantity_unit}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{c.ingredients.length} {t("compounds.ingredientsCount")}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{c.sig_code}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{c.refill_count}/{c.refills_authorized}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400 truncate max-w-[140px]">{c.prescriber_name ?? "—"}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {canWrite && (
                      <button
                        onClick={() => setEditTarget(c)}
                        className="text-xs text-blue-400 hover:text-blue-300"
                      >
                        {t("compounds.edit")}
                      </button>
                    )}
                    {canDispense && (
                      <button
                        onClick={() => {
                          setSelectedCompound(c);
                          setDispenseOpen(true);
                        }}
                        className="text-xs text-purple-400 hover:text-purple-300"
                      >
                        {t("compounds.dispense")}
                      </button>
                    )}
                    {canWrite && (
                      <button
                        onClick={() => {
                          setSelectedCompound(c);
                          setPriceOpen(true);
                        }}
                        className="text-xs text-amber-400 hover:text-amber-300"
                      >
                        {t("compounds.price")}
                      </button>
                    )}
                    {canWrite && (
                      <button
                        onClick={() => setDeleteTarget(c)}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        {t("compounds.delete")}
                      </button>
                    )}
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
          {t("compounds.showing")} {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, compounds.length)} {t("compounds.of")} {compounds.length}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            {t("common.prev")}
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 text-sm border border-gray-600 rounded-md text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            {t("common.next")}
          </button>
        </div>
      </div>

      {/* Modals */}
      {createOpen && (
        <CreateCompoundModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => setCreateOpen(false)}
        />
      )}

      {editTarget && (
        <EditCompoundModal
          compound={editTarget}
          onClose={() => setEditTarget(null)}
          onSuccess={() => setEditTarget(null)}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          item={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
          type="compound"
        />
      )}

      {dispenseOpen && (
        <DispenseCompoundModal
          compound={useCompoundStore.getState().selectedCompound}
          onClose={() => setDispenseOpen(false)}
        />
      )}

      {priceOpen && (
        <CompoundPriceModal
          compound={useCompoundStore.getState().selectedCompound}
          onClose={() => setPriceOpen(false)}
        />
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface CreateCompoundModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

function CreateCompoundModal({ onClose, onSuccess }: CreateCompoundModalProps) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ingredients, setIngredients] = useState<Omit<CompoundIngredientCreate, "sequence">[]>([
    { product_name: "", quantity: 1, unit: "g", strength: "" },
  ]);
  const [form, setForm] = useState({
    name: "",
    description: "",
    total_quantity: 100,
    total_quantity_unit: "g",
    sig_code: "QD",
    days_supply: 30,
    refills_authorized: 0,
    prescriber_id: "",
    price_code: "",
  });

  const addIngredient = () => setIngredients([...ingredients, { product_name: "", quantity: 1, unit: "g", strength: "" }]);
  const removeIngredient = (idx: number) => setIngredients(ingredients.filter((_, i) => i !== idx));
  const updateIngredient = (idx: number, field: string, value: string | number) =>
    setIngredients(ingredients.map((ing, i) => (i === idx ? { ...ing, [field]: value } : ing)));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setError(t("compounds.nameRequired")); return; }
    if (ingredients.some((i) => !i.product_name.trim())) { setError(t("compounds.ingredientNameRequired")); return; }

    setSaving(true);
    setError(null);
    try {
      await compoundApi.createCompound({
        ...form,
        total_quantity: Number(form.total_quantity),
        days_supply: Number(form.days_supply),
        refills_authorized: Number(form.refills_authorized),
        prescriber_id: form.prescriber_id ? Number(form.prescriber_id) : undefined,
        price_code: form.price_code || undefined,
        ingredients: ingredients.map((ing, idx) => ({ ...ing, sequence: idx })),
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
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("compounds.createNewFormula")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-1">{t("compounds.fieldName")}</label>
              <input id="compounddashboard-field-1"
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-2">{t("compounds.fieldTotalQty")}</label>
              <input id="compounddashboard-field-2"
                type="number"
                step="0.01"
                min="0.01"
                value={form.total_quantity}
                onChange={(e) => setForm({ ...form, total_quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-3">{t("compounds.fieldQtyUnit")}</label>
              <select id="compounddashboard-field-3"
                value={form.total_quantity_unit}
                onChange={(e) => setForm({ ...form, total_quantity_unit: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              >
                <option value="g">{t("compounds.unitG")}</option>
                <option value="ml">{t("compounds.unitMl")}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-4">{t("compounds.fieldSig")}</label>
              <input id="compounddashboard-field-4"
                type="text"
                value={form.sig_code}
                onChange={(e) => setForm({ ...form, sig_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-5">{t("compounds.fieldDaysSupply")}</label>
              <input id="compounddashboard-field-5"
                type="number"
                min="1"
                value={form.days_supply}
                onChange={(e) => setForm({ ...form, days_supply: Number(e.target.value) })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-6">{t("compounds.fieldRefills")}</label>
              <input id="compounddashboard-field-6"
                type="number"
                min="0"
                value={form.refills_authorized}
                onChange={(e) => setForm({ ...form, refills_authorized: Number(e.target.value) })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-7">{t("compounds.fieldPrescriber")}</label>
              <input id="compounddashboard-field-7"
                type="number"
                placeholder="ID"
                value={form.prescriber_id}
                onChange={(e) => setForm({ ...form, prescriber_id: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-8">{t("compounds.fieldPriceCode")}</label>
              <input id="compounddashboard-field-8"
                type="text"
                value={form.price_code}
                onChange={(e) => setForm({ ...form, price_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-9">{t("compounds.fieldDescription")}</label>
            <textarea id="compounddashboard-field-9"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>

          <div className="border-t border-gray-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("compounds.ingredients")}</h3>
              <button
                type="button"
                onClick={addIngredient}
                className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                + {t("compounds.addIngredient")}
              </button>
            </div>
            {ingredients.map((ing, idx) => (
              <div key={idx} className="grid grid-cols-5 gap-2 mb-2">
                <input
                  type="text"
                  placeholder={t("compounds.ingredientProduct")}
                  value={ing.product_name}
                  onChange={(e) => updateIngredient(idx, "product_name", e.target.value)}
                  required
                  className="col-span-2 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder={t("compounds.ingredientQty")}
                  value={ing.quantity}
                  onChange={(e) => updateIngredient(idx, "quantity", Number(e.target.value))}
                  required
                  className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                <select
                  value={ing.unit}
                  onChange={(e) => updateIngredient(idx, "unit", e.target.value)}
                  className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                >
                  <option value="g">{t("compounds.unitG")}</option>
                  <option value="ml">{t("compounds.unitMl")}</option>
                </select>
<input
                    type="text"
                    placeholder={t("compounds.ingredientStrength")}
                    value={ing.strength ?? ""}
                    onChange={(e) => updateIngredient(idx, "strength", e.target.value)}
                    className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                  />
                {ingredients.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeIngredient(idx)}
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
              {saving ? "Creating..." : t("compounds.create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── EditCompoundModal ────────────────────────────────────────────────────────

interface EditCompoundModalProps {
  compound: CompoundRead;
  onClose: () => void;
  onSuccess: () => void;
}

function EditCompoundModal({ compound, onClose, onSuccess }: EditCompoundModalProps) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ingredients, setIngredients] = useState<Omit<CompoundIngredientCreate, "sequence">[]>(
    compound.ingredients.map((i) => ({
      product_name: i.product_name,
      quantity: i.quantity,
      unit: i.unit,
      strength: i.strength ?? "",
    }))
  );
  const [form, setForm] = useState({
    name: compound.name,
    description: compound.description ?? "",
    total_quantity: compound.total_quantity,
    total_quantity_unit: compound.total_quantity_unit,
    sig_code: compound.sig_code,
    days_supply: compound.days_supply,
    refills_authorized: compound.refills_authorized,
    prescriber_id: compound.prescriber_id?.toString() ?? "",
    price_code: compound.price_code ?? "",
  });

  const addIngredient = () => setIngredients([...ingredients, { product_name: "", quantity: 1, unit: "g", strength: "" }]);
  const removeIngredient = (idx: number) => setIngredients(ingredients.filter((_, i) => i !== idx));
  const updateIngredient = (idx: number, field: string, value: string | number) =>
    setIngredients(ingredients.map((ing, i) => (i === idx ? { ...ing, [field]: value } : ing)));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setError(t("compounds.nameRequired")); return; }
    if (ingredients.some((i) => !i.product_name.trim())) { setError(t("compounds.ingredientNameRequired")); return; }

    setSaving(true);
    setError(null);
    try {
      await compoundApi.updateCompound(compound.id, {
        ...form,
        total_quantity: Number(form.total_quantity),
        days_supply: Number(form.days_supply),
        refills_authorized: Number(form.refills_authorized),
        prescriber_id: form.prescriber_id ? Number(form.prescriber_id) : undefined,
        price_code: form.price_code || undefined,
        ingredients: ingredients.map((ing, idx) => ({ ...ing, sequence: idx })),
      });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-3xl rounded-lg bg-gray-800 p-6 shadow-xl max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("compounds.editFormula")}: {compound.name}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-10">{t("compounds.fieldName")}</label>
              <input id="compounddashboard-field-10"
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-11">{t("compounds.fieldTotalQty")}</label>
              <input id="compounddashboard-field-11"
                type="number"
                step="0.01"
                min="0.01"
                value={form.total_quantity}
                onChange={(e) => setForm({ ...form, total_quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-12">{t("compounds.fieldQtyUnit")}</label>
              <select id="compounddashboard-field-12"
                value={form.total_quantity_unit}
                onChange={(e) => setForm({ ...form, total_quantity_unit: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              >
                <option value="g">{t("compounds.unitG")}</option>
                <option value="ml">{t("compounds.unitMl")}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-13">{t("compounds.fieldSig")}</label>
              <input id="compounddashboard-field-13"
                type="text"
                value={form.sig_code}
                onChange={(e) => setForm({ ...form, sig_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-14">{t("compounds.fieldDaysSupply")}</label>
              <input id="compounddashboard-field-14"
                type="number"
                min="1"
                value={form.days_supply}
                onChange={(e) => setForm({ ...form, days_supply: Number(e.target.value) })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-15">{t("compounds.fieldRefills")}</label>
              <input id="compounddashboard-field-15"
                type="number"
                min="0"
                value={form.refills_authorized}
                onChange={(e) => setForm({ ...form, refills_authorized: Number(e.target.value) })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-16">{t("compounds.fieldPrescriber")}</label>
              <input id="compounddashboard-field-16"
                type="number"
                placeholder="ID"
                value={form.prescriber_id}
                onChange={(e) => setForm({ ...form, prescriber_id: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-17">{t("compounds.fieldPriceCode")}</label>
              <input id="compounddashboard-field-17"
                type="text"
                value={form.price_code}
                onChange={(e) => setForm({ ...form, price_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-18">{t("compounds.fieldDescription")}</label>
            <textarea id="compounddashboard-field-18"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>

          <div className="border-t border-gray-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("compounds.ingredients")}</h3>
              <button
                type="button"
                onClick={() => setIngredients([...ingredients, { product_name: "", quantity: 1, unit: "g", strength: "" }])}
                className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                + {t("compounds.addIngredient")}
              </button>
            </div>
            {ingredients.map((ing, idx) => (
              <div key={idx} className="grid grid-cols-5 gap-2 mb-2">
                <input
                  type="text"
                  placeholder={t("compounds.ingredientProduct")}
                  value={ing.product_name}
                  onChange={(e) => setIngredients(ingredients.map((i, i2) => i2 === idx ? { ...i, product_name: e.target.value } : i))}
                  required
                  className="col-span-2 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder={t("compounds.ingredientQty")}
                  value={ing.quantity}
                  onChange={(e) => setIngredients(ingredients.map((i, i2) => i2 === idx ? { ...i, quantity: Number(e.target.value) } : i))}
                  required
                  className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                <select
                  value={ing.unit}
                  onChange={(e) => setIngredients(ingredients.map((i, i2) => i2 === idx ? { ...i, unit: e.target.value } : i))}
                  className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                >
                  <option value="g">{t("compounds.unitG")}</option>
                  <option value="ml">{t("compounds.unitMl")}</option>
                </select>
                <input
                  type="text"
                  placeholder={t("compounds.ingredientStrength")}
                  value={ing.strength ?? ""}
                  onChange={(e) => setIngredients(ingredients.map((i, i2) => i2 === idx ? { ...i, strength: e.target.value } : i))}
                  className="rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
                />
                {ingredients.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setIngredients(ingredients.filter((_, i) => i !== idx))}
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
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-70">
              {saving ? "Saving..." : t("compounds.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── DispenseCompoundModal ────────────────────────────────────────────────────

interface DispenseCompoundModalProps {
  compound: CompoundRead | null;
  onClose: () => void;
}

function DispenseCompoundModal({ compound, onClose }: DispenseCompoundModalProps) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    patient_id: "",
    quantity: 1,
    fill_date: new Date().toISOString().slice(0, 10),
    insurance_copay: "0",
    insurance_amount: "0",
    insurance_plan_id: "",
    price_code: "",
  });
  const { setSelectedCompound } = useCompoundStore();

  if (!compound) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.patient_id) { setError(t("compounds.patientRequired")); return; }

    setSaving(true);
    setError(null);
    try {
      const clientTxId = crypto.randomUUID();
      await compoundApi.dispenseCompound({
        compound_id: compound.id,
        patient_id: Number(form.patient_id),
        quantity: Number(form.quantity),
        fill_date: form.fill_date,
        insurance_copay: Number(form.insurance_copay),
        insurance_amount: Number(form.insurance_amount),
        insurance_plan_id: form.insurance_plan_id ? Number(form.insurance_plan_id) : undefined,
        price_code: form.price_code || undefined,
        client_tx_id: clientTxId,
      });
      onClose();
      setSelectedCompound(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispense failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("compounds.dispense")}: {compound.name}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-19">{t("compounds.fieldPatient")}</label>
            <input id="compounddashboard-field-19"
              type="number"
              placeholder={t("compounds.patientIdPlaceholder")}
              value={form.patient_id}
              onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
              required
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-20">{t("compounds.fieldQuantity")}</label>
              <input id="compounddashboard-field-20"
                type="number"
                step="0.01"
                min="0.01"
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-21">{t("compounds.fieldFillDate")}</label>
              <input id="compounddashboard-field-21"
                type="date"
                value={form.fill_date}
                onChange={(e) => setForm({ ...form, fill_date: e.target.value })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-22">{t("compounds.fieldCopay")}</label>
              <input id="compounddashboard-field-22"
                type="number"
                step="0.01"
                min="0"
                value={form.insurance_copay}
                onChange={(e) => setForm({ ...form, insurance_copay: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-23">{t("compounds.fieldInsuranceAmount")}</label>
              <input id="compounddashboard-field-23"
                type="number"
                step="0.01"
                min="0"
                value={form.insurance_amount}
                onChange={(e) => setForm({ ...form, insurance_amount: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-24">{t("compounds.fieldPriceCode")}</label>
            <input id="compounddashboard-field-24"
              type="text"
              value={form.price_code}
              onChange={(e) => setForm({ ...form, price_code: e.target.value })}
              className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
            />
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <button type="button" onClick={onClose} disabled={saving} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-md hover:bg-purple-700 disabled:opacity-70">
              {saving ? "Dispensing..." : t("compounds.dispense")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── CompoundPriceModal ─────────────────────────────────────────────────────

interface CompoundPriceModalProps {
  compound: CompoundRead | null;
  onClose: () => void;
}

function CompoundPriceModal({ compound, onClose }: CompoundPriceModalProps) {
  const { t } = useI18n();
  const [calculating, setCalculating] = useState(false);
  const [result, setResult] = useState<CompoundPriceCalculationResult | null>(null);
  const [form, setForm] = useState({ quantity: 1, price_code: "" });

  if (!compound) return null;

  const handleCalculate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCalculating(true);
    try {
      const priceResult = await compoundApi.calculateCompoundPrice({ compound_id: compound.id, quantity: Number(form.quantity), price_code: form.price_code || undefined });
      setResult(priceResult);
    } catch (err) {
      console.error("Price calculation failed:", err);
    } finally {
      setCalculating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("compounds.priceCalculation")}: {compound.name}</h2>
        <form onSubmit={handleCalculate} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-25">{t("compounds.fieldQuantity")}</label>
              <input id="compounddashboard-field-25"
                type="number"
                step="0.01"
                min="0.01"
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1" htmlFor="compounddashboard-field-26">{t("compounds.fieldPriceCode")}</label>
              <input id="compounddashboard-field-26"
                type="text"
                value={form.price_code}
                onChange={(e) => setForm({ ...form, price_code: e.target.value })}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          </div>
          <button type="submit" disabled={calculating} className="w-full px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700 disabled:opacity-70">
            {calculating ? "Calculating..." : t("compounds.calculate")}
          </button>
        </form>

        {result && (
          <div className="mt-6 p-4 bg-gray-700/50 rounded-lg space-y-2">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("compounds.priceBreakdown")}</h3>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between text-gray-700 dark:text-gray-300">
                <span>{t("compounds.ingredientCost")}</span>
                <span>{formatMoney(parseMoney(result.ingredient_cost))}</span>
              </div>
              <div className="flex justify-between text-gray-700 dark:text-gray-300">
                <span>{t("compounds.dispensingFee")}</span>
                <span>{formatMoney(parseMoney(result.dispensing_fee))}</span>
              </div>
              <div className="flex justify-between text-gray-700 dark:text-gray-300">
                <span>{t("compounds.markup")}</span>
                <span>{formatMoney(parseMoney(result.markup))}</span>
              </div>
              <div className="flex justify-between font-medium text-gray-900 dark:text-white border-t border-gray-600 pt-2">
                <span>{t("compounds.totalPrice")}</span>
                <span>{formatMoney(parseMoney(result.total_price))}</span>
              </div>
              <div className="flex justify-between text-gray-600 dark:text-gray-400">
                <span>{t("compounds.perUnitPrice")}</span>
                <span>{formatMoney(parseMoney(result.per_unit_price))}</span>
              </div>
            </div>
            {result.ingredient_breakdown.length > 0 && (
              <details className="mt-4">
                <summary className="text-xs text-gray-600 dark:text-gray-400 cursor-pointer">{t("compounds.ingredientBreakdown")}</summary>
                <ul className="mt-2 space-y-1 text-xs text-gray-700 dark:text-gray-300">
                  {result.ingredient_breakdown.map((ing, i) => (
                    <li key={i}>
                      {ing.product_name}: {ing.quantity} × {formatMoney(parseMoney(ing.unit_price))} = {formatMoney(parseMoney(ing.total_cost))}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">{t("common.close")}</button>
        </div>
      </div>
    </div>
  );
}

// ── DeleteConfirmModal ─────────────────────────────────────────────────────

interface DeleteConfirmModalProps {
  item: CompoundRead;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  type: "compound";
}

function DeleteConfirmModal({ item, onClose, onConfirm }: DeleteConfirmModalProps) {
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
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2">{t("compounds.deleteTitle")}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          <span className="font-medium">{item.name}</span> {t("compounds.deleteConfirm")}
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
            {submitting ? "Deleting..." : t("compounds.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}