"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuthStore } from "@/stores/authStore";
import { useInventory } from "@/hooks/useInventory";
import type { Batch, Medicine, ReceiveBatch } from "@/types/contracts";

const SEARCH_DEBOUNCE_MS = 300;

export default function InventoryPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [searchTerm, setSearchTerm] = useState("");
  const [filters, setFilters] = useState({ vendor: "", status: "", lowStockOnly: false });
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Medicine | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    medicines,
    stockLevels,
    suppliers,
    canWrite,
    isLoading,
    error,
    search,
    applyFilters,
    refetch,
    receiveBatch,
    deleteMedicine,
  } = useInventory({
    vendor: filters.vendor || undefined,
    status: filters.status || undefined,
    lowStockOnly: filters.lowStockOnly,
  });

  // Debounced search: fires 300ms after the user stops typing.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(searchTerm), SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchTerm, search]);

  // Re-fetch when filter values change (immediate, no debounce).
  useEffect(() => {
    applyFilters({
      page: 1,
      vendor: filters.vendor || undefined,
      status: filters.status || undefined,
      lowStockOnly: filters.lowStockOnly,
    });
  }, [filters, applyFilters]);

  // Auth guard (mirrors app/dashboard/page.tsx pattern).
  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  const lowStock = useMemo(
    () => stockLevels?.filter((l) => l.is_low_stock) ?? [],
    [stockLevels],
  );

  const rows = useMemo(() => {
    if (!medicines || !stockLevels) return [];
    const byName = new Map(stockLevels.map((s) => [s.name, s]));
    return medicines.map((m) => {
      const sl = byName.get(m.name);
      return {
        ...m,
        on_hand: sl ? sl.total_on_hand : 0,
        isLow: sl ? sl.is_low_stock : false,
      };
    });
  }, [medicines, stockLevels]);

  const handleReceiveSubmit = async (payload: ReceiveBatch): Promise<Batch> => {
    const result = await receiveBatch(payload);
    void refetch();
    setModalOpen(false);
    return result;
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteMedicine(deleteTarget.id);
      void refetch();
      setDeleteTarget(null);
    } catch {
      // error surfaced by api interceptor
    }
  };

  if (!isAuthenticated()) return null;

  return (
    <main className="p-4 md:p-6 min-h-screen">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h1 className="text-xl md:text-2xl font-bold">Inventory Management</h1>
        {canWrite && (
          <button
            onClick={() => setModalOpen(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
          >
            Add / Adjust Stock
          </button>
        )}
      </header>

      {/* Low-stock warnings */}
      {lowStock.length > 0 && (
        <section className="mb-4 flex flex-wrap gap-3">
          {lowStock.map((l) => (
            <div
              key={l.medicine_id}
              className="rounded-md bg-amber-900/30 border border-amber-500/40 px-3 py-2 text-sm"
            >
              <span className="font-medium text-amber-300">{l.name}</span>
              <span className="mx-2 text-amber-400">•</span>
              <span className="text-amber-200">
                Low stock: {l.total_on_hand} on hand (threshold {l.reorder_threshold ?? "—"})
              </span>
              {l.expiring_soon_count > 0 && (
                <span className="ml-2 text-red-300">
                  (also {l.expiring_soon_count} expiring soon)
                </span>
              )}
            </div>
          ))}
        </section>
      )}

      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-3">
        <input
          type="search"
          placeholder="Search medicines, barcodes…"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          aria-label="Search medicines"
          className="flex-1 rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <select
          value={filters.vendor}
          onChange={(e) => setFilters({ ...filters, vendor: e.target.value })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">All vendors</option>
          {suppliers.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">All status</option>
          <option value="In Stock">In Stock</option>
          <option value="Expired">Expired</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={filters.lowStockOnly}
            onChange={(e) =>
              setFilters({ ...filters, lowStockOnly: e.target.checked })
            }
          />
          Low stock only
        </label>
      </div>

      {error && <p className="text-sm text-red-400 mb-3" role="alert">{error}</p>}

      {/* Responsive table */}
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="min-w-[720px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              {["Medicine", "Vendor", "Barcode", "Expiry", "On Hand", "Threshold", "Status"].map(
                (h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-left font-medium text-gray-300"
                  >
                    {h}
                  </th>
                ),
              )}
              <th className="px-3 py-2 text-right font-medium text-gray-300">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-gray-500">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading &&
              rows.map((r) => (
                <tr key={r.id} className={r.isLow ? "bg-amber-900/10" : undefined}>
                  <td className="px-3 py-2 truncate">{r.name}</td>
                  <td className="px-3 py-2 truncate">{r.vendor_name}</td>
                  <td className="px-3 py-2 truncate">{r.internal_unique_barcode}</td>
                  <td className="px-3 py-2">{r.expiry_date || "—"}</td>
                  <td className="px-3 py-2 font-medium">{r.on_hand}</td>
                  <td className="px-3 py-2">{r.reorder_threshold ?? "—"}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        r.status === "In Stock"
                          ? "text-green-400"
                          : "text-red-400"
                      }
                    >
                      {r.status}
                    </span>
                    {r.isLow && <span className="ml-2 text-amber-400">(low)</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canWrite && (
                      <button
                        onClick={() => setDeleteTarget(r)}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {medicines && medicines.length === 0 && !isLoading && (
        <p className="text-sm text-gray-400 mt-4">No medicines match your filters.</p>
      )}

      {/* Stock modal */}
      {modalOpen && (
        <StockModal
          onClose={() => setModalOpen(false)}
          onSuccess={() => {
            void refetch();
            setModalOpen(false);
          }}
          suppliers={suppliers}
          receiveBatch={handleReceiveSubmit}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <DeleteConfirm
          medicine={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </main>
  );
}

// ── Sub-components (co-located, no micro-files) ─────────────────────────────────

interface StockModalProps {
  onClose: () => void;
  onSuccess: () => void;
  suppliers: string[];
  receiveBatch: (payload: ReceiveBatch) => Promise<Batch>;
}

function StockModal({ onClose, onSuccess, suppliers, receiveBatch }: StockModalProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const [form, setForm] = useState({
    product_name: "",
    lot_number: "",
    expiry_date: "",
    quantity: 1,
    unit_cost: 0,
    supplier: suppliers[0] ?? "",
    ndc_code: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await receiveBatch({
        ...form,
        quantity: Number(form.quantity),
        unit_cost: String(form.unit_cost),
        ndc_code: form.ndc_code || undefined,
      });
      onSuccess();
    } catch (err: unknown) {
      setErr(err instanceof Error ? err.message : "Failed to receive batch");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-md rounded-lg bg-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Receive New Batch</h2>
        {err && <p className="text-sm text-red-400 mb-3">{err}</p>}
        <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300">Product</label>
            <input
              type="text"
              value={form.product_name}
              onChange={(e) => setForm({ ...form, product_name: e.target.value })}
              required
              className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300">Lot Number</label>
            <input
              type="text"
              value={form.lot_number}
              onChange={(e) => setForm({ ...form, lot_number: e.target.value })}
              required
              className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300">Expiry Date</label>
            <input
              type="date"
              value={form.expiry_date}
              onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
              required
              className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300">Quantity</label>
              <input
                type="number"
                min={1}
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
                required
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">Unit Cost</label>
              <input
                type="number"
                min={0}
                step={0.01}
                value={form.unit_cost}
                onChange={(e) => setForm({ ...form, unit_cost: Number(e.target.value) })}
                required
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300">Supplier</label>
            <select
              value={form.supplier}
              onChange={(e) => setForm({ ...form, supplier: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            >
              <option value="">— select —</option>
              {suppliers.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300">NDC Code (optional)</label>
            <input
              type="text"
              value={form.ndc_code}
              onChange={(e) => setForm({ ...form, ndc_code: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
            />
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-70"
            >
              {submitting ? "Receiving…" : "Receive"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface DeleteConfirmProps {
  medicine: Medicine;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}

function DeleteConfirm({ medicine, onClose, onConfirm }: DeleteConfirmProps) {
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
        <h2 className="text-lg font-semibold text-gray-100 mb-2">Delete Medicine?</h2>
        <p className="text-sm text-gray-400 mb-4">
          <span className="font-medium">{medicine.name}</span> will be soft-deleted (hidden from
          inventory, but historical lots remain linkable).
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-70"
          >
            {submitting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
