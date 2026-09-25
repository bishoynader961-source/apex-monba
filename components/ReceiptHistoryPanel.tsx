"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import { useCan } from "@/stores/authStore";
import { getRecentReceipts, getReceiptDetail, voidItem } from "@/lib/api/pos";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { ReceiptRead, ReceiptItemRead } from "@/types/contracts";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ReceiptHistoryPanel({ open, onClose }: Props) {
  const { t } = useI18n();
  const canVoid = useCan("pos.void_item");
  const [receipts, setReceipts] = useState<ReceiptRead[]>([]);
  const [selected, setSelected] = useState<ReceiptRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voidingItem, setVoidingItem] = useState<ReceiptItemRead | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [voiding, setVoiding] = useState(false);
  const [voidResult, setVoidResult] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    getRecentReceipts(50)
      .then((data) => { setReceipts(data); setLoading(false); })
      .catch((err) => { setError(String(err)); setLoading(false); });
  }, [open]);

  const handleSelect = async (r: ReceiptRead) => {
    try {
      const detail = await getReceiptDetail(r.id);
      setSelected(detail);
    } catch {
      setSelected(r);
    }
  };

  const handleVoid = async () => {
    if (!voidingItem) return;
    setVoiding(true);
    setVoidResult(null);
    try {
      const result = await voidItem({ receipt_item_id: voidingItem.id, reason: voidReason });
      setVoidResult(`Voided ${result.restocked_product} (x${result.quantity_restocked}) — refunded $${formatMoney(parseMoney(result.refund_amount))}`);
      setVoidingItem(null);
      setVoidReason("");
      // Refresh the selected receipt detail
      if (selected) {
        const refreshed = await getReceiptDetail(selected.id);
        setSelected(refreshed);
        // Also update the receipt in the list
        setReceipts((prev) => prev.map((r) => r.id === refreshed.id ? { ...r, total_amount: refreshed.total_amount, items: refreshed.items } : r));
      }
    } catch (err) {
      setVoidResult(`Error: ${err}`);
    } finally {
      setVoiding(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111] border border-gray-800 rounded-xl w-[720px] max-h-[80vh] shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 shrink-0">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {t("pos.receiptHistory") ?? "Receipt History"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Left: receipt list */}
          <div className="w-[280px] border-r border-gray-800 flex flex-col">
            <div className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 border-b border-gray-800">
              {t("pos.recentReceipts") ?? "Recent Receipts"}
            </div>
            <div className="flex-1 overflow-y-auto">
              {loading && (
                <div className="p-4 text-sm text-gray-500 text-center">Loading…</div>
              )}
              {error && (
                <div className="p-4 text-sm text-red-400 text-center">{error}</div>
              )}
              {!loading && receipts.length === 0 && (
                <div className="p-4 text-sm text-gray-500 text-center">
                  {t("pos.noReceipts") ?? "No receipts found"}
                </div>
              )}
              {receipts.map((r) => (
                <button
                  key={r.id}
                  onClick={() => handleSelect(r)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-800/50 transition-colors ${
                    selected?.id === r.id
                      ? "bg-blue-600/10 border-l-2 border-l-blue-500"
                      : "hover:bg-[#1a1a2e] border-l-2 border-l-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-800 dark:text-gray-200 font-medium">
                      {r.receipt_number || `RCP-${r.id}`}
                    </span>
                    <span className="text-sm text-green-400 font-medium">
                      ${formatMoney(parseMoney(r.total_amount))}
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-gray-500">
                      {r.timestamp ? new Date(r.timestamp).toLocaleString() : "—"}
                    </span>
                    <span className="text-xs text-gray-500">{r.payment_method}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Right: receipt detail */}
          <div className="flex-1 flex flex-col min-w-0">
            {!selected ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
                {t("pos.selectReceipt") ?? "← Select a receipt to view details"}
              </div>
            ) : (
              <>
                <div className="px-4 py-3 border-b border-gray-800 shrink-0">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                      {selected.receipt_number || `RCP-${selected.id}`}
                    </span>
                    <span className="text-sm text-green-400 font-semibold">
                      ${formatMoney(parseMoney(selected.total_amount))}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
                    <span>{selected.timestamp ? new Date(selected.timestamp).toLocaleString() : "—"}</span>
                    <span>{selected.payment_method}</span>
                    {selected.cashier_attribution && <span>by {selected.cashier_attribution}</span>}
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-600 dark:text-gray-400 border-b border-gray-800">
                        <th className="px-4 py-2 font-medium">{t("pos.colItem") ?? "Item"}</th>
                        <th className="px-4 py-2 font-medium text-center">{t("pos.colQty") ?? "Qty"}</th>
                        <th className="px-4 py-2 font-medium text-right">{t("pos.colPrice") ?? "Price"}</th>
                        <th className="px-4 py-2 font-medium text-right">{t("pos.colTotal") ?? "Total"}</th>
                        {canVoid && <th className="px-4 py-2 font-medium text-right w-16"></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {selected.items.map((item) => (
                        <tr key={item.id} className="border-b border-gray-800/50 hover:bg-[#1a1a2e]/50">
                          <td className="px-4 py-2 text-gray-800 dark:text-gray-200">{item.product_name}</td>
                          <td className="px-4 py-2 text-center text-gray-700 dark:text-gray-300">{item.quantity}</td>
                          <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-300">
                            ${formatMoney(parseMoney(item.price_at_time))}
                          </td>
                          <td className="px-4 py-2 text-right text-gray-800 dark:text-gray-200 font-medium">
                            ${formatMoney(parseMoney(item.price_at_time) * BigInt(item.quantity))}
                          </td>
                          {canVoid && (
                            <td className="px-4 py-2 text-right">
                              <button
                                onClick={() => { setVoidingItem(item); setVoidResult(null); }}
                                className="text-xs text-red-400 hover:text-red-300 transition-colors"
                              >
                                {t("pos.void") ?? "Void"}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Void item confirmation */}
        {voidingItem && (
          <div className="px-5 py-4 border-t border-gray-800 bg-[#1a1a2e]/50 shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-800 dark:text-gray-200">
                Void <strong>{voidingItem.product_name}</strong> (x{voidingItem.quantity})?
              </span>
              <button onClick={() => setVoidingItem(null)} className="text-gray-500 hover:text-gray-300 text-sm">
                {t("common.cancel") ?? "Cancel"}
              </button>
            </div>
            <input
              type="text"
              value={voidReason}
              onChange={(e) => setVoidReason(e.target.value)}
              placeholder={t("pos.voidReason") ?? "Reason (optional)"}
              className="w-full bg-[#0d0d20] border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 mb-2 focus:outline-none focus:border-blue-600"
            />
            <button
              onClick={() => void handleVoid()}
              disabled={voiding}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {voiding ? "Voiding…" : (t("pos.confirmVoid") ?? "Confirm Void")}
            </button>
          </div>
        )}

        {/* Void result message */}
        {voidResult && !voidingItem && (
          <div className="px-5 py-3 border-t border-gray-800 shrink-0">
            <p className={`text-sm ${voidResult.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
              {voidResult}
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-end px-5 py-4 border-t border-gray-800 shrink-0">
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
