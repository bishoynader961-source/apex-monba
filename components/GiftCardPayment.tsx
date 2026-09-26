"use client";

import { useState } from "react";
import { Gift } from "lucide-react";
import { lookupGiftCard } from "@/lib/api/giftCards";
// Money-safety invariant: balances are decimal strings; all arithmetic and
// comparisons happen in bigint cents. No parseFloat/Number on money, ever.
import { parseMoney, formatMoney, cmpMoney, type Cents } from "@/lib/decimalCurrency";

/** Decimal money string ("12.34") — matches the backend Money = string contract. */
type Money = string;

interface GiftCardPaymentProps {
  totalAmount: Money;
  onApply: (code: string, cardId: number, amount: Money) => void;
  disabled?: boolean;
}

export function GiftCardPayment({ totalAmount, onApply, disabled }: GiftCardPaymentProps) {
  const [code, setCode] = useState("");
  const [balance, setBalance] = useState<Money | null>(null);
  const [cardId, setCardId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);

  const handleLookup = async () => {
    if (!code.trim()) return;
    setLooking(true);
    setError(null);
    setBalance(null);
    setCardId(null);
    try {
      const card = await lookupGiftCard(code.trim());
      if (card.status !== "active") {
        setError(`Card is ${card.status}`);
      } else if (cmpMoney(parseMoney(card.current_balance), 0n) <= 0) {
        setError("Card has no balance");
      } else {
        setBalance(card.current_balance);
        setCardId(card.id);
      }
    } catch {
      setError("Card not found");
    } finally {
      setLooking(false);
    }
  };

  const handleApply = () => {
    if (cardId === null || balance === null) return;
    // Apply the lesser of card balance and cart total — computed in cents.
    let applyAmount: Cents;
    try {
      const totalCents = parseMoney(totalAmount);
      const balanceCents = parseMoney(balance);
      applyAmount = cmpMoney(balanceCents, totalCents) <= 0 ? balanceCents : totalCents;
    } catch {
      setError("Invalid amount");
      return;
    }
    onApply(code.trim(), cardId, formatMoney(applyAmount));
    setCode("");
    setBalance(null);
    setCardId(null);
  };

  const applyPreview = (() => {
    if (balance === null) return null;
    try {
      const totalCents = parseMoney(totalAmount);
      const balanceCents = parseMoney(balance);
      return cmpMoney(balanceCents, totalCents) <= 0 ? balanceCents : totalCents;
    } catch {
      return null;
    }
  })();

  return (
    <div className="flex items-center gap-2">
      <Gift className="w-4 h-4 text-pink-400 flex-shrink-0" />
      <input
        type="text"
        value={code}
        onChange={(e) => { setCode(e.target.value.toUpperCase()); setBalance(null); setCardId(null); setError(null); }}
        placeholder="Gift card code"
        disabled={disabled}
        className="flex-1 px-2 py-1.5 text-xs border border-gray-600 rounded bg-[#0d0d20] text-gray-800 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-pink-500 font-mono"
        onKeyDown={(e) => e.key === "Enter" && void handleLookup()}
      />
      {balance === null ? (
        <button
          onClick={() => void handleLookup()}
          disabled={disabled || looking || !code.trim()}
          className="px-2 py-1.5 text-xs bg-pink-600 hover:bg-pink-700 text-gray-900 dark:text-white rounded transition-colors disabled:opacity-50"
        >
          {looking ? "..." : "Check"}
        </button>
      ) : (
        <button
          onClick={handleApply}
          disabled={disabled}
          className="px-2 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded transition-colors disabled:opacity-50"
        >
          Apply ${applyPreview !== null ? formatMoney(applyPreview) : "—"}
        </button>
      )}
      {error && <span className="text-xs text-red-400">{error}</span>}
      {balance !== null && (
        <span className="text-xs text-green-400">${formatMoney(parseMoney(balance))} avail</span>
      )}
    </div>
  );
}
