"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  ArrowRight,
  LayoutDashboard,
  ShoppingCart,
  Package,
  Users,
  BarChart2,
  Pill,
  ClipboardList,
  Settings,
  FileText,
  Tag,
  Truck,
  AlertCircle,
  Printer,
  X,
} from "lucide-react";
import { searchMedicines } from "@/lib/api/inventory";
import type { ProductRead } from "@/types/contracts";

// ─── Static command index ─────────────────────────────────────────────────────

interface Command {
  id: string;
  label: string;
  description?: string;
  href?: string;
  icon: React.ReactNode;
  category: string;
  keywords?: string;
}

const STATIC_COMMANDS: Command[] = [
  // Navigation
  { id: "nav-dashboard", label: "Dashboard", description: "Home overview & KPIs", href: "/dashboard", icon: <LayoutDashboard size={15} />, category: "Navigate", keywords: "home" },
  { id: "nav-pos", label: "Point of Sale", description: "Ring up sales, process payments", href: "/pos", icon: <ShoppingCart size={15} />, category: "Navigate", keywords: "checkout till register" },
  { id: "nav-inventory", label: "Inventory", description: "Manage medicines & stock", href: "/dashboard/inventory", icon: <Package size={15} />, category: "Navigate", keywords: "stock drugs medicines" },
  { id: "nav-patients", label: "Patients", description: "Patient profiles & history", href: "/patients", icon: <Users size={15} />, category: "Navigate", keywords: "crm" },
  { id: "nav-analytics", label: "Analytics", description: "Sales reports & trends", href: "/dashboard/analytics", icon: <BarChart2 size={15} />, category: "Navigate", keywords: "reports sales revenue" },
  { id: "nav-drugs", label: "Drug Information", description: "NDC lookup & drug file", href: "/dashboard/drugs", icon: <Pill size={15} />, category: "Navigate", keywords: "ndc formulary" },
  { id: "nav-rx", label: "Rx Queue", description: "Prescription workflow", href: "/rx", icon: <ClipboardList size={15} />, category: "Navigate", keywords: "prescription dispense" },
  { id: "nav-vendors", label: "Vendors", description: "Supplier management", href: "/dashboard/vendors", icon: <Truck size={15} />, category: "Navigate", keywords: "suppliers" },
  { id: "nav-receiving", label: "Receiving Log", description: "Shipment history", href: "/dashboard/receiving-log", icon: <Truck size={15} />, category: "Navigate", keywords: "shipments po" },
  { id: "nav-templates", label: "Product Templates", description: "Manage product templates", href: "/dashboard/templates", icon: <FileText size={15} />, category: "Navigate", keywords: "template" },
  { id: "nav-labels", label: "Label Designer", description: "Design & print product labels", href: "/dashboard/label-engine", icon: <Printer size={15} />, category: "Navigate", keywords: "print sticker" },
  { id: "nav-sig", label: "SIG Codes", description: "Prescription sig code library", href: "/dashboard/sig-codes", icon: <Tag size={15} />, category: "Navigate", keywords: "sig directions" },
  { id: "nav-quick-sig", label: "Quick-SIG Builder", description: "Build & save SIG templates", href: "/dashboard/quick-sig", icon: <Tag size={15} />, category: "Navigate", keywords: "sig directions" },
  { id: "nav-expiry", label: "Expiry Alerts", description: "Monitor near-expiry stock", href: "/dashboard/expiry-alerts", icon: <AlertCircle size={15} />, category: "Navigate", keywords: "expire expiry" },
  { id: "nav-settings", label: "Settings", description: "App configuration", href: "/dashboard/settings", icon: <Settings size={15} />, category: "Navigate", keywords: "config" },
  { id: "nav-purchase-orders", label: "Purchase Orders", description: "PO management", href: "/dashboard/purchase-orders", icon: <ClipboardList size={15} />, category: "Navigate", keywords: "po vendor order" },
];

// ─── Fuzzy scorer (simple) ────────────────────────────────────────────────────

function score(item: string, query: string): number {
  const i = item.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return 1;
  if (i === q) return 100;
  if (i.startsWith(q)) return 80;
  if (i.includes(q)) return 60;
  // word match
  const words = i.split(/\s+/);
  if (words.some((w) => w.startsWith(q))) return 50;
  return 0;
}

