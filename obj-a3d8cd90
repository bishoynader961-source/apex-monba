"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Plus, Edit2, Trash2, Save, X, Package } from "lucide-react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useRouter } from "next/navigation";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import { RouteGuard } from "@/components/RouteGuard";
import {
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  type ProductTemplate,
} from "@/lib/api/templates";

const INPUT_STYLE =
  "w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm";

export default function TemplatesPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canWrite = useCan("inventory.write");

  const [templates, setTemplates] = useState<ProductTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: "",
    price: "",
    vendor_name: "",
    category: "",
    dea_schedule: "OTC",
    reorder_threshold: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTemplates(await listTemplates());
    } catch {
      setError("Failed to load templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated()) load();
  }, [isAuthenticated, load]);

  const canRead = useCan("templates.read");

  const resetForm = () =>
    setForm({ name: "", price: "", vendor_name: "", category: "", dea_schedule: "OTC", reorder_threshold: "" });

  const handleEdit = (t: ProductTemplate) => {
    setEditingId(t.id);
    setForm({
      name: t.name,
      price: String(t.price),
      vendor_name: t.vendor_name ?? "",
      category: t.category ?? "",
      dea_schedule: t.dea_schedule ?? "OTC",
      reorder_threshold: t.reorder_threshold != null ? String(t.reorder_threshold) : "",
    });
    setShowCreate(false);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: form.name.trim(),
        price: parseFloat(form.price) || 0,
        vendor_name: form.vendor_name.trim() || undefined,
        category: form.category.trim() || undefined,
        dea_schedule: form.dea_schedule || undefined,
        reorder_threshold: form.reorder_threshold ? parseInt(form.reorder_threshold) : undefined,
      };
      if (editingId !== null) {
        await updateTemplate(editingId, payload);
      } else {
        await createTemplate(payload);
      }
      setEditingId(null);
      setShowCreate(false);
      resetForm();
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this template?")) return;
    try {
      await deleteTemplate(id);
      if (editingId === id) {
        setEditingId(null);
        resetForm();
      }
      await load();
    } catch {
      setError("Delete failed");
    }
  };

  const handleCreate = () => {
    resetForm();
    setEditingId(null);
    setShowCreate(true);
  };

  const columns = useMemo<Column<ProductTemplate>[]>(() => [
    { key: "name", header: "Name", render: (row: ProductTemplate) => row.name },
    { key: "price", header: "Price", render: (row: ProductTemplate) => `$${row.price.toFixed(2)}`, className: "text-right" },
    { key: "category", header: "Category", render: (row: ProductTemplate) => row.category || "—" },
    { key: "dea_schedule", header: "Schedule", render: (row: ProductTemplate) => row.dea_schedule || "—" },
  ], []);

  return (
    <DashboardLayout>
      <RouteGuard permission="templates.read">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Package className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Product Templates</h1>
        </div>
        {canWrite && (
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors text-sm"
          >
            <Plus className="w-4 h-4" /> New Template
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-600/15 border border-red-600/30 text-red-400 px-4 py-2.5 rounded-lg text-sm mb-4 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Template List */}
        <div className="lg:col-span-2 bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              {templates.length} template{templates.length !== 1 ? "s" : ""}
            </h2>
          </div>
          {loading ? (
            <div className="p-6 text-center text-gray-500 text-sm">Loading...</div>
          ) : templates.length === 0 ? (
            <div className="p-6 text-center text-gray-500 text-sm">
              No templates yet. Create one to enable quick-add in POS.
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={templates}
              keyExtractor={(row) => row.id}
              loading={loading}
              emptyMessage="No templates yet. Create one to enable quick-add in POS."
              onRowClick={handleEdit}
              actions={canWrite ? {
                header: "",
                render: (row) => (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(row.id); }}
                    className="text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )
              } : undefined}
              className="bg-[#1a1a2e] border border-gray-800"
            />
          )}
        </div>

        {/* Edit / Create Panel */}
        {(editingId !== null || showCreate) && (
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 h-fit">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">
              {editingId !== null ? "Edit Template" : "New Template"}
            </h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-1">Name *</label>
                <input id="page-field-1"
                  className={INPUT_STYLE}
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Aspirin 500mg"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-2">Price *</label>
                <input id="page-field-2"
                  className={INPUT_STYLE}
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.price}
                  onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-3">Vendor</label>
                <input id="page-field-3"
                  className={INPUT_STYLE}
                  value={form.vendor_name}
                  onChange={(e) => setForm((f) => ({ ...f, vendor_name: e.target.value }))}
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-4">Category</label>
                <input id="page-field-4"
                  className={INPUT_STYLE}
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                  placeholder="e.g. OTC, Supplement"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-5">DEA Schedule</label>
                  <select id="page-field-5"
                    className={INPUT_STYLE}
                    value={form.dea_schedule}
                    onChange={(e) => setForm((f) => ({ ...f, dea_schedule: e.target.value }))}
                  >
                    <option value="OTC">OTC</option>
                    <option value="Rx">Rx</option>
                    <option value="C-II">C-II</option>
                    <option value="C-III">C-III</option>
                    <option value="C-IV">C-IV</option>
                    <option value="C-V">C-V</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-6">Reorder At</label>
                  <input id="page-field-6"
                    className={INPUT_STYLE}
                    type="number"
                    min="0"
                    value={form.reorder_threshold}
                    onChange={(e) => setForm((f) => ({ ...f, reorder_threshold: e.target.value }))}
                    placeholder="Qty"
                  />
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => { setEditingId(null); setShowCreate(false); resetForm(); }}
                className="flex-1 px-3 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim()}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
              >
                {saving ? "Saving..." : <><Save className="w-3.5 h-3.5" /> Save</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}
