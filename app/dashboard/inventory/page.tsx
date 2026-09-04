"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { DashboardNav } from "@/components/DashboardNav";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useInventory } from "@/hooks/useInventory";
import { useInventoryStore } from "@/stores/inventoryStore";
import type {
  Batch,
  Medicine,
  MedicineCreate,
  MedicineUpdate,
  MovementFilters,
  MovementLogItem,
  ReceiveBatch,
} from "@/types/contracts";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import { useI18n } from "@/components/I18nProvider";

import * as inventoryApi from "@/lib/api/inventory";

const SEARCH_DEBOUNCE_MS = 300;
const TABS = ["Inventory", "Drug Information", "Movement History"] as const;
type TabName = (typeof TABS)[number];

export default function InventoryPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { t } = useI18n();
  const [searchTerm, setSearchTerm] = useState("");
  const [filters, setFilters] = useState({ vendor: "", status: "", lowStockOnly: false });
  const [modalOpen, setModalOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Medicine | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Medicine | null>(null);
  const [activeTab, setActiveTab] = useState<TabName>("Inventory");
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

  const tabLabels: Record<TabName, string> = {
    "Inventory": t("inventory.tabInventory"),
    "Drug Information": t("inventory.tabDrugInfo"),
    "Movement History": t("inventory.tabMovements"),
  };

  return (
    <main className="p-4 md:p-6 min-h-screen">
      <DashboardNav active="/dashboard/inventory" />

      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h1 className="text-xl md:text-2xl font-bold">{t("inventory.title")}</h1>
        {canWrite && (
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setCreateOpen(true)}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium"
            >
              {t("inventory.newMedicine")}
            </button>
            <button
              onClick={() => setModalOpen(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
            >
              {t("inventory.addAdjustStock")}
            </button>
          </div>
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
          placeholder={t("inventory.searchPlaceholder")}
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
          <option value="">{t("inventory.allVendors")}</option>
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
          <option value="">{t("inventory.allStatus")}</option>
          <option value="In Stock">{t("inventory.inStock")}</option>
          <option value="Expired">{t("inventory.expired")}</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={filters.lowStockOnly}
            onChange={(e) =>
              setFilters({ ...filters, lowStockOnly: e.target.checked })
            }
          />
          {t("inventory.lowStockOnly")}
        </label>
      </div>

      {error && <p className="text-sm text-red-400 mb-3" role="alert">{error}</p>}

      {/* Tab bar */}
      <div className="flex gap-2 mb-4 border-b border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              activeTab === tab
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </div>

      {activeTab === "Inventory" && (
        <>
          <div className="overflow-x-auto rounded-lg border border-gray-700">
            <table className="min-w-[720px] w-full table-fixed border-collapse text-sm">
              <thead className="bg-gray-800/60">
                <tr>
                  {[t("inventory.colMedicine"), t("inventory.colVendor"), t("inventory.colBarcode"), t("inventory.colExpiry"), t("inventory.colOnHand"), t("inventory.colThreshold"), t("inventory.colStatus")].map(
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
                {t("inventory.colActions")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-center text-gray-500">
                  {t("inventory.loading")}
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
                    {r.isLow && <span className="ml-2 text-amber-400">{t("inventory.lowBadge")}</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canWrite && (
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button
                          onClick={() => setEditTarget(r)}
                          className="text-xs text-blue-400 hover:text-blue-300"
                        >
                          {t("inventory.edit")}
                        </button>
                        <button
                          onClick={() => setDeleteTarget(r)}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          {t("inventory.delete")}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
        {medicines && medicines.length === 0 && !isLoading && (
          <p className="text-sm text-gray-400 mt-4">{t("inventory.noMatches")}</p>
        )}
        </>
      )}

      {activeTab === "Movement History" && <MovementHistoryTab />}

      {activeTab === "Drug Information" && (
        <DrugInformationTab
          medicines={medicines ?? []}
          updateMedicine={useInventoryStore.getState().updateMedicine}
          canWrite={canWrite}
        />
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

      {/* Create medicine modal */}
      {createOpen && (
        <CreateMedicineModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => {
            void refetch();
            setCreateOpen(false);
          }}
        />
      )}

      {/* Edit medicine modal */}
      {editTarget && (
        <EditMedicineModal
          medicine={editTarget}
          onClose={() => setEditTarget(null)}
          onSuccess={() => {
            void refetch();
            setEditTarget(null);
          }}
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
  const { t } = useI18n();
  const [mode, setMode] = useState<"receive" | "adjust">("receive");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Receive form
  const [recvForm, setRecvForm] = useState({
    product_name: "",
    lot_number: "",
    expiry_date: "",
    quantity: 1,
    unit_cost: 0,
    supplier: suppliers[0] ?? "",
    ndc_code: "",
  });

  // Adjustment form
  const [adjProduct, setAdjProduct] = useState("");
  const [adjQty, setAdjQty] = useState(0);
  const [adjReason, setAdjReason] = useState("");

  const handleReceive = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await receiveBatch({
        ...recvForm,
        quantity: Number(recvForm.quantity),
        unit_cost: String(recvForm.unit_cost),
        ndc_code: recvForm.ndc_code || undefined,
      });
      onSuccess();
    } catch (err: unknown) {
      setErr(err instanceof Error ? err.message : "Failed to receive batch");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAdjust = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await inventoryApi.createAdjustment({
        product_id: Number(adjProduct),
        quantity_change: adjQty,
        reason: adjReason,
      });
      onSuccess();
    } catch (err: unknown) {
      setErr(err instanceof Error ? err.message : "Failed to apply adjustment");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-md rounded-lg bg-gray-800 p-6 shadow-xl">
        {/* Mode tabs */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode("receive")}
            className={`px-3 py-1.5 text-sm font-medium rounded-md ${mode === "receive" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"}`}
          >
            {t("inventory.tabReceive")}
          </button>
          <button
            onClick={() => setMode("adjust")}
            className={`px-3 py-1.5 text-sm font-medium rounded-md ${mode === "adjust" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"}`}
          >
            {t("inventory.tabAdjust")}
          </button>
        </div>

        {err && <p className="text-sm text-red-400 mb-3">{err}</p>}

        {mode === "receive" ? (
          <form onSubmit={handleReceive} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.receiveProduct")}</label>
              <input
                type="text"
                value={recvForm.product_name}
                onChange={(e) => setRecvForm({ ...recvForm, product_name: e.target.value })}
                required
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.lotNumber")}</label>
              <input
                type="text"
                value={recvForm.lot_number}
                onChange={(e) => setRecvForm({ ...recvForm, lot_number: e.target.value })}
                required
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.expiryDate")}</label>
              <input
                type="date"
                value={recvForm.expiry_date}
                onChange={(e) => setRecvForm({ ...recvForm, expiry_date: e.target.value })}
                required
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300">{t("inventory.quantity")}</label>
                <input
                  type="number"
                  min={1}
                  value={recvForm.quantity}
                  onChange={(e) => setRecvForm({ ...recvForm, quantity: Number(e.target.value) })}
                  required
                  className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300">{t("inventory.unitCost")}</label>
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  value={recvForm.unit_cost}
                  onChange={(e) => setRecvForm({ ...recvForm, unit_cost: Number(e.target.value) })}
                  required
                  className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.supplier")}</label>
              <select
                value={recvForm.supplier}
                onChange={(e) => setRecvForm({ ...recvForm, supplier: e.target.value })}
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              >
                <option value="">{t("inventory.selectPlaceholder")}</option>
                {suppliers.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.ndcCodeOptional")}</label>
              <input
                type="text"
                value={recvForm.ndc_code}
                onChange={(e) => setRecvForm({ ...recvForm, ndc_code: e.target.value })}
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={onClose} disabled={submitting} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
              <button type="submit" disabled={submitting} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-70">
                {submitting ? t("inventory.receiving") : t("inventory.receive")}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleAdjust} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.productId")}</label>
              <input
                type="number"
                min={1}
                value={adjProduct}
                onChange={(e) => setAdjProduct(e.target.value)}
                required
                placeholder={t("inventory.enterProductId")}
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.quantityChange")}</label>
              <input
                type="number"
                value={adjQty}
                onChange={(e) => setAdjQty(Number(e.target.value))}
                required
                placeholder="+ adds stock, − removes stock"
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">Positive number adds stock, negative removes stock.</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300">{t("inventory.adjustReason")}</label>
              <input
                type="text"
                value={adjReason}
                onChange={(e) => setAdjReason(e.target.value)}
                required
                placeholder="e.g. Damaged, Expired, Cycle count correction"
                className="mt-1 block w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100"
              />
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={onClose} disabled={submitting} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
              <button type="submit" disabled={submitting} className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700 disabled:opacity-70">
                {submitting ? t("inventory.applying") : t("inventory.applyAdjustment")}
              </button>
            </div>
          </form>
        )}
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
        <h2 className="text-lg font-semibold text-gray-100 mb-2">{t("inventory.deleteTitle")}</h2>
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
            {t("common.cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-70"
          >
            {submitting ? "Deleting…" : t("inventory.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Movement History Tab (M99) ──────────────────────────────────────────────

const MOVEMENT_TYPE_BADGES: Record<string, string> = {
  RECEIVE: "bg-green-900/30 text-green-400 border-green-600/40",
  SALE: "bg-red-900/30 text-red-400 border-red-600/40",
  DISPENSE: "bg-red-900/30 text-red-400 border-red-600/40",
  ADJUSTMENT: "bg-amber-900/30 text-amber-400 border-amber-600/40",
};

function MovementHistoryTab() {
  const { t } = useI18n();
  const canRead = useCan("inventory.read");
  const [items, setItems] = useState<MovementLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<MovementFilters>({});

  const fetchMovements = async (resetPage: boolean = true) => {
    if (!canRead) return;
    setIsLoading(true);
    setError(null);
    try {
      const params: MovementFilters = { ...filters, page: resetPage ? 1 : page, limit: 50 };
      const resp = await inventoryApi.listMovements(params);
      setItems(resp.items);
      setTotal(resp.total);
      if (resetPage) setPage(1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load movements");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchMovements();
  }, [canRead]);

  const handleFilterChange = (next: Partial<MovementFilters>) => {
    setFilters((prev) => ({ ...prev, ...next }));
  };

  const handleApply = () => {
    void fetchMovements();
  };

  if (!canRead) {
    return <p className="text-sm text-gray-400">You do not have permission to view movement history.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
        <input
          type="text"
          placeholder={t("inventory.productNdc")}
          value={filters.batch_number ?? ""}
          onChange={(e) => handleFilterChange({ batch_number: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <select
          value={filters.movement_type ?? ""}
          onChange={(e) => handleFilterChange({ movement_type: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">{t("inventory.allTypes")}</option>
          <option value="RECEIVE">{t("inventory.typeReceive")}</option>
          <option value="SALE">{t("inventory.typeSale")}</option>
          <option value="DISPENSE">{t("inventory.typeDispense")}</option>
          <option value="ADJUSTMENT">{t("inventory.typeAdjustment")}</option>
        </select>
        <input
          type="date"
          value={filters.start_date ?? ""}
          onChange={(e) => handleFilterChange({ start_date: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="date"
          value={filters.end_date ?? ""}
          onChange={(e) => handleFilterChange({ end_date: e.target.value || undefined })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <button
          onClick={handleApply}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
        >
          Apply
        </button>
      </div>

      {error && <p className="text-sm text-red-400" role="alert">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="min-w-[900px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-300">{t("inventory.colDateTime")}</th>
              <th className="px-3 py-2 text-left font-medium text-gray-300">{t("inventory.colMedicine")}</th>
              <th className="px-3 py-2 text-left font-medium text-gray-300">{t("inventory.colBatchNdc")}</th>
              <th className="px-3 py-2 text-center font-medium text-gray-300">{t("inventory.colType")}</th>
              <th className="px-3 py-2 text-right font-medium text-gray-300">{t("inventory.colQtyChange")}</th>
              <th className="px-3 py-2 text-right font-medium text-gray-300">{t("inventory.colOnHandMovements")}</th>
              <th className="px-3 py-2 text-left font-medium text-gray-300">{t("inventory.colReference")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                  {t("inventory.loadingMovements")}
                </td>
              </tr>
            )}
            {!isLoading && items.map((item) => (
              <tr key={item.id}>
                <td className="px-3 py-2 truncate">{item.timestamp.slice(0, 19)}</td>
                <td className="px-3 py-2 truncate">{item.product_name || "—"}</td>
                <td className="px-3 py-2 truncate text-gray-400">
                  {item.batch_number || item.ndc_code || "—"}
                </td>
                <td className="px-3 py-2 text-center">
                  <span
                    className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${
                      MOVEMENT_TYPE_BADGES[item.movement_type] ?? "bg-gray-700 text-gray-300"
                    }`}
                  >
                    {item.movement_type}
                  </span>
                </td>
                <td
                  className={`px-3 py-2 text-right font-medium ${
                    (item.quantity_change ?? 0) >= 0
                      ? "text-green-400"
                      : "text-red-400"
                  }`}
                >
                  {item.quantity_change > 0 ? "+" : ""}{item.quantity_change}
                </td>
                <td className="px-3 py-2 text-right text-gray-300">
                  {item.remaining_stock_snapshot ?? "—"}
                </td>
                <td className="px-3 py-2 truncate text-gray-400">
                  {item.user_name ? `Txn #${item.reference_id}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-500">
        {total} movement{total !== 1 ? "s" : ""} • Page {page}
      </p>
    </div>
  );
}

// ── Drug Information Tab ──────────────────────────────────────────────────────
function DrugInformationTab({
  medicines,
  updateMedicine,
  canWrite,
}: {
  medicines: Medicine[];
  updateMedicine: (id: number, payload: MedicineUpdate) => Promise<Medicine>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Partial<Medicine>>({});
  const [saving, setSaving] = useState(false);

  const startEdit = (med: Medicine) => {
    setEditing(med.id);
    setDraft({
      ndc_code: med.ndc_code ?? "",
      form: med.form ?? "",
      strength: med.strength ?? "",
      manufacturer_name: med.manufacturer_name ?? "",
      therapeutic_class: med.therapeutic_class ?? "",
      is_generic: med.is_generic ?? 0,
      is_controlled: med.is_controlled ?? 0,
      maintenance_medication: med.maintenance_medication ?? 0,
      drug_cost: med.drug_cost ?? "",
      default_sig_code: med.default_sig_code ?? "",
      default_qty: med.default_qty ?? null,
      default_days_supply: med.default_days_supply ?? null,
      lot_number: med.lot_number ?? "",
      package_size: med.package_size ?? "",
      unit_of_measure: med.unit_of_measure ?? "",
    });
  };

  const cancelEdit = () => { setEditing(null); setDraft({}); };

  const saveEdit = async (id: number) => {
    setSaving(true);
    try {
      await updateMedicine(id, draft as MedicineUpdate);
      setEditing(null);
      setDraft({});
    } catch (e) {
      console.error("Failed to save drug info", e);
    } finally {
      setSaving(false);
    }
  };

  const field = (
    label: string,
    key: keyof MedicineUpdate,
    opts?: { type?: string; min?: number; step?: number }
  ) => (
    <div className="flex flex-col gap-0.5">
      <label className="text-[10px] text-gray-400 uppercase">{label}</label>
      {editing !== null ? (
        <input
          type={opts?.type ?? "text"}
          min={opts?.min}
          step={opts?.step}
          className="rounded bg-gray-700 px-2 py-1 text-xs text-white border border-gray-600 focus:border-blue-500 focus:outline-none"
          value={String(draft[key] ?? "")}
          onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        />
      ) : (
        <span className="text-xs text-gray-200">—</span>
      )}
    </div>
  );

  const toggleField = (label: string, key: keyof MedicineUpdate) => (
    <div className="flex flex-col gap-0.5">
      <label className="text-[10px] text-gray-400 uppercase">{label}</label>
      {editing !== null ? (
        <button
          type="button"
          className={`rounded px-2 py-1 text-xs font-medium border transition-colors ${
            Number(draft[key]) ? "bg-green-600 border-green-500 text-white" : "bg-gray-700 border-gray-600 text-gray-400"
          }`}
          onClick={() => setDraft((d) => ({ ...d, [key]: Number(d[key]) ? 0 : 1 }))}
        >
          {Number(draft[key]) ? "Yes" : "No"}
        </button>
      ) : (
        <span className={`text-xs font-medium ${Number((editing !== null ? draft : {})[key] ?? (medicines.find((m) => m.id === editing) as any)?.[key]) ? "text-green-400" : "text-gray-500"}`}>
          {Number((editing !== null ? draft : {})[key] ?? (medicines.find((m) => m.id === editing) as any)?.[key]) ? "Yes" : "No"}
        </span>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-white">{t("inventory.drugInfo")}</h2>
      <p className="text-xs text-gray-400">Drug file enrichment fields for each medicine. Click Edit to modify.</p>
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="w-full text-xs text-left">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">{t("inventory.colMedicine")}</th>
              <th className="px-3 py-2">NDC Code</th>
              <th className="px-3 py-2">{t("inventory.colForm")}</th>
              <th className="px-3 py-2">{t("inventory.colStrength")}</th>
              <th className="px-3 py-2">{t("inventory.colManufacturer")}</th>
              <th className="px-3 py-2">{t("inventory.colClass")}</th>
              <th className="px-3 py-2">{t("inventory.colGeneric")}</th>
              <th className="px-3 py-2">{t("inventory.colControlled")}</th>
              <th className="px-3 py-2">{t("inventory.colMaintenance")}</th>
              <th className="px-3 py-2">{t("inventory.colDrugCost")}</th>
              <th className="px-3 py-2">{t("inventory.colDefaultSig")}</th>
              <th className="px-3 py-2">{t("inventory.colDefaultQty")}</th>
              <th className="px-3 py-2">{t("inventory.colDaysSupply")}</th>
              <th className="px-3 py-2">{t("inventory.colLot")}</th>
              <th className="px-3 py-2">{t("inventory.colPackage")}</th>
              <th className="px-3 py-2">{t("inventory.colUnit")}</th>
              {canWrite && <th className="px-3 py-2">Action</th>}
            </tr>
          </thead>
          <tbody>
            {medicines.map((med) => (
              <tr
                key={med.id}
                className={`border-t border-gray-700 ${editing === med.id ? "bg-gray-750" : "hover:bg-gray-800"}`}
              >
                <td className="px-3 py-2 font-medium text-white max-w-[140px] truncate" title={med.name}>{med.name}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field("NDC", "ndc_code") : (med.ndc_code || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colForm"), "form") : (med.form || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colStrength"), "strength") : (med.strength || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colManufacturer"), "manufacturer_name") : (med.manufacturer_name || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colClass"), "therapeutic_class") : (med.therapeutic_class || "—")}</td>
                <td className="px-3 py-2">{editing === med.id ? toggleField(t("inventory.colGeneric"), "is_generic") : <span className={med.is_generic ? "text-green-400" : "text-gray-500"}>{med.is_generic ? "Yes" : "No"}</span>}</td>
                <td className="px-3 py-2">{editing === med.id ? toggleField(t("inventory.colControlled"), "is_controlled") : <span className={med.is_controlled ? "text-red-400" : "text-gray-500"}>{med.is_controlled ? "Yes" : "No"}</span>}</td>
                <td className="px-3 py-2">{editing === med.id ? toggleField(t("inventory.colMaintenance"), "maintenance_medication") : <span className={med.maintenance_medication ? "text-blue-400" : "text-gray-500"}>{med.maintenance_medication ? "Yes" : "No"}</span>}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colDrugCost"), "drug_cost", { type: "number", step: 0.01 }) : (med.drug_cost ? formatMoney(parseMoney(med.drug_cost)) : "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colDefaultSig"), "default_sig_code") : (med.default_sig_code || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colDefaultQty"), "default_qty", { type: "number", min: 1 }) : (med.default_qty ?? "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colDaysSupply"), "default_days_supply", { type: "number", min: 1 }) : (med.default_days_supply ?? "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colLot"), "lot_number") : (med.lot_number || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colPackage"), "package_size") : (med.package_size || "—")}</td>
                <td className="px-3 py-2 text-gray-300">{editing === med.id ? field(t("inventory.colUnit"), "unit_of_measure") : (med.unit_of_measure || "—")}</td>
                {canWrite && (
                  <td className="px-3 py-2">
                    {editing === med.id ? (
                      <div className="flex gap-1">
                        <button
                          className="rounded bg-blue-600 px-2 py-1 text-[10px] text-white hover:bg-blue-500 disabled:opacity-50"
                          onClick={() => void saveEdit(med.id)}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Save"}
                        </button>
                        <button
                          className="rounded bg-gray-600 px-2 py-1 text-[10px] text-gray-300 hover:bg-gray-500"
                          onClick={cancelEdit}
                        >
                          {t("common.cancel")}
                        </button>
                      </div>
                    ) : (
                      <button
                        className="rounded bg-gray-700 px-2 py-1 text-[10px] text-gray-300 hover:bg-gray-600"
                        onClick={() => startEdit(med)}
                      >
                        Edit
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {medicines.length === 0 && (
              <tr>
                <td colSpan={canWrite ? 17 : 16} className="px-3 py-8 text-center text-gray-500">
                  {t("inventory.noMedicines")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Create Medicine Modal ────────────────────────────────────────────────────

function CreateMedicineModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    price: "",
    ndc_code: "",
    manufacturer_barcode: "",
    internal_unique_barcode: "",
    vendor_name: "",
    category: "",
    form: "",
    strength: "",
    manufacturer_name: "",
    therapeutic_class: "",
    dea_schedule: "",
    is_generic: 0,
    is_controlled: 0,
    wholesale_price: "",
    reorder_threshold: "",
  });

  const update = (field: string, value: string | number) => setForm({ ...form, [field]: value });

  const handleSave = async () => {
    if (!form.name.trim()) { setError(t("inventory.nameRequired")); return; }
    setSaving(true);
    setError(null);
    try {
      const payload: MedicineCreate = {
        name: form.name.trim(),
        price: form.price || "0",
        ndc_code: form.ndc_code || undefined,
        manufacturer_barcode: form.manufacturer_barcode || undefined,
        internal_unique_barcode: form.internal_unique_barcode || undefined,
        vendor_name: form.vendor_name || undefined,
        category: form.category || undefined,
        form: form.form || undefined,
        strength: form.strength || undefined,
        manufacturer_name: form.manufacturer_name || undefined,
        therapeutic_class: form.therapeutic_class || undefined,
        dea_schedule: form.dea_schedule || undefined,
        is_generic: form.is_generic,
        is_controlled: form.is_controlled,
        wholesale_price: form.wholesale_price || undefined,
        reorder_threshold: form.reorder_threshold ? Number(form.reorder_threshold) : undefined,
      };
      await inventoryApi.createMedicine(payload);
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-gray-800 p-6 shadow-xl max-h-[80vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("inventory.createNewMedicine")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="grid grid-cols-2 gap-3">
          {([
            [t("inventory.fieldName"), "name", "text"],
            [t("inventory.fieldPrice"), "price", "text"],
            [t("inventory.fieldNdcCode"), "ndc_code", "text"],
            [t("inventory.fieldMfgBarcode"), "manufacturer_barcode", "text"],
            [t("inventory.fieldInternalBarcode"), "internal_unique_barcode", "text"],
            [t("inventory.fieldVendor"), "vendor_name", "text"],
            [t("inventory.fieldCategory"), "category", "text"],
            [t("inventory.fieldForm"), "form", "text"],
            [t("inventory.fieldStrength"), "strength", "text"],
            [t("inventory.fieldManufacturer"), "manufacturer_name", "text"],
            [t("inventory.fieldTherapeuticClass"), "therapeutic_class", "text"],
            [t("inventory.fieldDeaSchedule"), "dea_schedule", "text"],
            [t("inventory.fieldWholesalePrice"), "wholesale_price", "text"],
            [t("inventory.fieldReorderThreshold"), "reorder_threshold", "number"],
          ] as const).map(([label, field, type]) => (
            <div key={field}>
              <label className="block text-xs text-gray-400 mb-1">{label}</label>
              <input
                type={type}
                value={String(form[field])}
                onChange={(e) => update(field, e.target.value)}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-3 mt-4">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
          <button onClick={() => void handleSave()} disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-70">
            {saving ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Medicine Modal ──────────────────────────────────────────────────────

function EditMedicineModal({ medicine, onClose, onSuccess }: { medicine: Medicine; onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: medicine.name,
    price: medicine.price,
    ndc_code: medicine.ndc_code ?? "",
    manufacturer_barcode: medicine.manufacturer_barcode ?? "",
    internal_unique_barcode: medicine.internal_unique_barcode ?? "",
    vendor_name: medicine.vendor_name ?? "",
    category: medicine.category ?? "",
    form: medicine.form ?? "",
    strength: medicine.strength ?? "",
    manufacturer_name: medicine.manufacturer_name ?? "",
    therapeutic_class: medicine.therapeutic_class ?? "",
    dea_schedule: medicine.dea_schedule ?? "",
    is_generic: medicine.is_generic ?? 0,
    is_controlled: medicine.is_controlled ?? 0,
    wholesale_price: medicine.wholesale_price ?? "",
    reorder_threshold: medicine.reorder_threshold?.toString() ?? "",
  });

  const update = (field: string, value: string | number) => setForm({ ...form, [field]: value });

  const handleSave = async () => {
    if (!form.name.trim()) { setError(t("inventory.nameRequired")); return; }
    setSaving(true);
    setError(null);
    try {
      const payload: MedicineUpdate = {
        name: form.name.trim(),
        price: form.price,
        ndc_code: form.ndc_code || undefined,
        manufacturer_barcode: form.manufacturer_barcode || undefined,
        internal_unique_barcode: form.internal_unique_barcode || undefined,
        vendor_name: form.vendor_name || undefined,
        category: form.category || undefined,
        form: form.form || undefined,
        strength: form.strength || undefined,
        manufacturer_name: form.manufacturer_name || undefined,
        therapeutic_class: form.therapeutic_class || undefined,
        dea_schedule: form.dea_schedule || undefined,
        is_generic: form.is_generic,
        is_controlled: form.is_controlled,
        wholesale_price: form.wholesale_price || undefined,
        reorder_threshold: form.reorder_threshold ? Number(form.reorder_threshold) : undefined,
      };
      await inventoryApi.updateMedicine(medicine.id, payload);
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg rounded-lg bg-gray-800 p-6 shadow-xl max-h-[80vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Edit Medicine: {medicine.name}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="grid grid-cols-2 gap-3">
          {([
            [t("inventory.fieldName"), "name", "text"],
            [t("inventory.fieldPrice"), "price", "text"],
            [t("inventory.fieldNdcCode"), "ndc_code", "text"],
            [t("inventory.fieldMfgBarcode"), "manufacturer_barcode", "text"],
            [t("inventory.fieldInternalBarcode"), "internal_unique_barcode", "text"],
            [t("inventory.fieldVendor"), "vendor_name", "text"],
            [t("inventory.fieldCategory"), "category", "text"],
            [t("inventory.fieldForm"), "form", "text"],
            [t("inventory.fieldStrength"), "strength", "text"],
            [t("inventory.fieldManufacturer"), "manufacturer_name", "text"],
            [t("inventory.fieldTherapeuticClass"), "therapeutic_class", "text"],
            [t("inventory.fieldDeaSchedule"), "dea_schedule", "text"],
            [t("inventory.fieldWholesalePrice"), "wholesale_price", "text"],
            [t("inventory.fieldReorderThreshold"), "reorder_threshold", "number"],
          ] as const).map(([label, field, type]) => (
            <div key={field}>
              <label className="block text-xs text-gray-400 mb-1">{label}</label>
              <input
                type={type}
                value={String(form[field])}
                onChange={(e) => update(field, e.target.value)}
                className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200"
              />
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-3 mt-4">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-300">{t("common.cancel")}</button>
          <button onClick={() => void handleSave()} disabled={saving} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-70">
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}