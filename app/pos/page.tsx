"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore, useCan } from "@/stores/authStore";
import {
  ShoppingCart,
  Search,
  Trash2,
  Plus,
  Minus,
  CreditCard,
  Banknote,
  ArrowLeftRight,
  Layers,
  CheckCircle2,
  AlertCircle,
  Wifi,
  WifiOff,
  Printer,
  ChevronLeft,
  Tag,
  User,
  X,
  ReceiptText,
} from "lucide-react";

import { usePosStore } from "@/stores/posStore";
import { useI18n } from "@/components/I18nProvider";
import { ReceiptPrintPreview } from "@/components/ReceiptPrintPreview";
import { SplitPaymentDialog } from "@/components/SplitPaymentDialog";
import { DiscountDialog } from "@/components/DiscountDialog";
import { searchMedicines } from "@/lib/api/inventory";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { ProductRead, CartLine } from "@/types/contracts";
import { useToast } from "@/hooks/useToast";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtPrice(price: string | number): string {
  try {
    if (typeof price === "number") {
      return formatMoney(parseMoney(BigInt(Math.round(price * 100))));
    }
    const cents = Math.round(parseFloat(price) * 100);
    return formatMoney(parseMoney(BigInt(cents)));
  } catch {
    return String(price);
  }
}

function parseMoneyNum(m: string): number {
  try {
    return parseFloat(m) || 0;
  } catch {
    return 0;
  }
}

