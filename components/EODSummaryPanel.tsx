"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import { getEODSummary } from "@/lib/api/pos";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { EODSummary } from "@/types/contracts";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function EODSummaryPanel({ open, onClose }: Props) {
  const { t } = useI18n();
  const [data, setData] = useState<EODSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    getEODSummary()
      .then((d) => { setData(d); setLoading(false); })
      .catch((err) => { setError(String(err)); setLoading(false); });
  }, [open]);

  const handleExportCSV = () => {
    if (!data) return;
    const lines: string[] = [
      `End of Day — ${data.date}`,
      `Total Revenue,${formatMoney(parseMoney(data.total_revenue))}`,
      `Transactions,${data.transaction_count}`,
      `Items Sold,${data.items_sold}`,
      "",
      "Receipt #,Time,Payment Method,Item,Qty,Unit Price,Line Total",
    ];
    for (const r of data.receipts) {
      const time = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : "";
      for (const item of r.items) {
        const unit = parseMoney(item.price_at_time);
        const lineTotal = unit * BigInt(item.quantity);
        lines.push(`${r.receipt_number},${time},${r.payment_method},"${item.product_name}",${item.quantity},${formatMoney(unit)},${formatMoney(lineTotal)}`);
      }
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `EOD_${data.date}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111] border border-gray-800 rounded-xl w-[680px] max-h-[80vh] shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {t("pos.eodSummary") ?? "End of Day Summary"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loading && <div className="text-sm text-gray-500 text-center py-6">Loading…</div>}
          {error && <div className="text-sm text-red-400 text-center py-6">{error}</div>}

          {data && (
            <>
              {/* KPI cards */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-[#0d0d20] rounded-lg p-3 text-center">
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">{t("pos.totalRevenue") ?? "Total Revenue"}</div>
                  <div className="text-lg font-bold text-green-400">${formatMoney(parseMoney(data.total_revenue))}</div>
                </div>
                <div className="bg-[#0d0d20] rounded-lg p-3 text-center">
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">{t("pos.transactions") ?? "Transactions"}</div>
                  <div className="text-lg font-bold text-blue-400">{data.transaction_count}</div>
                </div>
                <div className="bg-[#0d0d20] rounded-lg p-3 text-center">
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">{t("pos.itemsSold") ?? "Items Sold"}</div>
                  <div className="text-lg font-bold text-amber-400">{data.items_sold}</div>
                </div>
              </div>

              {/* Payment method breakdown */}
              {Object.keys(data.by_payment_method).length > 0 && (
                <div className="bg-[#0d0d20] rounded-lg p-3">
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">{t("pos.byPaymentMethod") ?? "By Payment Method"}</div>
                  <div className="flex gap-4 flex-wrap">
                    {Object.entries(data.by_payment_method).map(([method, amount]) => (
                      <div key={method} className="text-sm">
                        <span className="text-gray-600 dark:text-gray-400">{method}: </span>
                        <span className="text-gray-800 dark:text-gray-200 font-medium">${formatMoney(parseMoney(amount))}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Receipts detail */}
              <div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {t("pos.todayReceipts") ?? "Today's Receipts"} ({data.receipts.length})
                </div>
                {data.receipts.length === 0 ? (
                  <div className="text-sm text-gray-500 text-center py-4">
                    {t("pos.noReceiptsToday") ?? "No receipts for today"}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.receipts.map((r) => (
                      <div key={r.receipt_id} className="bg-[#0d0d20] rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-gray-800 dark:text-gray-200 font-medium">{r.receipt_number}</span>
                          <span className="text-sm text-green-400 font-medium">${formatMoney(parseMoney(r.total_amount))}</span>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-gray-500 mb-2">
                          <span>{r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : "—"}</span>
                          <span>{r.payment_method}</span>
                        </div>
                        {r.items.length > 0 && (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-gray-500">
                                <th className="text-left py-0.5">Item</th>
                                <th className="text-center py-0.5 w-12">Qty</th>
                                <th className="text-right py-0.5 w-16">Price</th>
                              </tr>
                            </thead>
                            <tbody>
                              {r.items.map((item, idx) => (
                                <tr key={idx} className="text-gray-600 dark:text-gray-400">
                                  <td className="py-0.5">{item.product_name}</td>
                                  <td className="text-center py-0.5">{item.quantity}</td>
                                  <td className="text-right py-0.5">${formatMoney(parseMoney(item.price_at_time))}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-800 shrink-0">
          <button
            onClick={handleExportCSV}
            disabled={!data}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {t("pos.exportCSV") ?? "Export CSV"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-200 transition-colors"
          >
            {t("common.close") ?? "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