function rankCommand(cmd: Command, query: string): number {
  return Math.max(
    score(cmd.label, query),
    score(cmd.description ?? "", query),
    score(cmd.keywords ?? "", query),
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const [medicines, setMedicines] = useState<ProductRead[]>([]);
  const [medLoading, setMedLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const focusRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setMedicines([]);
      setActiveIdx(0);
      focusRef.current = setTimeout(() => inputRef.current?.focus(), 50);
    }
    return () => {
      // Cancel pending focus so no timer fires after close/unmount
      if (focusRef.current) clearTimeout(focusRef.current);
    };
  }, [open]);

  // Debounced medicine search
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim() || query.length < 2) {
      setMedicines([]);
      return;
    }
    setMedLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const items = await searchMedicines(query);
        setMedicines(items.slice(0, 5));
      } catch {
        setMedicines([]);
      } finally {
        setMedLoading(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, open]);

  // Build combined result list
  const filteredCommands = query.trim()
    ? STATIC_COMMANDS.filter((c) => rankCommand(c, query) > 0).sort(
        (a, b) => rankCommand(b, query) - rankCommand(a, query),
      )
    : STATIC_COMMANDS.slice(0, 8);

  const medicineCommands: Command[] = medicines.map((m) => ({
    id: `med-${m.id}`,
    label: m.name,
    description: `${m.vendor_name !== "N/A" ? m.vendor_name + " · " : ""}${m.status} · ${m.price}`,
    href: `/dashboard/inventory?search=${encodeURIComponent(m.name)}`,
    icon: <Pill size={15} />,
    category: "Medicine",
  }));

  const allItems = [...filteredCommands, ...medicineCommands];
  const totalItems = allItems.length;

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => (i + 1) % Math.max(1, totalItems));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => (i - 1 + Math.max(1, totalItems)) % Math.max(1, totalItems));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = allItems[activeIdx];
        if (item?.href) {
          router.push(item.href);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeIdx, totalItems, allItems]);

  // Reset active index on query change
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  const handleSelect = useCallback(
    (item: Command) => {
      if (item.href) {
        router.push(item.href);
        onClose();
      }
    },
    [router, onClose],
  );

  if (!open) return null;

  // Group by category
  const groups: Record<string, Command[]> = {};
  for (const item of allItems) {
    if (!groups[item.category]) groups[item.category] = [];
    groups[item.category].push(item);
  }

  let globalIdx = 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Palette modal */}
      <div
        role="dialog"
        aria-modal
        aria-label="Command palette"
        className="fixed left-1/2 top-[15%] z-50 w-full max-w-xl -translate-x-1/2 rounded-xl bg-white shadow-2xl border border-[--border] overflow-hidden"
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[--border]">
          <Search size={16} className="text-gray-600 dark:text-slate-400 flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, medicines, actions…"
            className="flex-1 text-sm text-[--text-main] placeholder:text-slate-400 bg-transparent outline-none"
          />
          {medLoading && (
            <div className="w-3.5 h-3.5 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          )}
          <button onClick={onClose} className="text-gray-600 dark:text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0">
            <X size={15} />
          </button>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto py-1">
          {totalItems === 0 && (
            <p className="text-center text-sm text-gray-600 dark:text-slate-400 py-8">No results for &quot;{query}&quot;</p>
          )}

          {Object.entries(groups).map(([category, items]) => (
            <div key={category}>
              <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-gray-600 dark:text-slate-400">
                {category}
              </div>
              {items.map((item) => {
                const idx = globalIdx++;
                const isActive = idx === activeIdx;
                return (
                  <button
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    onMouseEnter={() => setActiveIdx(idx)}
                    className={`w-full text-left flex items-center gap-3 px-4 py-2.5 transition-colors ${
                      isActive ? "bg-emerald-50" : "hover:bg-slate-50"
                    }`}
                  >
                    <span className={`flex-shrink-0 ${isActive ? "text-emerald-600" : "text-slate-400"}`}>
                      {item.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${isActive ? "text-emerald-700" : "text-[--text-main]"}`}>
                        {item.label}
                      </p>
                      {item.description && (
                        <p className="text-xs text-gray-600 dark:text-slate-400 truncate">{item.description}</p>
                      )}
                    </div>
                    {isActive && <ArrowRight size={13} className="text-emerald-400 flex-shrink-0" />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="border-t border-[--border] px-4 py-2 flex items-center gap-4 text-[10px] text-gray-600 dark:text-slate-400">
          <span><kbd className="bg-slate-100 px-1 rounded text-[10px]">↑↓</kbd> navigate</span>
          <span><kbd className="bg-slate-100 px-1 rounded text-[10px]">↵</kbd> open</span>
          <span><kbd className="bg-slate-100 px-1 rounded text-[10px]">Esc</kbd> close</span>
          <span className="ml-auto">Ctrl+K to toggle</span>
        </div>
      </div>
    </>
  );
}
