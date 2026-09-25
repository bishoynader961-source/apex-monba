"use client";

import { useState, useMemo, useCallback } from "react";
import { forwardRef, useImperativeHandle } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
  sortable?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string | number;
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  selection?: {
    selectedKeys: Set<string | number>;
    onSelectionChange: (keys: Set<string | number>) => void;
    selectAll?: boolean;
    onSelectAll?: (selected: boolean) => void;
  };
  actions?: {
    render: (row: T) => React.ReactNode;
    header?: string;
    className?: string;
  };
  sort?: {
    key: string;
    direction: "asc" | "desc";
    onSort: (key: string) => void;
  };
  className?: string;
  stickyHeader?: boolean;
}

interface DataTableInstance {
  scrollToTop: () => void;
  scrollToBottom: () => void;
}

export const DataTable = forwardRef<DataTableInstance, DataTableProps<any>>(
  function DataTable(
    {
      columns,
      data,
      keyExtractor,
      loading = false,
      emptyMessage = "No data available",
      onRowClick,
      selection,
      actions,
      sort,
      className = "",
      stickyHeader = true,
    },
    ref
  ) {
    const [localSort, setLocalSort] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);

    const sortedData = useMemo(() => {
      if (!sort && !localSort) return data;

      const sortKey = sort?.key ?? localSort?.key;
      const direction = sort?.direction ?? localSort?.direction;

      if (!sortKey) return data;

      return [...data].sort((a, b) => {
        const aVal = (a as any)[sortKey];
        const bVal = (b as any)[sortKey];
        if (aVal === bVal) return 0;
        if (aVal === null || aVal === undefined) return 1;
        if (bVal === null || bVal === undefined) return -1;
        const cmp = aVal < bVal ? -1 : 1;
        return direction === "asc" ? cmp : -cmp;
      });
    }, [data, sort, localSort]);

    const handleSort = useCallback((key: string) => {
      if (sort) {
        sort.onSort(key);
      } else {
        setLocalSort((prev) => ({
          key,
          direction: prev?.key === key && prev.direction === "asc" ? "desc" : "asc",
        }));
      }
    }, [sort]);

    const handleSelectAll = useCallback(() => {
      if (selection) {
        if (selection.selectAll) {
          selection.onSelectionChange(new Set());
        } else {
          const allKeys = new Set(data.map(keyExtractor));
          selection.onSelectionChange(allKeys);
        }
      }
    }, [selection, data, keyExtractor]);

    const handleRowSelect = useCallback(
      (rowKey: string | number) => {
        if (selection) {
          const newSelection = new Set(selection.selectedKeys);
          if (newSelection.has(rowKey)) {
            newSelection.delete(rowKey);
          } else {
            newSelection.add(rowKey);
          }
          selection.onSelectionChange(newSelection);
        }
      }, [selection]);

    useImperativeHandle(ref, () => ({
      scrollToTop: () => {
        document.querySelector(".data-table-container")?.scrollTo({ top: 0, behavior: "smooth" });
      },
      scrollToBottom: () => {
        const container = document.querySelector(".data-table-container");
        container?.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
      },
    }));

    return (
      <div className={`data-table-wrapper ${className}`}>
        <div className="data-table-container overflow-x-auto rounded-lg border border-gray-700 dark:border-gray-700">
          {stickyHeader && (
            <div className="sticky top-0 z-10 bg-background dark:bg-[#0a0a1a]">
              <table className="min-w-full w-full table-fixed border-collapse text-sm data-table">
                <thead className="bg-gray-800/60 dark:bg-gray-900/60">
                  <tr className="border-b border-gray-700 dark:border-gray-700">
                    {selection && (
                      <th
                        className="px-3 py-2 text-center font-medium text-gray-700 dark:text-gray-300 w-12"
                        style={{ backgroundColor: "var(--bg-secondary)" }}
                      >
                        <input
                          type="checkbox"
                          checked={selection.selectAll && data.length > 0}
                          onChange={handleSelectAll}
                          className="w-4 h-4 text-blue-600 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                          aria-label="Select all"
                        />
                      </th>
                    )}
                    {columns.map((col) => (
                      <th
                        key={col.key}
                        className={`px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 ${col.headerClassName || ""} ${
                          col.sortable
                            ? "cursor-pointer select-none hover:bg-gray-700/50 dark:hover:bg-gray-600/50"
                            : ""
                        }`}
                        style={{
                          backgroundColor: "var(--bg-secondary)",
                          color: "var(--fg-muted)",
                          minWidth: col.className?.includes("w-") ? undefined : undefined,
                        }}
                        onClick={col.sortable ? () => handleSort(col.key) : undefined}
                      >
                        <span className="flex items-center gap-1">
                          {col.header}
                          {col.sortable && (
                            <span className="text-xs">
                              {sort?.key === col.key
                                ? sort.direction === "asc"
                                  ? "▲"
                                  : "▼"
                                : localSort?.key === col.key
                                ? localSort.direction === "asc"
                                  ? "▲"
                                  : "▼"
                                : ""}
                            </span>
                          )}
                        </span>
                      </th>
                    ))}
                    {actions && (
                      <th
                        className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300"
                        style={{ backgroundColor: "var(--bg-secondary)" }}
                      >
                        {actions.header ?? "Actions"}
                      </th>
                    )}
                  </tr>
                </thead>
              </table>
            </div>
          )}
          <div className="data-table-body" style={{ maxHeight: stickyHeader ? "calc(100vh - 200px)" : undefined }}>
            <table className="min-w-full w-full table-fixed border-collapse text-sm data-table">
              {!stickyHeader && (
                <thead className="bg-gray-800/60 dark:bg-gray-900/60">
                  <tr className="border-b border-gray-700 dark:border-gray-700">
                    {selection && (
                      <th
                        className="px-3 py-2 text-center font-medium text-gray-700 dark:text-gray-300 w-12"
                        style={{ backgroundColor: "var(--bg-secondary)" }}
                      >
                        <input
                          type="checkbox"
                          checked={selection.selectAll && data.length > 0}
                          onChange={() => selection?.onSelectionChange(
                            selection.selectAll ? new Set() : new Set(data.map(keyExtractor))
                          )}
                          className="w-4 h-4 text-blue-600 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                          aria-label="Select all"
                        />
                      </th>
                    )}
                    {columns.map((col) => (
                      <th
                        key={col.key}
                        className={`px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300 ${col.headerClassName || ""} ${
                          col.sortable
                            ? "cursor-pointer select-none hover:bg-gray-700/50 dark:hover:bg-gray-600/50"
                            : ""
                        }`}
                        style={{
                          backgroundColor: "var(--bg-secondary)",
                          color: "var(--fg-muted)",
                        }}
                        onClick={col.sortable ? () => handleSort(col.key) : undefined}
                      >
                        <span className="flex items-center gap-1">
                          {col.header}
                          {col.sortable && (
                            <span className="text-xs">
                              {sort?.key === col.key
                                ? sort.direction === "asc"
                                  ? "▲"
                                  : "▼"
                                : localSort?.key === col.key
                                ? localSort.direction === "asc"
                                  ? "▲"
                                  : "▼"
                                : ""}
                            </span>
                          )}
                        </span>
                      </th>
                    ))}
                    {actions && (
                      <th
                        className="px-3 py-2 text-right font-medium text-gray-700 dark:text-gray-300"
                        style={{ backgroundColor: "var(--bg-secondary)" }}
                      >
                        {actions.header ?? "Actions"}
                      </th>
                    )}
                  </tr>
                </thead>
              )}
              <tbody className="divide-y divide-gray-700 dark:divide-gray-700">
                {loading && (
                  <tr>
                    <td
                      colSpan={columns.length + (selection ? 1 : 0) + (actions ? 1 : 0)}
                      className="px-3 py-4 text-center text-gray-500"
                    >
                      Loading...
                    </td>
                  </tr>
                )}
                {!loading && data.length === 0 && (
                  <tr>
                    <td
                      colSpan={columns.length + (selection ? 1 : 0) + (actions ? 1 : 0)}
                      className="px-3 py-8 text-center text-gray-500"
                    >
                      {emptyMessage}
                    </td>
                  </tr>
                )}
                {!loading &&
                  data.map((row, index) => {
                    const rowKey = keyExtractor(row);
                    const isSelected = selection?.selectedKeys.has(rowKey);
                    return (
                      <tr
                        key={rowKey}
                        className={`border-b divide-gray-700 dark:divide-gray-700 transition-colors ${
                          isSelected ? "bg-blue-900/20 dark:bg-blue-900/10" : index % 2 === 1 ? "bg-black/5 dark:bg-white/5" : ""
                        }`}
                        onClick={() => onRowClick?.(row)}
                        style={{
                          cursor: onRowClick ? "pointer" : undefined,
                          color: "var(--fg)",
                          backgroundColor: isSelected
                            ? "rgba(59, 130, 246, 0.1)"
                            : index % 2 === 1
                            ? "rgba(255, 255, 255, 0.03)"
                            : "transparent",
                        }}
                      >
                        {selection && (
                          <td className="px-3 py-2 text-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => handleRowSelect(keyExtractor(row))}
                              className="w-4 h-4 text-blue-600 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                              aria-label={`Select row ${rowKey}`}
                            />
                          </td>
                        )}
                        {columns.map((col) => (
                          <td
                            key={col.key}
                            className={`px-3 py-2 ${col.className || ""} truncate`}
                            style={{
                              color: "var(--fg)",
                            }}
                          >
                            {col.render ? col.render(row) : (row as any)[col.key] ?? "—"}
                          </td>
                        ))}
                        {actions && (
                          <td className="px-3 py-2 text-right" style={{ color: "var(--fg)" }}>
                            {actions.render(data[index])}
                          </td>
                        )}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          {!loading && data.length === 0 && !actions && !selection && (
            <div className="p-8 text-center text-gray-500">{emptyMessage}</div>
          )}
        </div>
      </div>
    );
  }
);

DataTable.displayName = "DataTable";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[10px] font-semibold text-gray-500 dark:text-gray-400 block mb-1">{label}</label>
      {children}
    </div>
  );
}