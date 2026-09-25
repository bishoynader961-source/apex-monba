"use client";

import { useState, useEffect } from "react";
import LabelCanvas, { type LabelElement } from "@/components/LabelCanvas";
import { useToast } from "@/hooks/useToast";
import { searchMedicines } from "@/lib/api/inventory";
import { saveProductLabel } from "@/lib/api/labelTemplates";
import type { Medicine } from "@/types/contracts";

export default function LabelEnginePreviewPage() {
  const { toast } = useToast();
  const [canvasW, setCanvasW] = useState(400);
  const [canvasH, setCanvasH] = useState(300);
  const [elements, setElements] = useState<LabelElement[]>([]);
  const [tplName, setTplName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"single" | "inventory">("single");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Medicine[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [productName, setProductName] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [searching, setSearching] = useState(false);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let mounted = true;
    let unlisten: (() => void) | null = null;

    const listenForState = async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");

        unlisten = await listen<{
          canvasW: number;
          canvasH: number;
          elements: LabelElement[];
          currentTplId: number | null;
          tplName: string;
        }>("label-preview-state", (event) => {
          if (!mounted) return;
          const { canvasW, canvasH, elements, tplName } = event.payload;
          setCanvasW(canvasW);
          setCanvasH(canvasH);
          setElements(elements);
          setTplName(tplName || "Preview");
          setLoading(false);
        });
      } catch (err) {
        if (mounted) {
          setError("Failed to listen for preview state");
          setLoading(false);
          console.error(err);
        }
      }
    };

    void listenForState();

    const timeout = setTimeout(() => {
      if (mounted) {
        setLoading((prevLoading) => {
          if (prevLoading) setError("Timeout waiting for preview state");
          return false;
        });
      }
    }, 8000);

    return () => {
      mounted = false;
      clearTimeout(timeout);
      if (unlisten) unlisten();
    };
  }, []);

  const doPrint = async (copies: number) => {
    const canvas = document.querySelector<HTMLCanvasElement>('canvas[data-label-canvas="true"]');
    if (!canvas) {
      toast({ title: "Error", message: "No canvas found", variant: "destructive" });
      return;
    }
    setWorking(true);
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const dataUrl = canvas.toDataURL("image/png");
      for (let i = 0; i < Math.max(1, copies); i++) {
        // NOTE: snake_case to match Rust params (Architectural Law #4).
        await invoke("print_label", { image_data: dataUrl, canvas_width: canvasW, canvas_height: canvasH });
      }
      toast({ title: "Success", message: copies > 1 ? `Sent ${copies} labels to printer` : "Print dialog opened" });
    } catch (err) {
      const message = err instanceof Error ? err.message : typeof err === "string" ? err : "Print failed";
      toast({ title: "Error", message, variant: "destructive" });
    } finally {
      setWorking(false);
    }
  };

  const handlePrintSingle = () => void doPrint(1);

  const handleSearch = async (q: string) => {
    setQuery(q);
    setProductId(null);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      setResults(await searchMedicines(q.trim()));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleSaveAndPrint = async () => {
    if (productId === null) {
      toast({ title: "Error", message: "Select a product first.", variant: "destructive" });
      return;
    }
    if (quantity < 1) {
      toast({ title: "Error", message: "Quantity must be at least 1.", variant: "destructive" });
      return;
    }
    setWorking(true);
    try {
      await saveProductLabel(productId, { canvas_width: canvasW, canvas_height: canvasH, elements });
      toast({ title: "Success", message: `Label applied to ${productName || `product #${productId}`}` });
      await doPrint(quantity);
    } catch (err) {
      toast({ title: "Error", message: err instanceof Error ? err.message : "Save & Print failed", variant: "destructive" });
    } finally {
      setWorking(false);
    }
  };

  const handleClose = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("close_label_window");
    } catch {
      window.close();
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col h-screen bg-background dark:bg-[#0a0a1a] text-foreground dark:text-gray-100">
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Loading preview…</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-screen bg-background dark:bg-[#0a0a1a] text-foreground dark:text-gray-100">
        <div className="flex items-center justify-center h-full">
          <div className="text-center p-6">
            <p className="text-red-500 mb-4">{error}</p>
            <button
              onClick={handleClose}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm font-medium"
            >
              Close Window
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background dark:bg-[#0a0a1a] text-foreground dark:text-gray-100">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border dark:border-gray-800 bg-surface dark:bg-[#111] flex-wrap min-h-[48px]">
        <span className="px-2 py-1 text-xs text-muted-foreground">{tplName} · {canvasW}×{canvasH}</span>
        <span className="text-xs text-border dark:text-gray-700 mx-1">|</span>
        <div className="flex rounded border border-border dark:border-gray-700 overflow-hidden text-xs">
          <button onClick={() => setMode("single")} className={`px-2.5 py-1 ${mode === "single" ? "bg-blue-600 text-white" : ""}`}>
            Print Single
          </button>
          <button onClick={() => setMode("inventory")} className={`px-2.5 py-1 ${mode === "inventory" ? "bg-blue-600 text-white" : ""}`}>
            Apply to Inventory Items
          </button>
        </div>
        <span className="text-xs text-border dark:text-gray-700 mx-1">|</span>
        {mode === "single" ? (
          <button
            onClick={handlePrintSingle}
            disabled={working}
            className="px-2.5 py-1 text-xs rounded text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
          >
            {working ? "Printing…" : "Print Single"}
          </button>
        ) : (
          <div className="flex items-center gap-1.5 flex-wrap">
            <input
              value={query}
              onChange={(e) => void handleSearch(e.target.value)}
              placeholder="Search products…"
              className="w-44 px-2 py-1 text-xs border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
            />
            <input
              type="number"
              min={1}
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              title="Quantity"
              className="w-16 px-2 py-1 text-xs border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
            />
            <button
              onClick={() => void handleSaveAndPrint()}
              disabled={working || productId === null}
              className="px-2.5 py-1 text-xs rounded text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
            >
              {working ? "Working…" : "Save & Print"}
            </button>
          </div>
        )}
        <span className="text-xs text-border dark:text-gray-700 mx-1">|</span>
        <button
          onClick={handleClose}
          className="px-2.5 py-1 text-xs rounded text-white bg-red-600 hover:bg-red-700"
        >
          Close
        </button>
      </div>

      {mode === "inventory" && query.trim().length >= 2 && (
        <div className="border-b border-border dark:border-gray-800 bg-surface dark:bg-[#111] max-h-40 overflow-y-auto">
          {searching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!searching && results.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No products match “{query}”.</p>
          )}
          {results.map((m) => (
            <button
              key={m.id}
              onClick={() => { setProductId(m.id); setProductName(m.name); setQuery(m.name); setResults([]); }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/5 flex justify-between gap-2"
            >
              <span className="truncate">{m.name}</span>
              <span className="text-muted-foreground whitespace-nowrap">#{m.id}</span>
            </button>
          ))}
        </div>
      )}
      {mode === "inventory" && productId !== null && (
        <p className="px-3 py-1.5 text-[11px] text-green-600 dark:text-green-400 border-b border-border dark:border-gray-800">
          Target: {productName} (#{productId}) × {quantity}
        </p>
      )}

      <div
        className="flex flex-1 justify-center items-center overflow-auto p-6"
        style={{
          backgroundColor: "#e8eaf0",
          backgroundImage: "radial-gradient(#b9bec9 1px, transparent 1px)",
          backgroundSize: "16px 16px",
        }}
      >
        <LabelCanvas
          width={canvasW}
          height={canvasH}
          elements={elements}
          selectedId={null}
          onSelect={() => {}}
          onMove={() => {}}
          onResize={() => {}}
        />
      </div>
    </div>
  );
}
