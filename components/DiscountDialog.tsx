"use client";

import { useState, useMemo } from "react";
import { useI18n } from "@/components/I18nProvider";

interface Props {
  open: boolean;
  cartSubtotal: number;
  onApply: (type: "%" | "$", value: number) => void;
  onClose: () => void;
}

export function DiscountDialog({ open, cartSubtotal, onApply, onClose }: Props) {
  const { t } = useI18n();
  const [discountType, setDiscountType] = useState<"%" | "$">("%");
  const [valueStr, setValueStr] = useState("");

  const parsedValue = useMemo(() => {
    const v = parseFloat(valueStr);
    return isNaN(v) ? 0 : v;
  }, [valueStr]);

  const savings = useMemo(() => {
    if (parsedValue <= 0) return 0;
    if (discountType === "%") return Math.min(cartSubtotal * parsedValue / 100, cartSubtotal);
    return Math.min(parsedValue, cartSubtotal);
  }, [discountType, parsedValue, cartSubtotal]);

  if (!open) return null;

  const handleApply = () => {
    if (parsedValue <= 0) return;
    if (discountType === "%" && parsedValue > 100) return;
    onApply(discountType, parsedValue);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111] border border-gray-800 rounded-xl w-[380px] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {t("pos.applyDiscount") ?? "Apply Discount"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Discount type toggle */}
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-2">
              {t("pos.discountType") ?? "Discount Type"}
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setDiscountType("%")}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                  discountType === "%"
                    ? "bg-blue-600 text-white"
                    : "bg-[#1a1a2e] text-gray-400 hover:bg-[#252540]"
                }`}
              >
                Percentage (%)
              </button>
              <button
                onClick={() => setDiscountType("$")}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                  discountType === "$"
                    ? "bg-blue-600 text-white"
                    : "bg-[#1a1a2e] text-gray-400 hover:bg-[#252540]"
                }`}
              >
                Flat ($)
              </button>
            </div>
          </div>

          {/* Amount input */}
          <div>
            <label htmlFor="discount-amount" className="block text-sm text-gray-600 dark:text-gray-400 mb-2">
              {t("pos.discountAmount") ?? "Amount"}
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 dark:text-gray-400 text-sm">
                {discountType}
              </span>
              <input
                id="discount-amount"
                type="number"
                min="0"
                max={discountType === "%" ? "100" : undefined}
                step={discountType === "%" ? "1" : "0.01"}
                value={valueStr}
                onChange={(e) => setValueStr(e.target.value)}
                placeholder={discountType === "%" ? "10" : "5.00"}
                className="w-full bg-[#0d0d20] border border-gray-800 rounded-lg pl-8 pr-3 py-2.5 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:border-blue-600"
              />
            </div>
          </div>

          {/* Savings preview */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">
              {t("pos.saving") ?? "Saving"}
            </span>
            <span className={savings > 0 ? "text-green-400 font-medium" : "text-gray-500"}>
              -{savings.toFixed(2)}
            </span>
          </div>

          {discountType === "%" && parsedValue > 100 && (
            <p className="text-xs text-red-400">
              {t("pos.discountExceeds100") ?? "Percentage cannot exceed 100%"}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-200 transition-colors"
          >
            {t("common.cancel") ?? "Cancel"}
          </button>
          <button
            onClick={handleApply}
            disabled={parsedValue <= 0 || (discountType === "%" && parsedValue > 100)}
            className="px-5 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {t("pos.apply") ?? "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
