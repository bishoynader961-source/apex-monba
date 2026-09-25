"use client";

import { useEffect, useMemo, useState } from "react";

import { useCan } from "@/stores/authStore";
import { useRxQueueStore, useRxQueueItems, useRxQueueTotal, useRxQueueLoading, useRxQueueActiveTab, useRxQueueCounts } from "@/stores/rxQueueStore";
import type { RxQueueItem, RxBulkStatusRequest } from "@/types/contracts";
import { useI18n } from "@/components/I18nProvider";

const TABS = [
  { key: "processing" as const, label: "rx.queue.tabProcessing", group: "processing" },
  { key: "rejects" as const, label: "rx.queue.tabRejects", group: "rejects" },
  { key: "ready" as const, label: "rx.queue.tabReady", group: "ready" },
] as const;

const STATUS_COLORS: Record<string, string> = {
  Pending: "bg-yellow-900/30 text-yellow-400 border-yellow-600/40",
  Billed: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  Verified: "bg-purple-900/30 text-purple-400 border-purple-600/40",
  Filled: "bg-green-900/30 text-green-400 border-green-600/40",
  "Will Call": "bg-orange-900/30 text-orange-400 border-orange-600/40",
  Rejected: "bg-red-900/30 text-red-400 border-red-600/40",
};

const VALID_TRANSITIONS: Record<string, string[]> = {
  Pending: ["Billed", "Verified", "Rejected"],
  Billed: ["Verified", "Rejected"],
  Verified: ["Filled", "Will Call", "Rejected"],
  Filled: ["Rejected"],
  "Will Call": ["Filled", "Rejected"],
  Rejected: [],
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
  rx,
  onTransition,
  canTransition,
}: {
  rx: RxQueueItem;
  onTransition: (rxId: number, status: string) => Promise<void>;
  canTransition: boolean;
}) {
  const [open, setOpen] = useState(false);
  const currentStatus = rx.status || "Pending";
  const allowed = VALID_TRANSITIONS[currentStatus] || [];

  if (!canTransition || allowed.length === 0) {
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
        <div className="absolute right-0 top-full mt-1 z-20 bg-gray-800 border border-gray-700 rounded-md shadow-lg min-w-[140px]">
          {allowed.map((status) => (
            <button
              key={status}
              onClick={() => {
                onTransition(rx.id, status);
                setOpen(false);
              }}
              className="w-full px-3 py-2 text-left text-sm text-gray-100 hover:bg-gray-700"
            >
              {status}
            </button>
          ))}
          <div className="border-t border-gray-700" />
          <button
            onClick={() => setOpen(false)}
            className="w-full px-3 py-2 text-left text-sm text-gray-400 hover:bg-gray-700"
          >
            Cancel
          </button>
        </div>
      )}
      <div
        className="fixed inset-0 z-10"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
    </div>
  );
}