type PaymentMethod = "Cash" | "Card" | "Transfer" | "Split";
const PAYMENT_METHODS: PaymentMethod[] = ["Cash", "Card", "Transfer", "Split"];
const PAYMENT_ICONS: Record<PaymentMethod, React.ReactNode> = {
  Cash: <Banknote size={15} />,
  Card: <CreditCard size={15} />,
  Transfer: <ArrowLeftRight size={15} />,
  Split: <Layers size={15} />,
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function CartRow({
  line,
  onInc,
  onDec,
  onRemove,
}: {
  line: CartLine;
  onInc: () => void;
  onDec: () => void;
  onRemove: () => void;
}) {
  const lineTotal = parseMoneyNum(line.unit_price) * line.quantity;
  return (
    <tr className="border-b border-[--border] last:border-0 hover:bg-emerald-50/40 transition-colors">
      <td className="py-2 px-3">
        <span className="text-sm font-medium text-[--text-main] leading-snug">{line.product_name}</span>
      </td>
      <td className="py-2 px-2 text-center">
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={onDec}
            className="w-6 h-6 rounded flex items-center justify-center bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors"
            aria-label="Decrease quantity"
          >
            <Minus size={12} />
          </button>
          <span className="w-8 text-center text-sm font-semibold text-[--text-main]">{line.quantity}</span>
          <button
            onClick={onInc}
            className="w-6 h-6 rounded flex items-center justify-center bg-emerald-100 hover:bg-emerald-200 text-emerald-700 transition-colors"
            aria-label="Increase quantity"
          >
            <Plus size={12} />
          </button>
        </div>
      </td>
      <td className="py-2 px-2 text-right text-sm text-slate-500">{fmtPrice(line.unit_price)}</td>
      <td className="py-2 px-3 text-right text-sm font-semibold text-[--text-main]">
        {fmtPrice(String(lineTotal))}
      </td>
      <td className="py-2 px-2 text-center">
        <button
          onClick={onRemove}
          className="w-6 h-6 rounded flex items-center justify-center text-gray-600 dark:text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          aria-label="Remove item"
        >
          <Trash2 size={13} />
        </button>
      </td>
    </tr>
  );
}

function SearchResult({
  product,
  onAdd,
}: {
  product: ProductRead;
  onAdd: () => void;
}) {
  const isLowStock = (product.reorder_threshold ?? 5) >= 1;
  const expiryWarning =
    product.expiry_date
      ? (() => {
          const daysLeft = Math.ceil(
            (new Date(product.expiry_date).getTime() - Date.now()) / 86_400_000,
          );
          if (daysLeft < 7) return "critical";
          if (daysLeft < 30) return "warning";
          return null;
        })()
      : null;

  return (
    <button
      onClick={onAdd}
      className="w-full text-left px-3 py-2.5 hover:bg-emerald-50 border-b border-[--border] last:border-0 transition-colors group"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[--text-main] truncate">{product.name}</p>
          <p className="text-xs text-[--text-muted]">
            {product.vendor_name && product.vendor_name !== "N/A" && (
              <span className="mr-2">{product.vendor_name}</span>
            )}
            {product.expiry_date && (
              <span
                className={
                  expiryWarning === "critical"
                    ? "text-red-500 font-medium"
                    : expiryWarning === "warning"
                    ? "text-amber-500"
                    : ""
                }
              >
                Exp: {product.expiry_date}
              </span>
            )}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-sm font-bold text-emerald-700">{fmtPrice(product.price)}</p>
          {expiryWarning === "critical" && (
            <span className="text-[10px] font-medium text-red-500 bg-red-50 px-1 rounded">EXPIRES SOON</span>
          )}
        </div>
      </div>
    </button>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PosPage() {
  const { t } = useI18n();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canCheckout = useCan("pos.checkout");
  const { toast } = useToast();

  // Store selectors
  const lines = usePosStore((s) => s.lines ?? []);
  const offlineCount = usePosStore((s) => s.offlineCount);
  const syncing = usePosStore((s) => s.syncing);
  const result = usePosStore((s) => s.result);
  const error = usePosStore((s) => s.error);
  const hydrated = usePosStore((s) => s.hydrated);
  const discountType = usePosStore((s) => s.discountType);
  const discountValue = usePosStore((s) => s.discountValue);
  const taxExempt = usePosStore((s) => s.taxExempt);
  const addLine = usePosStore((s) => s.addLine);
  const updateQty = usePosStore((s) => s.updateQty);
  const remove = usePosStore((s) => s.remove);
  const clear = usePosStore((s) => s.clear);
  const setResult = usePosStore((s) => s.setResult);
  const setError = usePosStore((s) => s.setError);
  const toggleTaxExempt = usePosStore((s) => s.toggleTaxExempt);
  const doCheckout = usePosStore((s) => s.checkout);
  const hydrate = usePosStore((s) => s.hydrate);
  const ensureShift = usePosStore((s) => s.ensureShift);
  const setPayments = usePosStore((s) => s.setPayments);

  // Local UI state
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ProductRead[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("Cash");
  const [amountTendered, setAmountTendered] = useState("");
  const [processing, setProcessing] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [showSplitDialog, setShowSplitDialog] = useState(false);
  const [showDiscountDialog, setShowDiscountDialog] = useState(false);
  const [isOnline, setIsOnline] = useState(true);

  const searchRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Auth guard
  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  // Hydrate store + ensure shift on mount
  useEffect(() => {
    void hydrate();
    void ensureShift();
    searchRef.current?.focus();
  }, [hydrate, ensureShift]);

  // Online/offline detection
  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    setIsOnline(navigator.onLine);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // Auto-show receipt on successful checkout
  useEffect(() => {
    if (result) setShowReceipt(true);
  }, [result]);

  // F12 → checkout
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "F12") {
        e.preventDefault();
        void handleCheckout();
      }
      if (e.key === "Escape") {
        setShowResults(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, paymentMethod]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounced search
  const handleSearchChange = useCallback((value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }
    setSearchLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const items = await searchMedicines(value);
        setSearchResults(items.filter((i) => !i.is_deleted && i.status === "In Stock"));
        setShowResults(true);
      } catch {
        setSearchResults([]);
        toast({ title: "Error", message: "Failed to search products", variant: "destructive" });
      } finally {
        setSearchLoading(false);
      }
    }, 250);
  }, [toast]);

  const handleAddProduct = useCallback(
    (product: ProductRead) => {
      addLine(product);
      setQuery("");
      setSearchResults([]);
      setShowResults(false);
      searchRef.current?.focus();
    },
    [addLine],
  );

  // ── Totals ───────────────────────────────────────────────────────────────────
  const subtotal = lines.reduce((acc, l) => acc + parseMoneyNum(l.unit_price) * l.quantity, 0);
  const discountAmount = (() => {
    if (!discountType || discountValue == null) return 0;
    if (discountType === "%") return subtotal * (discountValue / 100);
    return Math.min(discountValue, subtotal);
  })();
  const afterDiscount = subtotal - discountAmount;
  // Tax rate from config (we use a reasonable default of 8.5% client-side for display;
  // the server recalculates the authoritative value on checkout)
  const TAX_RATE = taxExempt ? 0 : 0.085;
  const taxAmount = afterDiscount * TAX_RATE;
  const total = afterDiscount + taxAmount;
  const changeDue = amountTendered ? Math.max(0, parseFloat(amountTendered) - total) : 0;

  // ── Checkout ─────────────────────────────────────────────────────────────────
  const handleCheckout = useCallback(async () => {
    if (lines?.length === 0 || processing) return;
    if (paymentMethod === "Split") {
      setShowSplitDialog(true);
      return;
    }
    setProcessing(true);
    setError(null);
    try {
      await doCheckout(paymentMethod);
      toast({ title: "Success", message: "Checkout completed", variant: "success" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Checkout failed";
      setError(msg);
      toast({ title: "Error", message: msg, variant: "destructive" });
    } finally {
      setProcessing(false);
    }
  }, [lines, paymentMethod, processing, doCheckout, setError, toast]);

  // ── Receipt close ─────────────────────────────────────────────────────────────
  const handleReceiptClose = useCallback(() => {
    setShowReceipt(false);
    setResult(null);
    setAmountTendered("");
    searchRef.current?.focus();
  }, [setResult]);

  if (!isAuthenticated()) return null;

  const isEmpty = lines.length === 0;

  return (
    <div className="flex flex-col h-screen bg-[--bg-primary] overflow-hidden">
      {/* ── Top Bar ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2.5 bg-[--brand-sidebar] shadow-md z-10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1.5 text-emerald-200/70 hover:text-white transition-colors text-sm"
          >
            <ChevronLeft size={16} />
            <span className="hidden sm:inline">Dashboard</span>
          </button>
          <div className="h-4 w-px bg-white/20" />
          <div className="flex items-center gap-2">
            <ShoppingCart size={18} className="text-emerald-300" />
            <span className="text-gray-900 dark:text-white font-semibold text-base tracking-tight">Point of Sale</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Offline / queue badge */}
          {offlineCount > 0 && (
            <div className="flex items-center gap-1.5 bg-amber-500/20 border border-amber-400/30 text-amber-300 text-xs px-2.5 py-1 rounded-full font-medium">
              <WifiOff size={12} />
              <span>{offlineCount} queued</span>
            </div>
          )}
          {syncing && (
            <div className="flex items-center gap-1.5 text-emerald-300 text-xs">
              <span className="animate-pulse">Syncing…</span>
            </div>
          )}
          {/* Connection indicator */}
          <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${isOnline ? "text-emerald-300" : "text-red-300"}`}>
            {isOnline ? <Wifi size={12} /> : <WifiOff size={12} />}
            <span className="hidden sm:inline">{isOnline ? "Online" : "Offline"}</span>
          </div>
          {/* User */}
          {user && (
            <div className="flex items-center gap-1.5 text-emerald-200/70 text-sm">
              <User size={14} />
              <span className="hidden md:inline">{user.username}</span>
            </div>
          )}
        </div>
      </header>

      {/* ── Main Layout ─────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: Cart ──────────────────────────────────────────────────── */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          {/* Search bar */}
          <div className="px-4 pt-3 pb-2 bg-white border-b border-[--border] flex-shrink-0">
            <div className="relative" ref={dropdownRef}>
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 dark:text-slate-400 pointer-events-none" />
              <input
                ref={searchRef}
                id="pos-search"
                type="text"
                value={query}
                onChange={(e) => handleSearchChange(e.target.value)}
                onFocus={() => searchResults.length > 0 && setShowResults(true)}
                placeholder="Search medicine by name or barcode… (Enter to add first result)"
                className="w-full pl-9 pr-4 py-2.5 text-sm border border-[--border] rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-emerald-400 bg-[--bg-primary] text-[--text-main] placeholder:text-slate-400"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && searchResults.length > 0) {
                    handleAddProduct(searchResults[0]);
                  }
                }}
                autoComplete="off"
              />
              {searchLoading && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
                </div>
              )}

              {/* Dropdown results */}
              {showResults && searchResults.length > 0 && (
                <div className="absolute z-50 w-full top-full mt-1 bg-white border border-[--border] rounded-lg shadow-lg max-h-72 overflow-y-auto">
                  {searchResults.map((p) => (
                    <SearchResult key={p.id} product={p} onAdd={() => handleAddProduct(p)} />
                  ))}
                </div>
              )}
              {showResults && !searchLoading && query && searchResults.length === 0 && (
                <div className="absolute z-50 w-full top-full mt-1 bg-white border border-[--border] rounded-lg shadow-lg px-4 py-3 text-sm text-gray-600 dark:text-slate-400">
                  No medicines found for &quot;{query}&quot;
                </div>
              )}
            </div>
          </div>

          {/* Cart table */}
          <div className="flex-1 overflow-y-auto bg-white">
            {isEmpty ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-700 dark:text-slate-300 gap-3 py-12">
                <ShoppingCart size={48} strokeWidth={1} />
                <p className="text-sm font-medium">Cart is empty</p>
                <p className="text-xs text-gray-600 dark:text-slate-400">Search above or scan a barcode to add items</p>
              </div>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-xs font-semibold text-[--text-muted] uppercase tracking-wider border-b border-[--border] bg-slate-50">
                    <th className="py-2 px-3 text-left">Item</th>
                    <th className="py-2 px-2 text-center">Qty</th>
                    <th className="py-2 px-2 text-right">Unit</th>
                    <th className="py-2 px-3 text-right">Total</th>
                    <th className="py-2 px-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {lines?.map((line) => (
                    <CartRow
                      key={line.product_name}
                      line={line}
                      onInc={() => updateQty(line.product_name, 1)}
                      onDec={() => updateQty(line.product_name, -1)}
                      onRemove={() => remove(line.product_name)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Cart toolbar */}
          {!isEmpty && (
            <div className="flex items-center gap-2 px-4 py-2 bg-slate-50 border-t border-[--border] flex-shrink-0">
              <button
                onClick={clear}
                className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 px-2 py-1.5 rounded transition-colors"
              >
                <Trash2 size={13} /> Clear Cart
              </button>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => setShowDiscountDialog(true)}
                  className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-2 py-1.5 rounded transition-colors"
                >
                  <Tag size={13} />
                  {discountType && discountValue ? (
                    <span className="font-medium">
                      {discountType === "%" ? `${discountValue}% off` : `$${discountValue} off`}
                    </span>
                  ) : (
                    "Add Discount"
                  )}
                </button>
                <button
                  onClick={toggleTaxExempt}
                  className={`flex items-center gap-1.5 text-xs px-2 py-1.5 rounded transition-colors ${
                    taxExempt
                      ? "bg-purple-100 text-purple-700 font-medium"
                      : "text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  Tax {taxExempt ? "Exempt ✓" : "Taxable"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT: Balance & Payment ──────────────────────────────────── */}
        <aside className="w-72 flex-shrink-0 flex flex-col border-l border-[--border] bg-white overflow-y-auto">

          {/* Totals */}
          <div className="p-4 border-b border-[--border] space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[--text-muted] mb-3">
              Order Summary
            </h2>
            <div className="flex justify-between text-sm text-[--text-muted]">
              <span>Subtotal</span>
              <span className="font-medium text-[--text-main]">{fmtPrice(String(subtotal))}</span>
            </div>
            {discountAmount > 0 && (
              <div className="flex justify-between text-sm text-blue-600">
                <span>Discount</span>
                <span className="font-medium">−{fmtPrice(String(discountAmount))}</span>
              </div>
            )}
            {!taxExempt && (
              <div className="flex justify-between text-sm text-[--text-muted]">
                <span>Tax (8.5%)</span>
                <span className="font-medium text-[--text-main]">{fmtPrice(String(taxAmount))}</span>
              </div>
            )}
            {taxExempt && (
              <div className="flex justify-between text-xs text-purple-600">
                <span>Tax Exempt</span>
                <span>—</span>
              </div>
            )}
            <div className="flex justify-between text-base font-bold pt-2 border-t border-[--border] text-[--text-main]">
              <span>Total</span>
              <span className="text-emerald-700">{fmtPrice(String(total))}</span>
            </div>
          </div>

          {/* Payment method */}
          <div className="p-4 border-b border-[--border]">
            <p className="text-xs font-semibold uppercase tracking-wider text-[--text-muted] mb-2">
              Payment Method
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {PAYMENT_METHODS.map((m) => (
                <button
                  key={m}
                  onClick={() => setPaymentMethod(m)}
                  className={`flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-all border ${
                    paymentMethod === m
                      ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:border-emerald-300 hover:bg-emerald-50"
                  }`}
                >
                  {PAYMENT_ICONS[m]}
                  {m}
                </button>
              ))}
            </div>
          </div>

          {/* Amount tendered (cash only) */}
          {paymentMethod === "Cash" && (
            <div className="p-4 border-b border-[--border] space-y-3">
              <div>
                <label htmlFor="pos-tendered" className="text-xs font-semibold uppercase tracking-wider text-[--text-muted] block mb-1">
                  Amount Tendered
                </label>
                <input
                  id="pos-tendered"
                  type="number"
                  min="0"
                  step="0.01"
                  value={amountTendered}
                  onChange={(e) => setAmountTendered(e.target.value)}
                  placeholder={fmtPrice(String(Math.ceil(total)))}
                  className="w-full px-3 py-2 text-sm border border-[--border] rounded-md focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-emerald-400 bg-[--bg-primary]"
                />
              </div>
              {amountTendered && parseFloat(amountTendered) >= total && (
                <div className="flex justify-between text-sm font-bold text-emerald-700">
                  <span>Change Due</span>
                  <span>{fmtPrice(String(changeDue))}</span>
                </div>
              )}
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="mx-4 mt-3 flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-800 text-xs p-3 rounded-md">
              <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
              <span>{error}</span>
              <button onClick={() => setError(null)} className="ml-auto flex-shrink-0 hover:text-amber-900">
                <X size={12} />
              </button>
            </div>
          )}

{canCheckout && (
          <div className="p-4 mt-auto">
            <button
              id="pos-checkout-btn"
              onClick={handleCheckout}
              disabled={isEmpty || processing}
              className={`w-full py-3.5 rounded-lg font-bold text-sm transition-all shadow-sm flex items-center justify-center gap-2 ${
                isEmpty || processing
                  ? "bg-slate-200 text-slate-400 cursor-not-allowed"
                  : "bg-emerald-600 text-white hover:bg-emerald-700 active:scale-[0.98]"
              }`}
>
              {processing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Processing…
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} />
                  {isEmpty ? "Add items to checkout" : `Checkout — ${fmtPrice(String(total))}`}
                  <span className="ml-auto text-xs opacity-60 font-normal">F12</span>
                </>
              )}
</button>

            {/* Quick actions */}
            {!isEmpty && canCheckout && (
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                <button
                  onClick={() => void (async () => {
                    if (result) {
                      setShowReceipt(true);
                    }
                  })()}
                  className="flex items-center justify-center gap-1.5 py-1.5 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                >
                  <Printer size={12} /> Print Last
                </button>
                <button
                  onClick={() => router.push("/dashboard/analytics")}
                  className="flex items-center justify-center gap-1.5 py-1.5 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                >
                  <ReceiptText size={12} /> Reports
                </button>
              </div>
)}
            </div>
            )}

{/* Item count */}
            <div className="px-4 pb-3 text-center">
            <p className="text-xs text-[--text-muted]">
              {lines?.length ?? 0} item{lines?.length !== 1 ? "s" : ""} ·{" "}
              {lines?.reduce((a, l) => a + l.quantity, 0) ?? 0} units
            </p>
          </div>
        </aside>
      </div>

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      {showReceipt && result && (
        <ReceiptPrintPreview
          receiptId={result.receipt_id}
          open={showReceipt}
          onClose={handleReceiptClose}
        />
      )}

      {showSplitDialog && (
        <SplitPaymentDialog
          total={total}
          open={showSplitDialog}
          onClose={() => setShowSplitDialog(false)}
          onConfirm={async (splits) => {
            setPayments(splits);
            setShowSplitDialog(false);
            setProcessing(true);
            try {
              await doCheckout("Split");
            } finally {
              setProcessing(false);
            }
          }}
        />
      )}

      {showDiscountDialog && (
        <DiscountDialog
          open={showDiscountDialog}
          onClose={() => setShowDiscountDialog(false)}
          cartSubtotal={subtotal}
          onApply={(type, value) => {
            if (type === "%" || type === "$") {
              usePosStore.getState().setDiscount(type, value);
            }
          }}
        />
      )}
    </div>
  );
}
