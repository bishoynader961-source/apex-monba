"use client";

import { useState, useEffect, useCallback } from "react";
import { usePersistedFilters } from "@/hooks/usePersistedFilters";
import { useRouter } from "next/navigation";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { useToast } from "@/hooks/useToast";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";

const BASE = "/api/v1/receipts";

interface ReceiptListItem {
  id: number;
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id: number | null;
  created_at: string;
  expires_at: string | null;
}

interface ReceiptDetail {
  id: number;
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id: number | null;
  created_at: string;
  expires_at: string | null;
  items: {
    id: number;
    product_name: string;
    quantity: number;
    price_at_time: string;
    internal_barcode: string;
    vendor: string;
    expiry_date: string;
  }[];
}

const TYPE_LABELS: Record<string, string> = {
  pos_sale: "POS Sale",
  prescription: "Prescription",
  adjustment: "Adjustment",
};

const TYPE_BADGES: Record<string, string> = {
  pos_sale: "bg-green-900/30 text-green-400 border-green-600/40",
  prescription: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  adjustment: "bg-amber-900/30 text-amber-400 border-amber-600/40",
};

function ReceiptDetailModal({
  receipt,
  onClose,
  onPrint,
  onDelete,
  canWrite,
}: {
  receipt: ReceiptDetail;
  onClose: () => void;
  onPrint: () => void;
  onDelete: () => void;
  canWrite: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-lg bg-gray-800 p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4 border-b border-gray-700 pb-4">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Receipt #{receipt.receipt_number}</h2>
          <button onClick={onClose} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1" aria-label="Close">
            <span>×</span>
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto space-y-4">
          <div className="grid grid-cols-4 gap-4 text-sm">
            <div><span className="text-gray-600 dark:text-gray-400">Receipt #</span><br /><span className="font-medium text-gray-900 dark:text-white">{receipt.receipt_number}</span></div>
            <div><span className="text-gray-600 dark:text-gray-400">Date</span><br /><span className="font-medium text-gray-900 dark:text-white">{receipt.created_at.slice(0, 19).replace("T", " ")}</span></div>
            <div><span className="text-gray-600 dark:text-gray-400">Type</span><br /><span className="font-medium text-gray-900 dark:text-white">{receipt.type}</span></div>
            <div><span className="text-gray-600 dark:text-gray-400">Total</span><br /><span className="font-medium text-gray-900 dark:text-white">{receipt.total_amount}</span></div>
            <div><span className="text-gray-600 dark:text-gray-400">Payment</span><br /><span className="font-medium text-gray-900 dark:text-white">{receipt.payment_method}</span></div>
            <div>
              <span className="text-gray-600 dark:text-gray-400">Status</span>
              <br />
              <span className={receipt.expires_at && new Date(receipt.expires_at) < new Date() ? "text-red-400" : "text-green-400"}>
                {receipt.expires_at && new Date(receipt.expires_at) < new Date() ? "Expired" : "Active"}
              </span>
            </div>
          </div>

          <div className="border-t border-gray-700 pt-4">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Items</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 text-left text-gray-600 dark:text-gray-400">
                    <th className="px-3 py-2">Product</th>
                    <th className="px-3 py-2 text-center">Qty</th>
                    <th className="px-3 py-2 text-right">Price</th>
                    <th className="px-3 py-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {receipt.items.map((item) => (
                    <tr key={item.id} className="border-b border-gray-700/50">
                      <td className="px-3 py-2 truncate">{item.product_name}</td>
                      <td className="px-3 py-2 text-center">{item.quantity}</td>
                      <td className="px-3 py-2 text-right">{item.price_at_time}</td>
                      <td className="px-3 py-2 text-right font-medium">{item.price_at_time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-right mt-3 font-bold text-lg">
              Total: {receipt.total_amount}
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-700">
            <button onClick={onPrint} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700">
              Reprint
            </button>
            {canWrite && (
              <button onClick={onDelete} className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700">
                Delete Receipt
              </button>
            )}
            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ReceiptHistoryPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("pos.read");
  const canWrite = useCan("pos.write");
  const { t } = useI18n();
  const { toast } = useToast();

  const [receipts, setReceipts] = useState<ReceiptListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  // Filter memory: returning from the receipt detail modal view restores the
  // user's active filters (type/date-range/search) instead of resetting them.
  const [filters, setFilters] = usePersistedFilters<{
    type: string;
    start_date: string;
    end_date: string;
    search: string;
  }>({
    routeKey: "/dashboard/receipt-history",
    initial: { type: "", start_date: "", end_date: "", search: "" },
  });

  const [selectedReceipt, setSelectedReceipt] = useState<ReceiptDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role_id === 1;

  const handleReprint = (receipt: ReceiptDetail) => {
    const win = window.open("", "_blank", "width=400,height=600");
    if (!win) {
      toast({ title: "Error", message: "Popup blocked — allow popups to reprint.", variant: "destructive" });
      return;
    }
    const rows = receipt.items
      .map((it) => `<tr><td>${it.product_name}</td><td style="text-align:center">${it.quantity}</td><td style="text-align:right">${it.price_at_time}</td></tr>`)
      .join("");
    win.document.write(
      `<html><head><title>Receipt ${receipt.receipt_number}</title></head>` +
      `<body style="font-family:monospace;max-width:320px;margin:0 auto;padding:16px">` +
      `<h3 style="text-align:center">Receipt #${receipt.receipt_number}</h3>` +
      `<p>${receipt.created_at.slice(0, 19).replace("T", " ")}<br/>${receipt.type} · ${receipt.payment_method}</p>` +
      `<table style="width:100%;font-size:12px"><thead><tr><th style="text-align:left">Item</th><th>Qty</th><th style="text-align:right">Price</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<h3 style="text-align:right">Total: ${receipt.total_amount}</h3>` +
      `<script>window.onload = function () { window.print(); };</script>` +
      `</body></html>`
    );
    win.document.close();
    toast({ title: "Success", message: "Reprint sent to printer" });
  };
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [retentionLoading, setRetentionLoading] = useState(false);
  const [showRetentionModal, setShowRetentionModal] = useState(false);
  const [retentionInput, setRetentionInput] = useState<string>("");

  const fetchReceipts = useCallback(async (resetPage = true) => {
    if (!canRead) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("page", String(resetPage ? 1 : page));
      params.set("page_size", String(pageSize));
      if (filters.type) params.set("type", filters.type);
      if (filters.start_date) params.set("start_date", filters.start_date);
      if (filters.end_date) params.set("end_date", filters.end_date);
      if (filters.search) params.set("search", filters.search);
      const resp = await fetch(`${BASE}?${params.toString()}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (!resp.ok) throw new Error("Failed to fetch receipts");
      const data = await resp.json();
      const items = Array.isArray(data) ? data : data.items ?? [];
      setReceipts(items);
      setTotal(Array.isArray(data) ? data.length : data.total ?? items.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load receipts");
    } finally {
      setLoading(false);
    }
  }, [canRead, page, pageSize, filters]);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (canRead) fetchReceipts();
  }, [canRead, fetchReceipts]);

  const fetchRetention = async () => {
    try {
      const resp = await fetch(`${BASE}/settings`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setRetentionDays(data.retention_days ?? 365);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (canRead) fetchRetention();
  }, [canRead]);

  const handleApplyFilters = () => {
    setPage(1);
    fetchReceipts(true);
  };

  const handleRetentionChange = async () => {
    if (!retentionInput.trim()) return;
    const days = parseInt(retentionInput);
    if (isNaN(days) || days < 1) return;
    setRetentionLoading(true);
    try {
      const resp = await fetch(`${BASE}/settings`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({ retention_days: days }),
      });
      if (!resp.ok) throw new Error("Failed to update retention");
      setRetentionDays(days);
      setShowRetentionModal(false);
      setRetentionInput("");
      toast({ title: "Success", message: "Retention period updated", variant: "success" });
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to update", variant: "destructive" });
    } finally {
      setRetentionLoading(false);
    }
  };

  const handleDeleteExpired = async () => {
    if (!confirm("Delete all expired receipts? This cannot be undone.")) return;
    try {
      const resp = await fetch(`${BASE}/expired`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (!resp.ok) throw new Error("Failed to delete");
      const data = await resp.json();
      toast({ title: "Success", message: `Deleted ${data.deleted} expired receipts`, variant: "success" });
      fetchReceipts();
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to delete", variant: "destructive" });
    }
  };

  const viewReceipt = async (id: number) => {
    setDetailLoading(true);
    try {
      const resp = await fetch(`${BASE}/${id}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (!resp.ok) throw new Error("Failed to load receipt");
      const data = await resp.json();
      setSelectedReceipt(data);
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to load", variant: "destructive" });
    } finally {
      setDetailLoading(false);
    }
  };

  const deleteReceipt = async (id: number) => {
    if (!confirm("Delete this receipt? This cannot be undone.")) return;
    try {
      const resp = await fetch(`${BASE}/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (!resp.ok) throw new Error("Failed to delete");
      toast({ title: "Success", message: "Receipt deleted", variant: "success" });
      fetchReceipts();
      if (selectedReceipt?.id === id) setSelectedReceipt(null);
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to delete", variant: "destructive" });
    }
  };

  if (!isAuthenticated()) return null;

  return (
    <DashboardLayout>
      <RouteGuard permission="pos.read">
      <div className="p-4 md:p-6 min-h-screen">
        <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold">Receipt History</h1>
            {isAdmin && retentionDays !== null && (
              <p className="text-xs text-gray-500 mt-1">
                Retention: {retentionDays} days
                <button onClick={() => { setRetentionInput(String(retentionDays)); setShowRetentionModal(true); }} className="ml-2 text-blue-400 hover:text-blue-300 underline">
                  Change
                </button>
              </p>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {canWrite && (
              <button
                onClick={handleDeleteExpired}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium"
              >
                Clear Expired
              </button>
            )}
          </div>
        </header>

        {error && <p className="text-sm text-red-400 mb-3" role="alert">{error}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 mb-4">
          <input
            type="text"
            placeholder="Search receipt #"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <select
            value={filters.type}
            onChange={(e) => setFilters({ ...filters, type: e.target.value })}
            className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
          >
            <option value="">All Types</option>
            <option value="pos_sale">POS Sale</option>
            <option value="prescription">Prescription</option>
            <option value="adjustment">Adjustment</option>
          </select>
          <input
            type="date"
            value={filters.start_date}
            onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
            className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
          />
          <input
            type="date"
            value={filters.end_date}
            onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
            className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
          />
          <button
            onClick={handleApplyFilters}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
          >
            Apply
          </button>
        </div>

        {error && <p className="text-sm text-red-400 mb-3" role="alert">{error}</p>}

        {loading ? (
          <p className="text-gray-600 dark:text-gray-400 text-center py-8">Loading receipts...</p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-gray-700">
              <table className="min-w-full w-full table-fixed border-collapse text-sm">
                <thead className="bg-gray-800/60">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Receipt #</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Date</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-700 dark:text-gray-300">Type</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300">Total</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Payment</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Processed By</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300">Status</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {loading && (
                    <tr>
                      <td colSpan={8} className="px-3 py-4 text-center text-gray-500">Loading receipts...</td>
                    </tr>
                  )}
                  {!loading && receipts.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-3 py-4 text-center text-gray-500">No receipts found</td>
                    </tr>
                  )}
                  {receipts.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-gray-700/50 hover:bg-white/5 cursor-pointer"
                      onClick={() => viewReceipt(r.id)}
                    >
                      <td className="px-3 py-2 font-mono text-sm text-gray-800 dark:text-gray-200">{r.receipt_number}</td>
                      <td className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">{r.created_at.slice(0, 19).replace("T", " ")}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${TYPE_BADGES[r.type] ?? "bg-gray-700 text-gray-300"}`}>
                          {r.type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-800 dark:text-gray-200">{r.total_amount}</td>
                      <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{r.payment_method}</td>
                      <td className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">{r.user_id !== null ? `#${r.user_id}` : "—"}</td>
                      <td className="px-3 py-2">
                        {r.expires_at && new Date(r.expires_at) < new Date() ? (
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-600/40">Expired</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-600/40">Active</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={(e) => { e.stopPropagation(); viewReceipt(r.id); }}
                          className="text-xs text-blue-400 hover:text-blue-300 mr-2"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-gray-500">Total: {total} receipts</p>
              <div className="flex gap-2">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1 || loading} className="px-3 py-1 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded disabled:opacity-50">Prev</button>
                <span className="px-3 py-1 text-sm text-gray-300">Page {page}</span>
                <button onClick={() => setPage(p => p + 1)} disabled={loading} className="px-3 py-1 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded disabled:opacity-50">Next</button>
              </div>
            </div>
          </>
        )}

        {selectedReceipt && (
          <ReceiptDetailModal
            receipt={selectedReceipt}
            onClose={() => setSelectedReceipt(null)}
            onPrint={() => handleReprint(selectedReceipt)}
            onDelete={() => { deleteReceipt(selectedReceipt.id); setSelectedReceipt(null); }}
            canWrite={canWrite}
          />
        )}

        {showRetentionModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={() => setShowRetentionModal(false)}>
            <div className="w-full max-w-sm rounded-lg bg-gray-800 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-base font-semibold text-gray-100 mb-3">Retention Period (days)</h2>
              <input
                type="number"
                min={1}
                value={retentionInput}
                onChange={(e) => setRetentionInput(e.target.value)}
                placeholder={retentionDays !== null ? String(retentionDays) : "365"}
                className="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <div className="flex justify-end gap-2 mt-4">
                <button onClick={() => setShowRetentionModal(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">
                  Cancel
                </button>
                <button
                  onClick={handleRetentionChange}
                  disabled={retentionLoading}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50"
                >
                  {retentionLoading ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}