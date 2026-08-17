/**
 * Barcode scanner hook (R3) supporting three input modes:
 *   - "wedge"   : keyboard-wedge (rapid keydown burst + Enter) on the whole window.
 *   - "serial"  : serial/scanner devices emitting via a global event bus
 *                 (e.g. `@/lib/scannerBridge`), delivered through `onScan`.
 *   - "manual"  : an explicit input the caller binds (returns a ref + handler).
 *
 * Default mode is "wedge". Scanners emit characters as rapid keydown events
 * followed by Enter; we accumulate characters and reset on a timing gap so typing
 * into focused inputs is not captured.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type ScannerMode = "wedge" | "serial" | "manual";

const GAP_MS = 50;

export interface UseBarcodeScannerOptions {
  mode?: ScannerMode;
  enabled?: boolean;
  onScan?: (code: string) => void;
}

export function useBarcodeScanner(options: UseBarcodeScannerOptions = {}) {
  const { mode = "wedge", enabled = true, onScan } = options;
  const [scan, setScan] = useState<string>("");
  const buffer = useRef<string>("");
  const lastTime = useRef<number>(0);
  const onScanRef = useRef(onScan);
  onScanRef.current = onScan;

  const emit = useCallback((value: string) => {
    buffer.current = "";
    setScan(value);
    onScanRef.current?.(value);
  }, []);

  // Wedge mode: window-wide keydown capture.
  useEffect(() => {
    if (!enabled || mode !== "wedge") return;
    const onKeyDown = (e: KeyboardEvent) => {
      const now = Date.now();
      if (now - lastTime.current > GAP_MS) buffer.current = "";
      lastTime.current = now;

      if (e.key === "Enter") {
        e.preventDefault();
        if (e.currentTarget instanceof HTMLInputElement) e.currentTarget.value = "";
        if (buffer.current) emit(buffer.current);
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        buffer.current += e.key;
      } else if (e.key === "Backspace") {
        buffer.current = buffer.current.slice(0, -1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, mode, emit]);

  // Serial mode: listen on a global scanner bus if present.
  useEffect(() => {
    if (!enabled || mode !== "serial") return;
    const bus = (globalThis as { scannerBus?: EventTarget }).scannerBus;
    if (!bus) return;
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) emit(detail);
    };
    bus.addEventListener("scan", handler as EventListener);
    return () => bus.removeEventListener("scan", handler as EventListener);
  }, [enabled, mode, emit]);

  // Manual mode: explicit imperatively-invoked handler for a bound input.
  const manualSubmit = useCallback(
    (code: string) => {
      if (enabled && code.trim()) emit(code.trim());
    },
    [enabled, emit],
  );

  return { scan, manualSubmit, emit };
}