export function RxQueueDashboard() {
  const { t } = useI18n();
  const canTransition = useCan("rx.queue.transition");
  const canBulk = useCan("rx.queue.bulk");
  const canRead = useCan("rx.queue.read");

  const activeTab = useRxQueueActiveTab();
  const items = useRxQueueItems(activeTab);
  const total = useRxQueueTotal(activeTab);
  const isLoading = useRxQueueLoading(activeTab);
  const counts = useRxQueueCounts();
  const { setActiveTab, fetchTab, refreshCounts, transitionStatus, bulkTransition } = useRxQueueStore();
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkStatus, setBulkStatus] = useState<string>("");

  // Load counts on mount
  useEffect(() => {
    refreshCounts();
  }, [refreshCounts]);

  // Fetch current tab on mount and tab change
  useEffect(() => {
    fetchTab(activeTab, true);
  }, [activeTab, fetchTab]);

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(items.map((r) => r.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleRowSelect = (id: number, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? [...prev, id] : prev.filter((x) => x !== id)
    );
  };

  const handleBulkTransition = async () => {
    if (!bulkStatus || selectedIds.length === 0) return;
    try {
      await bulkTransition({ rx_ids: selectedIds, status: bulkStatus as RxBulkStatusRequest["status"] });
      setSelectedIds([]);
      setBulkStatus("");
    } catch (err) {
      console.error("Bulk transition failed:", err);
    }
  };

  const totalPages = Math.ceil(total / 50) || 1;

  const tabLabels = {
    processing: t("rx.queue.tabProcessing"),
    rejects: t("rx.queue.tabRejects"),
    ready: t("rx.queue.tabReady"),
  };

  return (
    <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
      {/* Tab Bar */}
      <div className="flex border-b border-gray-800 bg-[#0d0d20]">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-6 py-3 text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === tab.key
                ? "bg-blue-600 text-white border-b-2 border-blue-400"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
            }`}
          >
            {tabLabels[tab.key]}
            <span className={`px-2 py-0.5 text-xs rounded-full ${
              activeTab === tab.key
                ? "bg-white/20 text-white"
                : "bg-gray-700 text-gray-300"
            }`}>
              {counts?.[tab.group] ?? 0}
            </span>
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="p-4 border-b border-gray-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          {selectedIds.length > 0 && canBulk && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-700 dark:text-gray-300">
                {t("rx.queue.selectedCount")} {selectedIds.length}
              </span>
              <select
                value={bulkStatus}
                onChange={(e) => setBulkStatus(e.target.value)}
                className="rounded-md border border-gray-600 bg-gray-900 px-2 py-1 text-sm text-gray-100"
              >
                <option value="">{t("rx.queue.bulkAction")}</option>
                <option value="Billed">{t("rx.queue.statusBilled")}</option>
                <option value="Verified">{t("rx.queue.statusVerified")}</option>
                <option value="Filled">{t("rx.queue.statusFilled")}</option>
                <option value="Will Call">{t("rx.queue.statusWillCall")}</option>
                <option value="Rejected">{t("rx.queue.statusRejected")}</option>
              </select>
              <button
                onClick={handleBulkTransition}
                disabled={!bulkStatus}
                className="px-3 py-1.5 text-xs font-medium text-white bg-purple-600 rounded-md hover:bg-purple-700 disabled:opacity-50"
              >
                {t("rx.queue.apply")}
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600 dark:text-gray-400">
            Page {page} of {totalPages} • {total} {t("rx.queue.items")}
          </span>
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

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-[900px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300 w-10">
                <input
                  type="checkbox"
                  checked={selectedIds.length === items.length && items.length > 0}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                  className="w-4 h-4 accent-blue-600"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colRxNumber")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colPatient")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colDrug")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colQty")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colPrescriber")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colStatus")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colFillDate")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colRefills")}</th>
              <th className="px-4 py-3 text-left font-medium text-gray-700 dark:text-gray-300">{t("rx.queue.colActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-gray-500">
                  {t("rx.queue.loading")}
                </td>
              </tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-gray-500">
                  {t("rx.queue.empty")}
                </td>
              </tr>
            )}
            {!isLoading && items.map((rx) => (
              <tr key={rx.id} className="hover:bg-gray-800/50">
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(rx.id)}
                    onChange={(e) => handleRowSelect(rx.id, e.target.checked)}
                    className="w-4 h-4 accent-blue-600"
                  />
                </td>
                <td className="px-4 py-3 font-mono text-blue-400">{rx.rx_number ?? "—"}</td>
                <td className="px-4 py-3 truncate max-w-[180px]">{rx.patient_name}</td>
                <td className="px-4 py-3 truncate max-w-[200px]">{rx.product_name}</td>
                <td className="px-4 py-3 text-center">{rx.quantity}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400 truncate max-w-[140px]">{rx.prescriber_name ?? "—"}</td>
                <td className="px-4 py-3 text-center">
                  <StatusBadge status={rx.status || "Pending"} />
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{rx.fill_date ? rx.fill_date.slice(0, 10) : "—"}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {rx.refill_count}/{rx.refills_authorized}
                </td>
                <td className="px-4 py-3">
                  <ActionMenu
                    rx={rx}
                    onTransition={transitionStatus}
                    canTransition={canTransition}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination info */}
      <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500 text-right">
        Showing {((page - 1) * 50) + 1}–{Math.min(page * 50, total)} of {total}
      </div>
    </div>
  );
}