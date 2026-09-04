"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useI18n } from "@/components/I18nProvider";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useAnalytics } from "@/hooks/useAnalytics";
import { downloadCsv } from "@/lib/csv";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { DemandAnalyticsItem } from "@/types/contracts";

const VELOCITY_BADGES: Record<string, string> = {
  FAST_MOVING: "bg-green-900/30 text-green-400 border-green-600/40",
  MODERATE_MOVING: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  SLOW_MOVING: "bg-amber-900/30 text-amber-400 border-amber-600/40",
  NON_MOVING: "bg-gray-900/30 text-gray-500 border-gray-600/40",
};

const COLUMNS: { key: keyof DemandAnalyticsItem; labelKey: string }[] = [
  { key: "product_name", labelKey: "analytics.colProduct" },
  { key: "ndc_code", labelKey: "analytics.colNdc" },
  { key: "total_quantity_demanded", labelKey: "analytics.colQtyDemanded" },
  { key: "total_revenue", labelKey: "analytics.colRevenue" },
  { key: "avg_daily_consumption", labelKey: "analytics.colAvgDaily" },
  { key: "velocity_category", labelKey: "analytics.colVelocity" },
  { key: "reorder_suggestion", labelKey: "analytics.colReorder" },
];

export default function DemandAnalyticsPage() {
  const router = useRouter();
  const { t } = useI18n();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("analytics.read");
  const { summary, isLoading, error, filters, setFilters, fetch } = useAnalytics();

  const [sortKey, setSortKey] = useState<keyof DemandAnalyticsItem>("total_quantity_demanded");
  const [sortDesc, setSortDesc] = useState(true);
  const [startDate, setStartDate] = useState(filters.start_date ?? "");
  const [endDate, setEndDate] = useState(filters.end_date ?? "");
  const [category, setCategory] = useState(filters.category ?? "");

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (canRead) void fetch();
  }, [canRead, fetch]);

  const applyFilters = () => {
    setFilters({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      category: category || undefined,
    });
    void fetch();
  };

  const resetFilters = () => {
    setStartDate("");
    setEndDate("");
    setCategory("");
    setFilters({ start_date: undefined, end_date: undefined, category: undefined });
    void fetch();
  };

  const sortedItems = useMemo(() => {
    if (!summary) return [];
    const dir = sortDesc ? -1 : 1;
    return [...summary.items].sort((a, b) => {
      if (sortKey === "total_revenue") {
        const an = Number(parseMoney(a.total_revenue));
        const bn = Number(parseMoney(b.total_revenue));
        return (an - bn) * dir;
      }
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      if (typeof av === "string" && typeof bv === "string") return av.localeCompare(bv) * dir;
      return 0;
    });
  }, [summary, sortKey, sortDesc]);

  const handleSort = (key: keyof DemandAnalyticsItem) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  const handleExport = () => {
    if (!summary) return;
    const headers = [
      t("analytics.csvProduct"),
      t("analytics.csvNdc"),
      t("analytics.csvQtyDemanded"),
      t("analytics.csvTotalRevenue"),
      t("analytics.csvAvgDaily"),
      t("analytics.csvVelocity"),
      t("analytics.csvReorder"),
    ];
    const rows = summary.items.map((it) => ({
      [t("analytics.csvProduct")]: it.product_name,
      [t("analytics.csvNdc")]: it.ndc_code || "",
      [t("analytics.csvQtyDemanded")]: it.total_quantity_demanded,
      [t("analytics.csvTotalRevenue")]: formatMoney(parseMoney(it.total_revenue)),
      [t("analytics.csvAvgDaily")]: it.avg_daily_consumption.toFixed(2),
      [t("analytics.csvVelocity")]: it.velocity_category,
      [t("analytics.csvReorder")]: it.reorder_suggestion,
    }));
    downloadCsv("demand-analytics.csv", headers, rows);
  };

  const totalQty =
    summary?.items.reduce((s, it) => s + it.total_quantity_demanded, 0) ?? 0;
  const totalRevenue =
    summary?.items.reduce((s, it) => s + parseMoney(it.total_revenue), 0n) ?? 0n;
  const topProduct = summary?.items.reduce(
    (top, it) => (it.total_quantity_demanded > (top?.total_quantity_demanded ?? 0) ? it : top),
  );
  const slowOrNon =
    summary?.items.filter(
      (it) => it.velocity_category === "SLOW_MOVING" || it.velocity_category === "NON_MOVING",
    ).length ?? 0;

  if (!isAuthenticated()) return null;
  if (!canRead) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-gray-400 text-center">
            <div className="text-4xl mb-4">🔒</div>
            <p className="text-lg font-medium text-gray-200 mb-1">{t("analytics.noPermission")}</p>
            <p className="text-sm text-gray-500">You do not have permission to view demand analytics.</p>
          </div>
      </div>
    </DashboardLayout>
  );
}

  return (
    <DashboardLayout>

      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <h1 className="text-xl md:text-2xl font-bold text-gray-100">{t("analytics.title")}</h1>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            disabled={!summary || summary.items.length === 0}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
          >
            {t("analytics.exportCsv")}
          </button>
        </div>
      </header>

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 mb-4">
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          aria-label="Start date"
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          aria-label="End date"
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="text"
          placeholder={t("analytics.categoryPlaceholder")}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          aria-label="Category"
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <button
          onClick={applyFilters}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
        >
          {t("common.apply")}
        </button>
        <button
          onClick={resetFilters}
          className="px-4 py-2 border border-gray-600 text-gray-300 hover:bg-gray-700 rounded-md text-sm font-medium"
        >
          {t("analytics.reset")}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-400 mb-3" role="alert">
          {error}
        </p>
      )}

      {/* KPI Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{totalQty}</div>
            <p className="text-xs text-gray-400">{t("analytics.totalDemanded")}</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{formatMoney(totalRevenue)}</div>
            <p className="text-xs text-gray-400">{t("analytics.totalRevenue")}</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-purple-400 truncate">
              {topProduct?.product_name ?? "—"}
            </div>
            <p className="text-xs text-gray-400">{t("analytics.topProduct")}</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-amber-400">{slowOrNon}</div>
            <p className="text-xs text-gray-400">{t("analytics.slowNonMoving")}</p>
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-gray-400">{t("analytics.loading")}</p>}

      {/* Velocity Table */}
      {summary && !isLoading && (
        <div className="overflow-x-auto rounded-lg border border-gray-700">
          <table className="min-w-[900px] w-full table-fixed border-collapse text-sm">
            <thead className="bg-gray-800/60">
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className="px-3 py-2 text-left font-medium text-gray-300 cursor-pointer select-none hover:text-white"
                  >
                    {t(col.labelKey)}
                    {sortKey === col.key ? (sortDesc ? " ▼" : " ▲") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {sortedItems.map((it) => (
                <tr key={it.product_id}>
                  <td className="px-3 py-2 truncate">{it.product_name}</td>
                  <td className="px-3 py-2 truncate text-gray-400">{it.ndc_code || "—"}</td>
                  <td className="px-3 py-2 text-right font-medium">{it.total_quantity_demanded}</td>
                  <td className="px-3 py-2 text-right text-gray-300">
                    {formatMoney(parseMoney(it.total_revenue))}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-300">
                    {it.avg_daily_consumption.toFixed(2)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${
                        VELOCITY_BADGES[it.velocity_category] ?? "bg-gray-700 text-gray-300"
                      }`}
                    >
                      {it.velocity_category}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-gray-300">{it.reorder_suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DashboardLayout>
  );
}
