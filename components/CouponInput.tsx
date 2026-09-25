"use client";

import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { validateCoupon } from "@/lib/api/coupons";
import { usePosStore } from "@/stores/posStore";
import { formatMoney, parseMoney, sumMoney, mulByQty } from "@/lib/decimalCurrency";

export function CouponInput() {
  const { t } = useI18n();
  const lines = usePosStore((s) => s.lines ?? []);
  const discountType = usePosStore((s) => s.discountType);
  const discountValue = usePosStore((s) => s.discountValue);
  const setDiscount = usePosStore((s) => s.setDiscount);
  const clearDiscount = usePosStore((s) => s.clearDiscount);

  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  const subtotal = Number(sumMoney(lines.map((l) => mulByQty(parseMoney(l.unit_price), l.quantity))) / 100n);

  const handleApply = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    setApplied(false);
    try {
      const result = await validateCoupon(code.trim(), subtotal);
      if (result.valid) {
        setDiscount(result.discount_type as "%" | "$", Number(result.discount_value));
        setApplied(true);
        setError(null);
      } else {
        setError(result.message);
        setApplied(false);
      }
    } catch (err) {
      setError(String(err));
      setApplied(false);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    clearDiscount();
    setCode("");
    setApplied(false);
    setError(null);
  };

  // Show applied state
  if (applied && discountType) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs px-2 py-1 bg-violet-600/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400 rounded">
          {code.toUpperCase()} ({discountType}{discountValue})
        </span>
        <button
          onClick={handleClear}
          className="text-xs text-red-600 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        value={code}
        onChange={(e) => { setCode(e.target.value); setError(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") void handleApply(); }}
        placeholder={t("pos.couponPlaceholder") ?? "Coupon code"}
        disabled={lines.length === 0}
        className="w-[110px] px-2 py-1 text-xs rounded border bg-gray-900 dark:bg-gray-800 text-gray-100 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        style={{ borderColor: error ? "#dc2626" : "#d1d5db" }}
      />
      <button
        onClick={() => void handleApply()}
        disabled={lines.length === 0 || !code.trim() || loading}
        className="px-2 py-1 text-xs rounded border border-gray-600 dark:border-gray-500 bg-gray-800 dark:bg-gray-700 text-white hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "…" : (t("pos.apply") ?? "Apply")}
      </button>
      {error && <span className="text-[10px] text-red-600 dark:text-red-400 ml-1">{error}</span>}
    </div>
  );
}
