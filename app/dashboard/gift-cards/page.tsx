"use client";

import { useState, useEffect, useCallback } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useRouter } from "next/navigation";
import {
  issueGiftCard,
  listGiftCards,
  redeemGiftCard,
  voidGiftCard,
  lookupGiftCard,
  type GiftCard,
} from "@/lib/api/giftCards";
import { Gift, Search, Plus, Ban, CreditCard } from "lucide-react";
import { useToast } from "@/hooks/useToast";
// Money-safety invariant: currency math NEVER uses floating point.
// Server balances arrive as decimal strings (backend Decimal); all parsing,
// arithmetic, and display go through bigint-cent helpers.
import { parseMoney, formatMoney, cmpMoney } from "@/lib/decimalCurrency";

// Client-side guard without floating point: valid positive decimal string only.
function isValidMoneyInput(value: string): boolean {
  if (!/^-?\d+(\.\d+)?$/.test(value.trim())) return false;
  try {
    return cmpMoney(parseMoney(value), 0n) > 0;
  } catch {
    return false;
  }
}

const INPUT_STYLE =
  "w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm";

export default function GiftCardsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canWrite = useCan("pos.write");
  const { toast } = useToast();

  const [cards, setCards] = useState<GiftCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchCode, setSearchCode] = useState("");
  const [lookupResult, setLookupResult] = useState<GiftCard | null>(null);
  const [showIssue, setShowIssue] = useState(false);
  const [issueAmount, setIssueAmount] = useState("");
  const [issueNote, setIssueNote] = useState("");
  const [redeemAmount, setRedeemAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadCards = useCallback(async () => {
    setLoading(true);
    try {
      setCards(await listGiftCards());
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to load gift cards", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated()) void loadCards();
  }, [isAuthenticated, loadCards]);

  const handleLookup = async () => {
    if (!searchCode.trim()) return;
    setError(null);
    try {
      setLookupResult(await lookupGiftCard(searchCode.trim()));
    } catch (err) {
      setLookupResult(null);
      setError("Gift card not found");
      toast({ title: "Not Found", message: "Gift card not found", variant: "destructive" });
    }
  };

  const handleIssue = async () => {
    // Parse the decimal string exactly (bigint cents); reject invalid input.
    let amountCents: bigint;
    try {
      amountCents = parseMoney(issueAmount);
    } catch {
      return;
    }
    if (cmpMoney(amountCents, 0n) <= 0) return;
    setSaving(true);
    setError(null);
    try {
      // Backend takes a Decimal-compatible string, never a JS number.
      await issueGiftCard({ initial_balance: formatMoney(amountCents), note: issueNote || undefined });
      setShowIssue(false);
      setIssueAmount("");
      setIssueNote("");
      await loadCards();
      toast({ title: "Success", message: "Gift card issued", variant: "success" });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to issue card");
      toast({ title: "Error", message: e instanceof Error ? e.message : "Failed to issue card", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleRedeem = async (cardId: number) => {
    // Exact decimal-string parsing for the redeem amount (no float loss).
    let amountCents: bigint;
    try {
      amountCents = parseMoney(redeemAmount);
    } catch {
      return;
    }
    if (cmpMoney(amountCents, 0n) <= 0) return;
    setSaving(true);
    setError(null);
    try {
      await redeemGiftCard(cardId, formatMoney(amountCents));
      setRedeemAmount("");
      setLookupResult(null);
      setSearchCode("");
      await loadCards();
      toast({ title: "Success", message: "Gift card redeemed", variant: "success" });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to redeem");
      toast({ title: "Error", message: e instanceof Error ? e.message : "Failed to redeem", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleVoid = async (cardId: number) => {
    if (!confirm("Void this gift card? This cannot be undone.")) return;
    try {
      await voidGiftCard(cardId);
      setLookupResult(null);
      await loadCards();
      toast({ title: "Success", message: "Gift card voided", variant: "success" });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to void");
      toast({ title: "Error", message: e instanceof Error ? e.message : "Failed to void", variant: "destructive" });
    }
  };

  const activeCards = cards.filter((c) => c.status === "active");
  // Sum balances in bigint cents — floating-point addition of currency is forbidden.
  const totalBalanceCents = activeCards.reduce((sum, c) => sum + parseMoney(c.current_balance), 0n);
  // Display helper: decimal string -> exact 2-decimal string via bigint cents.
  const money = (v: string) => formatMoney(parseMoney(v));

  return (
    <DashboardLayout>
      <RouteGuard permission="giftCards.read">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Gift className="w-6 h-6 text-pink-500" />
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Gift Cards</h1>
        </div>
        {canWrite && (
          <button
            onClick={() => setShowIssue(true)}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors text-sm"
          >
            <Plus className="w-4 h-4" /> Issue Card
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-600/15 border border-red-600/30 text-red-400 px-4 py-2.5 rounded-lg text-sm mb-4 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-xs">Dismiss</button>
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Total Cards", value: cards.length.toString(), icon: CreditCard, color: "#ec4899" },
          { label: "Active Cards", value: activeCards.length.toString(), icon: Gift, color: "#22c55e" },
          { label: "Total Balance", value: `$${formatMoney(totalBalanceCents)}`, icon: CreditCard, color: "#3b82f6" },
        ].map((stat) => (
          <div key={stat.label} className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-4 flex items-center gap-3">
            <stat.icon className="w-5 h-5" style={{ color: stat.color }} />
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400">{stat.label}</div>
              <div className="text-lg font-bold text-gray-800 dark:text-gray-100">{stat.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Lookup */}
      <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 mb-6">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">Lookup Gift Card</h3>
        <div className="flex gap-2">
          <input
            className={INPUT_STYLE}
            placeholder="Enter gift card code (e.g. GC-A1B2C3D4)"
            value={searchCode}
            onChange={(e) => setSearchCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void handleLookup()}
          />
          <button
            onClick={() => void handleLookup()}
            disabled={!searchCode.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
          >
            <Search className="w-4 h-4" /> Lookup
          </button>
        </div>

        {lookupResult && (
          <div className="mt-4 bg-[#0d0d20] border border-gray-700 rounded-lg p-4">
            <div className="grid grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-600 dark:text-gray-400 text-xs block">Code</span>
                <span className="text-gray-800 dark:text-gray-100 font-mono font-semibold">{lookupResult.code}</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400 text-xs block">Balance</span>
                <span className="text-green-400 font-bold">${money(lookupResult.current_balance)}</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400 text-xs block">Status</span>
                <span className={`font-semibold ${lookupResult.status === "active" ? "text-green-400" : lookupResult.status === "void" ? "text-red-400" : "text-gray-400"}`}>
                  {lookupResult.status}
                </span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400 text-xs block">Issued</span>
                <span className="text-gray-700 dark:text-gray-300">{lookupResult.issued_at ? new Date(lookupResult.issued_at).toLocaleDateString() : "—"}</span>
              </div>
            </div>
            {lookupResult.status === "active" && canWrite && (
              <div className="flex gap-2 mt-4 pt-3 border-t border-gray-700">
                <input
                  className={INPUT_STYLE}
                  type="number"
                  step="0.01"
                  min="0"
                  max={lookupResult.current_balance}
                  placeholder="Redeem amount"
                  value={redeemAmount}
                  onChange={(e) => setRedeemAmount(e.target.value)}
                />
                <button
                  onClick={() => void handleRedeem(lookupResult.id)}
                  disabled={saving || !redeemAmount || !isValidMoneyInput(redeemAmount)}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
                >
                  Redeem
                </button>
                <button
                  onClick={() => void handleVoid(lookupResult.id)}
                  disabled={saving}
                  className="flex items-center gap-1 px-4 py-2 border border-red-600 text-red-400 hover:bg-red-600/10 rounded-md text-sm font-medium transition-colors disabled:opacity-50"
                >
                  <Ban className="w-3.5 h-3.5" /> Void
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Issue Dialog */}
      {showIssue && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">Issue Gift Card</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-1">Amount *</label>
                <input id="page-field-1"
                  className={INPUT_STYLE}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={issueAmount}
                  onChange={(e) => setIssueAmount(e.target.value)}
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block" htmlFor="page-field-2">Note (optional)</label>
                <input id="page-field-2"
                  className={INPUT_STYLE}
                  value={issueNote}
                  onChange={(e) => setIssueNote(e.target.value)}
                  placeholder="e.g. Birthday gift"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-6">
              <button
                onClick={() => { setShowIssue(false); setIssueAmount(""); setIssueNote(""); }}
                className="flex-1 px-3 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleIssue()}
                disabled={saving || !issueAmount || !isValidMoneyInput(issueAmount)}
                className="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
              >
                {saving ? "Issuing..." : "Issue Card"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Card List */}
      <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            {cards.length} card{cards.length !== 1 ? "s" : ""}
          </h3>
        </div>
        {loading ? (
          <div className="p-6 text-center text-gray-500 text-sm">Loading...</div>
        ) : cards.length === 0 ? (
          <div className="p-6 text-center text-gray-500 text-sm">No gift cards issued yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Code</th>
                  <th className="text-right px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Initial</th>
                  <th className="text-right px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Balance</th>
                  <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Status</th>
                  <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Issued</th>
                  <th className="text-left px-5 py-2.5 text-gray-600 dark:text-gray-400 font-medium">Note</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((card) => (
                  <tr key={card.id} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                    <td className="px-5 py-2.5 font-mono text-gray-800 dark:text-gray-100 font-semibold">{card.code}</td>
                    <td className="px-5 py-2.5 text-right text-gray-700 dark:text-gray-300">${money(card.initial_balance)}</td>
                    <td className="px-5 py-2.5 text-right text-green-400 font-semibold">${money(card.current_balance)}</td>
                    <td className="px-5 py-2.5">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        card.status === "active" ? "bg-green-600/20 text-green-400" :
                        card.status === "void" ? "bg-red-600/20 text-red-400" :
                        "bg-gray-600/20 text-gray-400"
                      }`}>
                        {card.status}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-gray-600 dark:text-gray-400">{card.issued_at ? new Date(card.issued_at).toLocaleDateString() : "—"}</td>
                    <td className="px-5 py-2.5 text-gray-600 dark:text-gray-400 text-xs">{card.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}
