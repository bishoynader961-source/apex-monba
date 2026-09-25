"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { CommandPalette } from "@/components/CommandPalette";

export function GlobalHotkeys() {
  const router = useRouter();
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteOpenRef = useRef(false);

  // Keep ref in sync so the keydown handler doesn't close over stale state
  useEffect(() => {
    paletteOpenRef.current = paletteOpen;
  }, [paletteOpen]);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;

      // Ctrl+K / Cmd+K — command palette
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
        return;
      }

      // Esc — close palette if open
      if (e.key === "Escape" && paletteOpenRef.current) {
        setPaletteOpen(false);
        return;
      }

      // Don't fire F-key navigation when typing inside inputs
      const target = e.target as HTMLElement;
      const isTyping =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;
      if (isTyping) return;

      let handled = false;
      switch (e.key) {
        // F1 — POS (cashier shortcut)
        case "F1":
          router.push("/pos");
          handled = true;
          break;
        // F2 — Inventory
        case "F2":
          router.push("/dashboard/inventory");
          handled = true;
          break;
        // F3 — Patients
        case "F3":
          router.push("/patients");
          handled = true;
          break;
        // F4 — Analytics
        case "F4":
          router.push("/dashboard/analytics");
          handled = true;
          break;
        // F5 — Prescribers
        case "F5":
          router.push("/prescribers");
          handled = true;
          break;
        // F6 — Price Codes
        case "F6":
          router.push("/dashboard/price-codes");
          handled = true;
          break;
        // F7 — Quick-SIG builder
        case "F7":
          router.push("/dashboard/quick-sig");
          handled = true;
          break;
        // F8 — Purchase Orders
        case "F8":
          router.push("/dashboard/purchase-orders");
          handled = true;
          break;
        // F12 — Checkout shortcut (POS page handles its own F12; this is a
        // fallback to navigate to POS from any other page)
        case "F12":
          if (!pathname?.startsWith("/pos")) {
            router.push("/pos");
            handled = true;
          }
          break;
      }

      if (handled) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [router, pathname]);

  return (
    <CommandPalette open={paletteOpen} onClose={closePalette} />
  );
}
