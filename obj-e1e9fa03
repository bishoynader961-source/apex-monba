"use client";

import { useState } from "react";
import { Gift, Search } from "lucide-react";
import { lookupGiftCard, type GiftCard } from "@/lib/api/giftCards";

export function GiftCardBalanceCheck() {
  const [code, setCode] = useState("");
  const [card, setCard] = useState<GiftCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLookup = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    setCard(null);
    try {
      const result = await lookupGiftCard(code.trim());
      setCard(result);
    } catch {
      setError("Card not found");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <Gift className="w-4 h-4 text-pink-400" />
        <h3 className="text-xs font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wide">Gift Card Balance</h3>
      </div>
      <div className="flex gap-1.5">
        <input
          type="text"
          value={code}
          onChange={(e) => { setCode(e.target.value.toUpperCase()); setCard(null); setError(null); }}
          placeholder="GC-XXXXXXXX"
          className="flex-1 px-2 py-1.5 text-xs border border-gray-700 rounded bg-[#0d0d20] text-gray-800 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-pink-500 font-mono"
          onKeyDown={(e) => e.key === "Enter" && void handleLookup()}
        />
        <button
          onClick={() => void handleLookup()}
          disabled={loading || !code.trim()}
          className="px-2 py-1.5 bg-pink-600 hover:bg-pink-700 text-gray-900 dark:text-white rounded text-xs transition-colors disabled:opacity-50"
        >
          <Search className="w-3.5 h-3.5" />
        </button>
      </div>
      {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      {card && (
        <div className="mt-2 p-2 bg-[#0d0d20] rounded border border-gray-700">
          <div className="flex justify-between text-xs">
            <span className="text-gray-600 dark:text-gray-400">Balance</span>
            <span className={`font-bold ${card.current_balance > 0 ? "text-green-400" : "text-gray-500"}`}>
              ${card.current_balance.toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between text-xs mt-1">
            <span className="text-gray-600 dark:text-gray-400">Status</span>
            <span className={`font-semibold ${
              card.status === "active" ? "text-green-400" :
              card.status === "void" ? "text-red-400" : "text-gray-400"
            }`}>
              {card.status}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
