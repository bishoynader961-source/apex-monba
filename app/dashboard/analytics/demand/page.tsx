"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuthStore, useCan } from "@/stores/authStore";
import * as inventoryApi from "@/lib/api/inventory";
import { downloadCsv } from "@/lib/csv";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { DemandAnalyticsItem, DemandAnalyticsSummary } from "@/types/contracts";

const VELOCITY_BADGES: Record<string, string> = {
  FAST_MOVING: "bg-green-900/30 text-green-400 border-green-600/40",
  MODERATE_MOVING: "bg-blue-900/30 text-blue-400 border-blue-600/40",
  SLOW_MOVING: "bg-amber-900/30 text-amber-400 border-amber-600/40",
  NON_MOVING: "bg-gray-900/30 text-gray-500 border-gray-600/40",
};

export default function DemandAnalyticsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("analytics.read");
  const [data, setData] = useState<DemandAnalyticsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<keyof DemandAnalyticsItem>("total_quantity_demanded");
  const [sortDesc, setSortDesc] = useState(true);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    void fetchData();
  }, [canRead]);

  async function fetchData() {
    setIsLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (category) params.category = category;
      const resp = await inventoryApi.getDemandAnalytics(params);
      setData(resp);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    } finally {
      setIsLoading(false);
    }
  }

  const sortedItems = useMemo(() => {
    if (!data) return [];
    return [...data.items].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return sortDesc ? bv - av : av - bv;
      }
      return 0;
    });
  }, [data, sortKey, sortDesc]);

  const handleSort = (key: keyof DemandAnalyticsItem) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      if (key === "total_quantity_demanded" || key === "total_revenue") {
        setSortDesc(true);
      } else {
        setSortDesc(false);
      }
    }
  };

  const handleExport = () => {
    if (!data) return;
    const headers = ["Product", "Category", "Quantity Demanded", "Total Revenue", "Avg Daily Consumption", "Velocity", "Reorder Suggestion"];
    const rows = data.items.map((it) => ({
      Product: it.product_name,
      Category: it.category || "",
      "Quantity Demanded": it.total_quantity_demanded,
      "Total Revenue": formatMoney(parseMoney(it.total_revenue)),
      "Avg Daily Consumption": it.avg_daily_consumption.toFixed(2),
      Velocity: it.velocity_category,
      "Reorder Suggestion": it.reorder_suggestion,
    }));
    downloadCsv("demand-analytics.csv", headers, rows);
  };

  const totalQty = data?.items.reduce((s, it) => s + it.total_quantity_demanded, 0) ?? 0;
  const totalRevenue = data?.items.reduce((s, it) => s + parseMoney(it.total_revenue), 0n) ?? 0n;
  const topProduct = data?.items.reduce((top, it) =>
    it.total_quantity_demanded > (top?.total_quantity_demanded ?? 0) ? it : top,
  );
  const slowOrNon = data?.items.filter(
    (it) => it.velocity_category === "SLOW_MOVING" || it.velocity_category === "NON_MOVING",
  ).length ?? 0;

  if (!isAuthenticated()) return null;
  if (!canRead) {
    return <p className="text-sm text-gray-400 p-4">You do not have permission to view demand analytics.</p>;
  }

  return (
    <main className="p-4 md:p-6 min-h-screen">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <h1 className="text-xl md:text-2xl font-bold text-gray-100">Demand Analytics</h1>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            disabled={!data || data.items.length === 0}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
          >
            Export CSV
          </button>
        </div>
      </header>

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 mb-4">
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <input
          type="text"
          placeholder="Category (e.g. OTC)"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        />
        <button
          onClick={() => void fetchData()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
        >
          Apply
        </button>
        <button
          onClick={() => {
            setStartDate("");
            setEndDate("");
            setCategory("");
            void fetchData();
          }}
          className="px-4 py-2 border border-gray-600 text-gray-300 hover:bg-gray-700 rounded-md text-sm font-medium"
        >
          Reset
        </button>
      </div>

      {error && <p className="text-sm text-red-400 mb-3" role="alert">{error}</p>}

      {/* KPI Cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{totalQty}</div>
            <p className="text-xs text-gray-400">Total Demanded</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{formatMoney(totalRevenue)}</div>
            <p className="text-xs text-gray-400">Total Revenue</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-purple-400 truncate">{topProduct?.product_name ?? "—"}</div>
            <p className="text-xs text-gray-400">Top Product</p>
          </div>
          <div className="rounded-lg bg-gray-800/60 p-4 text-center">
            <div className="text-2xl font-bold text-amber-400">{slowOrNon}</div>
            <p className="text-xs text-gray-400">Slow / Non-Moving</p>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && <p className="text-sm text-gray-400">Loading analytics…</p>}

      {/* Analytics Table */}
      {data && !isLoading && (
        <div className="overflow-x-auto rounded-lg border border-gray-700">
          <table className="min-w-[900px] w-full table-fixed border-collapse text-sm">
            <thead className="bg-gray-800/60">
              <tr>
                {["Product", "Category", "Qty Demanded", "Revenue", "Avg Daily", "Velocity", "Reorder"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-300">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {sortedItems.map((it) => (
                <tr key={it.product_id}>
                  <td className="px-3 py-2 truncate">{it.product_name}</td>
                  <td className="px-3 py-2 truncate text-gray-400">{it.category || "—"}</td>
                  <td className="px-3 py-2 text-right font-medium">{it.total_quantity_demanded}</td>
                  <td className="px-3 py-2 text-right text-gray-300">{formatMoney(parseMoney(it.total_revenue))}</td>
                  <td className="px-3 py-2 text-right text-gray-300">{it.avg_daily_consumption.toFixed(2)}</td>
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
    </main>
  );
}
