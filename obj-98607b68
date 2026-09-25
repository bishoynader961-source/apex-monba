"use client";

import { useState, useEffect, useMemo } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useCan } from "@/stores/authStore";
import { useReceivingLogStore } from "@/stores/receivingStore";
import { Calendar, Filter, Search, Package, Loader2 } from "lucide-react";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";

export default function ReceivingLogPage() {
  const {
    entries,
    vendors,
    total,
    page,
    pageSize,
    filters,
    isLoading,
    error,
    setFilters,
    fetchEntries,
    fetchVendors,
  } = useReceivingLogStore();

  const [dateInput, setDateInput] = useState(filters.date ?? "");
  const [vendorInput, setVendorInput] = useState(filters.vendor ?? "");

  useEffect(() => {
    fetchVendors();
  }, [fetchVendors]);

  useEffect(() => {
    void fetchEntries(1);
  }, [fetchEntries]);

  const handleFilter = () => {
    void setFilters({
      date: dateInput || undefined,
      vendor: vendorInput || undefined,
    });
  };

  const clearFilters = () => {
    setDateInput("");
    setVendorInput("");
    void setFilters({});
  };

const totalPages = Math.ceil(total / pageSize) || 1;

  const formatCurrency = (val: string | number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(Number(val));



  const columns = useMemo<Column<{ id: number; date_received: string; vendor_name: string; product_name: string; lot_number: string; quantity: number; total_cost: string | number; barcode: string }>[]>(() => [
    { key: "date_received", header: "Date Received", render: (row) => row.date_received || "—" },
    { key: "vendor_name", header: "Vendor", render: (row) => row.vendor_name },
    { key: "product_name", header: "Product", render: (row) => row.product_name },
    { key: "lot_number", header: "Lot", render: (row) => row.lot_number || "—" },
    { key: "quantity", header: "Qty", render: (row) => row.quantity, className: "text-right" },
    { key: "total_cost", header: "Total Cost", render: (row) => formatCurrency(row.total_cost), className: "text-right" },
    { key: "barcode", header: "Barcode", render: (row) => row.barcode || "—" },
  ], [formatCurrency]);

return (
    <DashboardLayout>
      <RouteGuard permission="inventory.read">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-3">
              <Package className="w-7 h-7 text-blue-400" />
              Receiving Log
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
              Global audit of all inventory receipts across all vendors
            </p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-3 rounded-md border text-sm bg-red-900/20 border-red-600/30 text-red-400">
            {error}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3 items-end">
          <div className="flex-1">
            <label htmlFor="receiving-date-filter" className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Date Filter</label>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
              <input
                id="receiving-date-filter"
                type="date"
                className="w-full pl-9 pr-4 py-2.5 bg-[#0d0d20] border border-gray-700 rounded-md text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                value={dateInput}
                onChange={(e) => setDateInput(e.target.value)}
              />
            </div>
          </div>
          <div className="flex-1">
            <label htmlFor="receiving-vendor-filter" className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Vendor Filter</label>
            <select
              id="receiving-vendor-filter"
              className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2.5 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm appearance-none"
              value={vendorInput}
              onChange={(e) => setVendorInput(e.target.value)}
            >
              <option value="">All Vendors</option>
              {vendors.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <button
              id="receiving-filter-btn"
              onClick={handleFilter}
              className="flex items-center gap-1.5 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors"
            >
              <Filter className="w-4 h-4" /> Apply
            </button>
            <button
              id="receiving-clear-btn"
              onClick={clearFilters}
              className="flex items-center gap-1.5 px-4 py-2.5 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm transition-colors"
            >
              Clear
            </button>
          </div>
        </div>

        {/* Table */}
        <DataTable
          columns={columns}
          data={entries ?? []}
          keyExtractor={(row) => row.id}
          loading={isLoading && entries === null}
          emptyMessage="No receiving log entries found."
          className="bg-[#1a1a2e] border border-gray-800"
        />

        {/* Pagination */}
        {entries && entries.length > 0 && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">
              Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of {total} entries
            </span>
            <div className="flex gap-1">
              <button
                id="receiving-prev-page"
                onClick={() => void fetchEntries(page - 1)}
                disabled={page <= 1}
                className="px-3 py-1 border border-gray-700 rounded text-gray-300 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <span className="px-3 py-1 text-gray-600 dark:text-gray-400">
                Page {page} of {totalPages}
              </span>
              <button
                id="receiving-next-page"
                onClick={() => void fetchEntries(page + 1)}
                disabled={page >= totalPages}
                className="px-3 py-1 border border-gray-700 rounded text-gray-300 hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}
