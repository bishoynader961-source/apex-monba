"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useCan } from "@/stores/authStore";
import { TrendingUp, Package, DollarSign, RefreshCcw, Download, Mail } from "lucide-react";
import { sendDailySalesReport } from "@/lib/api/email";
import { useDashboardAnalyticsStore } from "@/stores/dashboardAnalyticsStore";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import { RouteGuard } from "@/components/RouteGuard";

type Period = "day" | "week" | "month";

interface TopSellingItem {
  rank: number;
  product_name: string;
  total_quantity: number;
  total_revenue: number;
  source: string;
}

interface TopSellingResponse {
  window_start: string;
  window_end: string;
  items: TopSellingItem[];
}

const PERIOD_LABELS: Record<Period, string> = {
  day: "Today",
  week: "This Week",
  month: "This Month",
};

export default function SalesAnalyticsPage() {
  const canRead = useCan("analytics.read");
  const [period, setPeriod] = useState<Period>("month");
  const [data, setData] = useState<TopSellingResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Dashboard analytics summary state
  const { data: summaryData, isLoading: summaryLoading, error: summaryError, fetch: fetchSummary } =
    useDashboardAnalyticsStore();

  const fetchData = useCallback(async (p: Period) => {
    if (!canRead) return;
    setIsLoading(true);
    setError(null);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";
      const res = await fetch(`/api/v1/analytics/top-selling?period=${p}&limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load analytics data");
      const json: TopSellingResponse = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  }, [canRead]);

  useEffect(() => {
    void fetchData(period);
    // Load the dashboard analytics summary on mount
    void fetchSummary();
  }, [period, fetchData]);

  const handleExport = () => {
    if (!data) return;
    const csvRows = [
      ["Rank", "Product Name", "Total Quantity", "Total Revenue ($)", "Source"],
      ...data.items.map((item) => [
        item.rank,
        item.product_name,
        item.total_quantity,
        item.total_revenue.toFixed(2),
        item.source,
      ]),
    ];
    const csv = csvRows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `top_selling_${period}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const totalRevenue = data?.items?.reduce((s, i) => s + i.total_revenue, 0) ?? 0;
  const totalUnits = data?.items?.reduce((s, i) => s + i.total_quantity, 0) ?? 0;

  const columns = useMemo<Column<TopSellingItem>[]>(() => [
    { key: "rank", header: "#", render: (row: TopSellingItem) => (
      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
        row.rank === 1 ? "bg-yellow-500/20 text-yellow-400"
        : row.rank === 2 ? "bg-gray-400/20 text-gray-300"
        : row.rank === 3 ? "bg-orange-700/20 text-orange-400"
        : "bg-gray-800 text-gray-500"
      }`}>
        {row.rank}
      </span>
    )},
    { key: "product_name", header: "Product Name", render: (row: TopSellingItem) => row.product_name },
    { key: "total_quantity", header: "Units Sold", render: (row: TopSellingItem) => row.total_quantity.toLocaleString(), className: "text-right" },
    { key: "total_revenue", header: "Revenue", render: (row: TopSellingItem) => `$${row.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, className: "text-right" },
    { key: "source", header: "Source", render: (row: TopSellingItem) => (
      <span className="px-2 py-0.5 rounded text-xs bg-blue-900/30 text-blue-400 border border-blue-600/30">
        {row.source}
      </span>
    ), className: "text-center" },
  ], []);

  return (
    <DashboardLayout>
      <RouteGuard permission="analytics.read">
      {/* ── Dashboard Analytics Summary ───────────────────────────────────── */}
      <div className="mb-6 p-4 bg-[#1a1a2e] border border-gray-800 rounded-lg">
        {summaryLoading ? (
          <p className="text-gray-600 dark:text-gray-400">Loading analytics summary…</p>
        ) : summaryError ? (
          <p className="text-red-400">{summaryError}</p>
        ) : summaryData ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center">
              <h3 className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Sales</h3>
              <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">
                {summaryData.total_sales.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div className="text-center">
              <h3 className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Customers</h3>
              <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">{summaryData.total_customers}</p>
            </div>
            <div className="text-center">
              <h3 className="text-sm text-gray-600 dark:text-gray-400 mb-1">Top Items</h3>
              <ul className="text-left list-disc list-inside space-y-0.5 text-gray-800 dark:text-gray-200">
                {summaryData.top_items.slice(0, 3).map((item, idx) => (
                  <li key={idx}>{item.product_name} – {item.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </div>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-3">
              <TrendingUp className="w-7 h-7 text-orange-400" />
              Sales Analytics
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
              Top-selling items filtered by time period
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExport}
              disabled={!data || isLoading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md transition-colors text-sm disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
              Export CSV
            </button>
            <button
              onClick={async () => {
                const email = prompt("Enter recipient email:");
                if (!email) return;
                try {
                  const result = await sendDailySalesReport({ to_email: email });
                  alert(result.message);
                } catch (e) {
                  alert("Failed to send report: " + (e instanceof Error ? e.message : String(e)));
                }
              }}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md transition-colors text-sm"
            >
              <Mail className="w-4 h-4" />
              Email Report
            </button>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5">
            <div className="flex items-center gap-3 text-orange-400 mb-2">
              <TrendingUp className="w-5 h-5" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Top Items</span>
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">{data?.items.length ?? 0}</p>
          </div>
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5">
            <div className="flex items-center gap-3 text-blue-400 mb-2">
              <Package className="w-5 h-5" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Total Units Sold</span>
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">{totalUnits.toLocaleString()}</p>
          </div>
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5">
            <div className="flex items-center gap-3 text-green-400 mb-2">
              <DollarSign className="w-5 h-5" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Total Revenue</span>
            </div>
            <p className="text-2xl font-bold text-gray-800 dark:text-gray-100">
              ${totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        {/* Period Toggle + Table */}
        <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg">
          {/* Toggle Controls */}
          <div className="flex items-center justify-between p-4 border-b border-gray-800">
            <div className="flex items-center gap-1 p-1 bg-[#0d0d20] rounded-lg">
              {(["day", "week", "month"] as Period[]).map((p) => (
                <button
                  key={p}
                  id={`period-toggle-${p}`}
                  onClick={() => setPeriod(p)}
                  className={`px-5 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
                    period === p
                      ? "bg-orange-600 text-white shadow-lg shadow-orange-900/40"
                      : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                  }`}
                >
                  {PERIOD_LABELS[p]}
                </button>
              ))}
            </div>
            {data && (
              <p className="text-xs text-gray-500">
                {data.window_start} → {data.window_end}
              </p>
            )}
            <button
              onClick={() => fetchData(period)}
              disabled={isLoading}
              className="p-2 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded-md transition-colors disabled:opacity-50"
            >
              <RefreshCcw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {/* Table */}
          {!canRead ? (
            <div className="p-10 text-center text-gray-500">
              You do not have permission to view analytics.
            </div>
          ) : error ? (
            <div className="p-10 text-center text-red-400">{error}</div>
          ) : isLoading ? (
            <div className="p-10 text-center text-gray-600 dark:text-gray-400">
              <RefreshCcw className="w-6 h-6 animate-spin mx-auto mb-3 text-orange-400" />
              Loading analytics…
            </div>
          ) : data && data.items.length > 0 ? (
            <DataTable
              columns={columns}
              data={data.items}
              keyExtractor={(row) => row.rank}
              loading={isLoading}
              emptyMessage="No sales data for this period."
              className="bg-[#1a1a2e] border border-gray-800"
            />
          ) : (
            <div className="p-10 text-center text-gray-500">
              No sales data for this period.
            </div>
          )}
        </div>
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}
