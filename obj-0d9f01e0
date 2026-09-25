"use client";

import { useState, useMemo } from "react";
import { useI18n } from "@/components/I18nProvider";

interface PaymentRow {
  method: string;
  amount: string;
}

interface Props {
  open: boolean;
  total: number;
  onConfirm: (payments: Array<{ method: string; amount: string }>) => void;
  onClose: () => void;
}

const PAYMENT_METHODS = ["Cash", "Card", "Transfer", "Insurance"];

export function SplitPaymentDialog({ open, total, onConfirm, onClose }: Props) {
  const { t } = useI18n();
  const [payments, setPayments] = useState<PaymentRow[]>([
    { method: "Cash", amount: "" },
    { method: "Card", amount: "" },
  ]);

  const parsedPayments = useMemo(() => {
    return payments.map((p) => {
      const v = parseFloat(p.amount);
      return { method: p.method, amount: isNaN(v) ? 0 : v };
    });
  }, [payments]);

  const sum = useMemo(() => parsedPayments.reduce((s, p) => s + p.amount, 0), [parsedPayments]);
  const remaining = total - sum;

  if (!open) return null;

  const updateRow = (idx: number, field: keyof PaymentRow, value: string) => {
    setPayments((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));
  };

  const addRow = () => {
    const used = new Set(payments.map((p) => p.method));
    const next = PAYMENT_METHODS.find((m) => !used.has(m)) ?? "Cash";
    setPayments((prev) => [...prev, { method: next, amount: "" }]);
  };

  const removeRow = (idx: number) => {
    if (payments.length <= 1) return;
    setPayments((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleConfirm = () => {
    const valid = parsedPayments.filter((p) => p.amount > 0);
    if (valid.length === 0 || remaining > 0.01) return;
    onConfirm(valid.map((p) => ({ method: p.method, amount: p.amount.toFixed(2) })));
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111] border border-gray-800 rounded-xl w-[420px] shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {t("pos.splitPayment") ?? "Split Payment"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            &times;
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">{t("pos.total") ?? "Total"}</span>
            <span className="text-green-400 font-semibold text-lg">${total.toFixed(2)}</span>
          </div>

          {payments.map((row, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <select
                value={row.method}
                onChange={(e) => updateRow(idx, "method", e.target.value)}
                className="bg-[#0d0d20] border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 w-[120px] focus:outline-none focus:border-blue-600"
              >
                {PAYMENT_METHODS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 dark:text-gray-400 text-sm">$</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.amount}
                  onChange={(e) => updateRow(idx, "amount", e.target.value)}
                  placeholder="0.00"
                  className="w-full bg-[#0d0d20] border border-gray-800 rounded-lg pl-7 pr-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:border-blue-600"
                />
              </div>
              <button
                onClick={() => removeRow(idx)}
                disabled={payments.length <= 1}
                className="text-gray-500 hover:text-red-400 disabled:text-gray-700 text-lg leading-none px-1"
              >
                &times;
              </button>
            </div>
          ))}

          <button
            onClick={addRow}
            disabled={payments.length >= PAYMENT_METHODS.length}
            className="w-full py-1.5 text-sm text-blue-400 hover:text-blue-300 disabled:text-gray-600 border border-dashed border-gray-700 rounded-lg transition-colors"
          >
            + Add Payment Method
          </button>

          <div className="flex items-center justify-between text-sm pt-2 border-t border-gray-800">
            <span className="text-gray-600 dark:text-gray-400">{t("pos.remaining") ?? "Remaining"}</span>
            <span className={remaining <= 0.01 ? "text-green-400 font-medium" : "text-amber-400 font-medium"}>
              ${remaining > 0 ? remaining.toFixed(2) : "0.00"}
            </span>
          </div>

          {remaining > 0.01 && (
            <p className="text-xs text-amber-400">
              {t("pos.splitInsufficient") ?? "Payments must cover the full total."}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-200 transition-colors"
          >
            {t("common.cancel") ?? "Cancel"}
          </button>
          <button
            onClick={handleConfirm}
            disabled={remaining > 0.01 || sum === 0}
            className="px-5 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {t("pos.confirmSplit") ?? "Confirm Split"}
          </button>
        </div>
      </div>
    </div>
  );
}
