"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import LabelCanvas, { type LabelElement, type LabelElementType } from "@/components/LabelCanvas";
import LabelPropertiesPanel from "@/components/LabelPropertiesPanel";
import type JsBarcodeType from "jsbarcode";
import type QRCodeType from "qrcode";

// Thumbnail rendering is the only consumer here; load the barcode/QR engines
// on demand (Phase 3 diagnostics: performance / lazy loading).
let _jsbarcode: typeof JsBarcodeType | null = null;
let _qrcode: typeof QRCodeType | null = null;
async function loadJsBarcode(): Promise<typeof JsBarcodeType> {
  if (!_jsbarcode) _jsbarcode = (await import("jsbarcode")).default;
  return _jsbarcode;
}
async function loadQrCode(): Promise<typeof QRCodeType> {
  if (!_qrcode) _qrcode = (await import("qrcode")).default;
  return _qrcode;
}
import {
  listLabelTemplates,
  createLabelTemplate,
  updateLabelTemplate,
  deleteLabelTemplate,
  saveProductLabel,
  getProductLabel,
  type LabelTemplateRead,
} from "@/lib/api/labelTemplates";
import { useToast } from "@/hooks/useToast";

function logError(context: string, err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  console.error(`[LabelEngine] ${context}:`, msg);
}

function cloneElements(els: LabelElement[]): LabelElement[] {
  return JSON.parse(JSON.stringify(els)) as LabelElement[];
}

/** Miniature canvas preview for template thumbnails */
function TemplateThumbnail({
  width,
  height,
  elements,
  bg = "#ffffff",
}: {
  width: number;
  height: number;
  elements: LabelElement[];
  bg?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const qrCache = useRef<Map<string, string>>(new Map());
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());

  const draw = useCallback(async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const scale = Math.min(160 / width, 100 / height);
    const drawW = Math.round(width * scale);
    const drawH = Math.round(height * scale);

    canvas.width = drawW;
    canvas.height = drawH;

    ctx.scale(scale, scale);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    for (const elem of elements) {
      ctx.save();

      if (elem.type === "text") {
        const text = String(elem.props.text ?? "Text");
        const font = String(elem.props.font ?? "Arial");
        const fontSize = Number(elem.props.font_size ?? 16);
        const color = String(elem.props.color ?? "#000000");
        const bold = Boolean(elem.props.bold);
        const italic = Boolean(elem.props.italic);
        const align = String(elem.props.align ?? "left") as "left" | "center" | "right";
        ctx.font = `${italic ? "italic " : ""}${bold ? "bold " : ""}${fontSize}px ${font}, sans-serif`;
        ctx.fillStyle = color;
        ctx.textBaseline = "middle";
        ctx.textAlign = align;
        const tx = align === "center" ? elem.x + elem.width / 2 : align === "right" ? elem.x + elem.width : elem.x;
        const ty = elem.y + elem.height / 2;
        ctx.fillText(text, tx, ty, elem.width);
      } else if (elem.type === "shape") {
        const shape = String(elem.props.shape ?? "rectangle");
        const fill = String(elem.props.fill_color ?? "#cccccc");
        const stroke = String(elem.props.border_color ?? "#000000");
        const lineW = Number(elem.props.border_width ?? 2);
        ctx.fillStyle = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineW;
        if (shape === "ellipse") {
          ctx.beginPath();
          ctx.ellipse(elem.x + elem.width / 2, elem.y + elem.height / 2, elem.width / 2, elem.height / 2, 0, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        } else if (shape === "line") {
          ctx.beginPath();
          ctx.moveTo(elem.x, elem.y + elem.height / 2);
          ctx.lineTo(elem.x + elem.width, elem.y + elem.height / 2);
          ctx.stroke();
        } else {
          ctx.fillRect(elem.x, elem.y, elem.width, elem.height);
          ctx.strokeRect(elem.x, elem.y, elem.width, elem.height);
        }
      } else if (elem.type === "barcode") {
        const data = String(elem.props.data ?? "");
        const format = String(elem.props.barcode_format ?? "CODE128");
        try {
          if (!data) throw new Error("empty");
          const JsBarcode = await loadJsBarcode();
          const tempCanvas = document.createElement("canvas");
          JsBarcode(tempCanvas, data, { format, width: 1, height: 20, displayValue: false, margin: 0 });
          ctx.drawImage(tempCanvas, elem.x, elem.y, elem.width, elem.height);
        } catch {
          ctx.fillStyle = "#ff0000";
          ctx.font = "6px Arial";
          ctx.fillText("[BC]", elem.x, elem.y + 8);
        }
      } else if (elem.type === "qr") {
        const data = String(elem.props.data ?? "");
        const cacheKey = `${data}_${elem.width}_${elem.height}`;
        if (!qrCache.current.has(cacheKey)) {
          try {
            const QRCode = await loadQrCode();
            const dataUrl = await QRCode.toDataURL(data || " ", { width: 32, margin: 0, errorCorrectionLevel: "M" });
            qrCache.current.set(cacheKey, dataUrl);
          } catch {
            qrCache.current.set(cacheKey, "");
          }
        }
        const dataUrl = qrCache.current.get(cacheKey);
        if (dataUrl) {
          let img = imgCache.current.get(cacheKey);
          if (!img) {
            img = new Image();
            img.src = dataUrl;
            imgCache.current.set(cacheKey, img);
          }
          if (img.complete && img.naturalWidth > 0) {
            ctx.drawImage(img, elem.x, elem.y, elem.width, elem.height);
          }
        }
      } else if (elem.type === "image") {
        const src = String(elem.props.src ?? "");
        if (src) {
          let img = imgCache.current.get(src);
          if (!img) {
            img = new Image();
            img.src = src;
            imgCache.current.set(src, img);
          }
          if (img.complete && img.naturalWidth > 0) {
            ctx.drawImage(img, elem.x, elem.y, elem.width, elem.height);
          } else {
            ctx.fillStyle = "#e5e7eb";
            ctx.fillRect(elem.x, elem.y, elem.width, elem.height);
          }
        }
      }

      ctx.restore();
    }
  }, [width, height, elements, bg]);

  useEffect(() => { void draw(); }, [draw]);

  return <canvas ref={canvasRef} className="border border-gray-300 dark:border-gray-600 rounded" width={160} height={100} />;
}

async function openLabelWindow(
  canvasW: number,
  canvasH: number,
  elements: LabelElement[],
  currentTplId: number | null,
  tplName: string,
) {
  const { emit } = await import("@tauri-apps/api/event");
  const { invoke } = await import("@tauri-apps/api/core");
  await emit("label-preview-state", { canvasW, canvasH, elements, currentTplId, tplName });
  await invoke("open_label_window");
}

const ELEMENT_DEFS: Array<{ type: LabelElementType; icon: string; label: string; hint: string }> = [
  { type: "text", icon: "📝", label: "Text", hint: "Titles, prices, dates" },
  { type: "shape", icon: "▭", label: "Shape", hint: "Rectangle / line" },
  { type: "barcode", icon: "▦", label: "Barcode", hint: "CODE128 & more" },
  { type: "qr", icon: "⊞", label: "QR Code", hint: "Links, IDs" },
  { type: "image", icon: "🖼", label: "Image", hint: "Logo / graphic" },
];

export default function LabelEnginePage() {
  const { toast } = useToast();
  const [canvasW, setCanvasW] = useState(400);
  const [canvasH, setCanvasH] = useState(300);
  const [canvasBg, setCanvasBg] = useState("#ffffff");
  const [elements, setElementsState] = useState<LabelElement[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [templates, setTemplates] = useState<LabelTemplateRead[]>([]);
  const [currentTplId, setCurrentTplId] = useState<number | null>(null);
  const [tplName, setTplName] = useState("");
  const [tplNameError, setTplNameError] = useState("");
  const [productId, setProductId] = useState("");
  const [leftTab, setLeftTab] = useState<"elements" | "templates">("elements");
  const [zoom, setZoom] = useState(1);
  const [snapToGrid, setSnapToGrid] = useState(false);
  const [gridSize, setGridSize] = useState(5);
  const [dirty, setDirty] = useState(false);
  const [past, setPast] = useState<LabelElement[][]>([]);
  const [future, setFuture] = useState<LabelElement[][]>([]);

  const elementsRef = useRef<LabelElement[]>([]);
  const pendingSnapshot = useRef<LabelElement[] | null>(null);

  // Deep-link support: /dashboard/label-engine?productId=123 (from Inventory "Generate Label")
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = new URLSearchParams(window.location.search).get("productId");
    if (raw && /^\d+$/.test(raw)) setProductId(raw);
  }, []);

  const setElements = useCallback((next: LabelElement[]) => {
    elementsRef.current = next;
    setElementsState(next);
    setDirty(true);
  }, []);

  const pushPast = useCallback((snapshot: LabelElement[]) => {
    setPast((prev) => [...prev.slice(-49), snapshot]);
    setFuture([]);
  }, []);

  /** Commit a pending drag snapshot once per gesture. */
  const commitPending = useCallback(() => {
    if (pendingSnapshot.current) {
      pushPast(pendingSnapshot.current);
      pendingSnapshot.current = null;
    }
  }, [pushPast]);

  const beginGesture = useCallback(() => {
    if (!pendingSnapshot.current) {
      pendingSnapshot.current = cloneElements(elementsRef.current);
    }
  }, []);

  /** Apply a one-shot change with undo support. */
  const applyChange = useCallback(
    (updater: (prev: LabelElement[]) => LabelElement[]) => {
      pendingSnapshot.current = null;
      pushPast(cloneElements(elementsRef.current));
      setElements(updater(elementsRef.current));
    },
    [pushPast, setElements]
  );

  const loadTemplates = useCallback(async () => {
    try {
      setTemplates(await listLabelTemplates());
    } catch (err) {
      logError("loadTemplates", err);
    }
  }, []);

  useEffect(() => { void loadTemplates(); }, [loadTemplates]);

  const selectedId = selectedIds.length > 0 ? selectedIds[selectedIds.length - 1] : null;
  const selectedElem = elements.find((e) => e.id === selectedId) ?? null;

  // ── Element ops ──────────────────────────────────────────────
  const addElement = useCallback(
    (type: LabelElementType) => {
      const id = crypto.randomUUID().slice(0, 8);
      const defaults: Record<LabelElementType, { width: number; height: number; props: Record<string, unknown> }> = {
        text: { width: 150, height: 30, props: { text: "Sample Text", font: "Arial", font_size: 16, color: "#000000", align: "left" } },
        shape: { width: 100, height: 100, props: { shape: "rectangle", fill_color: "#cccccc", border_color: "#000000", border_width: 2, border_radius: 0 } },
        barcode: { width: 200, height: 60, props: { data: "SAMPLE-12345", show_text: true, barcode_format: "CODE128", barcodeMode: "Manual" } },
        qr: { width: 100, height: 100, props: { data: "https://example.com", fill_color: "#000000", back_color: "#ffffff", ec_level: "M" } },
        image: { width: 120, height: 80, props: { src: "" } },
      };
      const d = defaults[type];
      const elem: LabelElement = { id, type, x: 20, y: 20, width: d.width, height: d.height, props: d.props };
      pendingSnapshot.current = null;
      pushPast(cloneElements(elementsRef.current));
      setElements([...elementsRef.current, elem]);
      setSelectedIds([id]);
    },
    [pushPast, setElements]
  );

  const updateElementProps = useCallback(
    (id: string, props: Record<string, unknown>) => {
      applyChange((prev) => prev.map((e) => (e.id === id ? { ...e, props } : e)));
    },
    [applyChange]
  );

  const updateGeometry = useCallback(
    (id: string, patch: { x?: number; y?: number; width?: number; height?: number }) => {
      applyChange((prev) =>
        prev.map((e) =>
          e.id === id
            ? {
                ...e,
                x: patch.x ?? e.x,
                y: patch.y ?? e.y,
                width: patch.width ?? e.width,
                height: patch.height ?? e.height,
              }
            : e
        )
      );
    },
    [applyChange]
  );

  const deleteSelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    const ids = new Set(selectedIds);
    applyChange((prev) => prev.filter((e) => !ids.has(e.id)));
    setSelectedIds([]);
    toast({ title: "Deleted", message: `${ids.size} element${ids.size > 1 ? "s" : ""} removed` });
  }, [selectedIds, applyChange, toast]);

  const deleteOne = useCallback(
    (id: string) => {
      applyChange((prev) => prev.filter((e) => e.id !== id));
      setSelectedIds((prev) => prev.filter((s) => s !== id));
    },
    [applyChange]
  );

  const duplicateSelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    const ids = new Set(selectedIds);
    const copies: LabelElement[] = [];
    for (const e of elementsRef.current) {
      if (!ids.has(e.id)) continue;
      copies.push({
        ...e,
        id: crypto.randomUUID().slice(0, 8),
        x: Math.min(e.x + 10, Math.max(0, canvasW - e.width)),
        y: Math.min(e.y + 10, Math.max(0, canvasH - e.height)),
        props: { ...e.props },
      });
    }
    if (copies.length === 0) return;
    pendingSnapshot.current = null;
    pushPast(cloneElements(elementsRef.current));
    setElements([...elementsRef.current, ...copies]);
    setSelectedIds(copies.map((c) => c.id));
  }, [selectedIds, canvasW, canvasH, pushPast, setElements]);

  const moveElement = useCallback(
    (id: string, x: number, y: number) => {
      commitPending();
      setElements(elementsRef.current.map((e) => (e.id === id ? { ...e, x, y } : e)));
    },
    [commitPending, setElements]
  );

  const moveMany = useCallback(
    (moves: Array<{ id: string; x: number; y: number }>) => {
      commitPending();
      const byId = new Map(moves.map((m) => [m.id, m]));
      setElements(elementsRef.current.map((e) => {
        const m = byId.get(e.id);
        return m ? { ...e, x: m.x, y: m.y } : e;
      }));
    },
    [commitPending, setElements]
  );

  const resizeElement = useCallback(
    (id: string, w: number, h: number) => {
      commitPending();
      setElements(elementsRef.current.map((e) => (e.id === id ? { ...e, width: w, height: h } : e)));
    },
    [commitPending, setElements]
  );

  const handleSelect = useCallback(
    (id: string | null, additive?: boolean) => {
      if (id === null) {
        setSelectedIds([]);
        return;
      }
      if (additive) {
        setSelectedIds((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
      } else {
        setSelectedIds([id]);
      }
    },
    []
  );

  const nudge = useCallback(
    (dx: number, dy: number) => {
      if (selectedIds.length === 0) return;
      const ids = new Set(selectedIds);
      applyChange((prev) =>
        prev.map((e) => (ids.has(e.id) ? { ...e, x: Math.max(0, e.x + dx), y: Math.max(0, e.y + dy) } : e))
      );
    },
    [selectedIds, applyChange]
  );

  const undo = useCallback(() => {
    pendingSnapshot.current = null;
    setPast((prevPast) => {
      if (prevPast.length === 0) return prevPast;
      const prev = prevPast[prevPast.length - 1];
      setFuture((prevFuture) => [cloneElements(elementsRef.current), ...prevFuture].slice(0, 50));
      setElements(prev);
      setSelectedIds([]);
      return prevPast.slice(0, -1);
    });
  }, [setElements]);

  const redo = useCallback(() => {
    pendingSnapshot.current = null;
    setFuture((prevFuture) => {
      if (prevFuture.length === 0) return prevFuture;
      const [next, ...rest] = prevFuture;
      setPast((prevPast) => [...prevPast.slice(-49), cloneElements(elementsRef.current)]);
      setElements(next);
      setSelectedIds([]);
      return rest;
    });
  }, [setElements]);

  // ── Keyboard shortcuts ───────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || t?.isContentEditable) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
        e.preventDefault();
        redo();
      } else if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        duplicateSelected();
      } else if (mod && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setSelectedIds(elementsRef.current.map((el) => el.id));
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteSelected();
      } else if (e.key.startsWith("Arrow")) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        if (e.key === "ArrowLeft") nudge(-step, 0);
        else if (e.key === "ArrowRight") nudge(step, 0);
        else if (e.key === "ArrowUp") nudge(0, -step);
        else if (e.key === "ArrowDown") nudge(0, step);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, duplicateSelected, deleteSelected, nudge]);

  // ── Template ops ─────────────────────────────────────────────
  const confirmDiscard = useCallback(() => {
    if (!dirty) return true;
    return window.confirm("You have unsaved changes. Discard them and load anyway?");
  }, [dirty]);

  const handleSaveTemplate = useCallback(async () => {
    if (!tplName.trim()) {
      setTplNameError("Enter a template name before saving.");
      toast({ title: "Error", message: "Enter a template name before saving.", variant: "destructive" });
      return;
    }
    setTplNameError("");
    try {
      if (currentTplId) {
        await updateLabelTemplate(currentTplId, { name: tplName.trim(), canvas_width: canvasW, canvas_height: canvasH, elements: elementsRef.current });
      } else {
        const created = await createLabelTemplate({ name: tplName.trim(), canvas_width: canvasW, canvas_height: canvasH, elements: elementsRef.current });
        setCurrentTplId(created.id);
      }
      await loadTemplates();
      setDirty(false);
      toast({ title: "Success", message: `Template "${tplName.trim()}" saved` });
    } catch (err) {
      logError("handleSaveTemplate", err);
      toast({ title: "Error", message: err instanceof Error ? err.message : "Save failed", variant: "destructive" });
    }
  }, [tplName, currentTplId, canvasW, canvasH, loadTemplates, toast]);

  const handleLoadTemplate = useCallback(
    (tpl: LabelTemplateRead) => {
      if (!confirmDiscard()) return;
      pendingSnapshot.current = null;
      pushPast(cloneElements(elementsRef.current));
      setCurrentTplId(tpl.id);
      setTplName(tpl.name);
      setTplNameError("");
      setCanvasW(tpl.canvas_width);
      setCanvasH(tpl.canvas_height);
      setElements([...tpl.elements]);
      setSelectedIds([]);
      setDirty(false);
    },
    [confirmDiscard, pushPast, setElements]
  );

  const handleDeleteTemplate = useCallback(
    async (id: number) => {
      try {
        await deleteLabelTemplate(id);
        if (currentTplId === id) {
          setCurrentTplId(null);
          setTplName("");
        }
        await loadTemplates();
        toast({ title: "Success", message: "Template deleted" });
      } catch (err) {
        logError("handleDeleteTemplate", err);
        toast({ title: "Error", message: err instanceof Error ? err.message : "Delete failed", variant: "destructive" });
      }
    },
    [currentTplId, loadTemplates, toast]
  );

  const handleNewTemplate = useCallback(() => {
    if (!confirmDiscard()) return;
    pendingSnapshot.current = null;
    pushPast(cloneElements(elementsRef.current));
    setCurrentTplId(null);
    setTplName("");
    setTplNameError("");
    setElements([]);
    setSelectedIds([]);
    setDirty(false);
  }, [confirmDiscard, pushPast, setElements]);

  // ── Product label ops ────────────────────────────────────────
  const handleSaveProductLabel = useCallback(async () => {
    if (!productId.trim()) {
      toast({ title: "Error", message: "Enter a Product ID first.", variant: "destructive" });
      return;
    }
    const pid = parseInt(productId.trim(), 10);
    if (Number.isNaN(pid)) {
      toast({ title: "Error", message: "Product ID must be numeric.", variant: "destructive" });
      return;
    }
    try {
      await saveProductLabel(pid, { canvas_width: canvasW, canvas_height: canvasH, elements: elementsRef.current });
      toast({ title: "Success", message: `Label saved for product #${pid}` });
    } catch (err) {
      logError("handleSaveProductLabel", err);
      toast({ title: "Error", message: err instanceof Error ? err.message : "Save failed", variant: "destructive" });
    }
  }, [productId, canvasW, canvasH, toast]);

  const handleLoadProductLabel = useCallback(async () => {
    if (!productId.trim()) {
      toast({ title: "Error", message: "Enter a Product ID first.", variant: "destructive" });
      return;
    }
    const pid = parseInt(productId.trim(), 10);
    if (Number.isNaN(pid)) {
      toast({ title: "Error", message: "Product ID must be numeric.", variant: "destructive" });
      return;
    }
    if (!confirmDiscard()) return;
    try {
      const pl = await getProductLabel(pid);
      if (pl) {
        pendingSnapshot.current = null;
        pushPast(cloneElements(elementsRef.current));
        setCanvasW(pl.canvas_width);
        setCanvasH(pl.canvas_height);
        setElements([...pl.elements]);
        setSelectedIds([]);
        setDirty(false);
        toast({ title: "Success", message: `Loaded label for product #${pid}` });
      } else {
        toast({ title: "Info", message: `No label saved for product #${pid}` });
      }
    } catch (err) {
      logError("handleLoadProductLabel", err);
      toast({ title: "Error", message: err instanceof Error ? err.message : "Load failed", variant: "destructive" });
    }
  }, [productId, confirmDiscard, pushPast, setElements, toast]);

  // ── Output ops ───────────────────────────────────────────────
  const handleExportPNG = useCallback(async () => {
    if (elementsRef.current.length === 0) {
      toast({ title: "Error", message: "Add elements before exporting", variant: "destructive" });
      return;
    }
    const canvas = document.querySelector<HTMLCanvasElement>('canvas[data-label-canvas="true"]');
    if (!canvas) {
      logError("handleExportPNG", "No canvas element found");
      toast({ title: "Error", message: "No canvas found", variant: "destructive" });
      return;
    }
    try {
      const dataUrl = canvas.toDataURL("image/png");
      try {
        const { save } = await import("@tauri-apps/plugin-dialog");
        const { writeFile } = await import("@tauri-apps/plugin-fs");
        const filePath = await save({
          filters: [{ name: "Image", extensions: ["png"] }],
          defaultPath: `label-${tplName.trim() || "export"}.png`,
        });
        if (!filePath) return;
        const base64Data = dataUrl.replace(/^data:image\/png;base64,/, "");
        const binaryString = window.atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);
        await writeFile(filePath, bytes);
        toast({ title: "Success", message: "PNG exported" });
      } catch {
        const link = document.createElement("a");
        link.download = `label-${tplName.trim() || "export"}.png`;
        link.href = dataUrl;
        link.click();
        toast({ title: "Success", message: "PNG exported" });
      }
    } catch (err) {
      logError("handleExportPNG", err);
      toast({ title: "Error", message: err instanceof Error ? err.message : "Export failed", variant: "destructive" });
    }
  }, [tplName, toast]);

  const handlePrint = useCallback(async () => {
    if (elementsRef.current.length === 0) {
      toast({ title: "Error", message: "Add elements before printing", variant: "destructive" });
      return;
    }
    const canvas = document.querySelector<HTMLCanvasElement>('canvas[data-label-canvas="true"]');
    if (!canvas) {
      toast({ title: "Error", message: "No canvas found", variant: "destructive" });
      return;
    }
    const dataUrl = canvas.toDataURL("image/png");
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      // NOTE: snake_case to match Rust params (Architectural Law #4).
      await invoke("print_label", { image_data: dataUrl, canvas_width: canvas.width, canvas_height: canvas.height });
      toast({ title: "Success", message: "Print dialog opened" });
    } catch (err) {
      logError("handlePrint", err);
      const message = err instanceof Error ? err.message : typeof err === "string" ? err : "Print failed";
      // Surface the ShellExecuteW error code (returned by the Rust command) when present.
      toast({ title: "Error", message, variant: "destructive" });
      try {
        const iframe = document.createElement("iframe");
        iframe.style.display = "none";
        document.body.appendChild(iframe);
        const doc = iframe.contentWindow?.document;
        if (doc) {
          doc.open();
          doc.write(`<html><head><title>Print Label</title></head><body style="margin:0;display:flex;justify-content:center;align-items:center;"><img src="${dataUrl}" onload="window.print();" /></body></html>`);
          doc.close();
          setTimeout(() => { if (document.body.contains(iframe)) document.body.removeChild(iframe); }, 10000);
        }
      } catch (fallbackErr) {
        logError("handlePrint fallback", fallbackErr);
      }
    }
  }, [toast]);

  const handlePreview = useCallback(async () => {
    try {
      await openLabelWindow(canvasW, canvasH, elementsRef.current, currentTplId, tplName);
    } catch (err) {
      logError("handlePreview", err);
      toast({ title: "Error", message: err instanceof Error ? err.message : "Could not open preview", variant: "destructive" });
    }
  }, [canvasW, canvasH, currentTplId, tplName, toast]);

  const zoomIn = useCallback(() => setZoom((z) => Math.min(3, Math.round((z + 0.1) * 10) / 10)), []);
  const zoomOut = useCallback(() => setZoom((z) => Math.max(0.25, Math.round((z - 0.1) * 10) / 10)), []);

  return (
    <div className="flex flex-col h-screen bg-background dark:bg-[#0a0a1a] text-foreground dark:text-gray-100">
      {/* ── Header bar ── */}
      <header className="flex items-center gap-3 px-3 py-2 border-b border-border dark:border-gray-800 bg-surface dark:bg-[#111] flex-wrap">
        <div className="flex items-center gap-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="page-field-1">W:</label>
          <input id="page-field-1"
            type="number"
            min={50}
            value={canvasW}
            onChange={(e) => { setCanvasW(parseInt(e.target.value) || 400); setDirty(true); }}
            className="w-16 px-2 py-1 text-xs border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
          />
          <label className="text-xs text-muted-foreground" htmlFor="page-field-2">H:</label>
          <input id="page-field-2"
            type="number"
            min={50}
            value={canvasH}
            onChange={(e) => { setCanvasH(parseInt(e.target.value) || 300); setDirty(true); }}
            className="w-16 px-2 py-1 text-xs border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
          />
          <div className="flex items-center gap-1 ml-1">
            <button onClick={zoomOut} title="Zoom out" className="px-2 py-1 text-xs rounded border border-border dark:border-gray-700 hover:bg-white/5">−</button>
            <span className="text-xs w-11 text-center">{Math.round(zoom * 100)}%</span>
            <button onClick={zoomIn} title="Zoom in" className="px-2 py-1 text-xs rounded border border-border dark:border-gray-700 hover:bg-white/5">+</button>
          </div>
        </div>

        <div className="flex-1 min-w-[140px] max-w-[280px]">
          <input
            value={tplName}
            onChange={(e) => { setTplName(e.target.value); setTplNameError(""); setDirty(true); }}
            placeholder="Template name…"
            aria-label="Template name"
            className={`w-full px-2 py-1 text-xs border rounded bg-background dark:bg-[#1a1a2e] focus:outline-none focus:ring-1 focus:ring-primary ${tplNameError ? "border-red-500" : "border-border dark:border-gray-700"}`}
          />
          {tplNameError && <p className="text-[10px] text-red-500 mt-0.5">{tplNameError}</p>}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <button onClick={undo} disabled={past.length === 0} title="Undo (Ctrl+Z)" className="px-2 py-1 text-xs rounded border border-border dark:border-gray-700 hover:bg-white/5 disabled:opacity-40">↩ Undo</button>
          <button onClick={redo} disabled={future.length === 0} title="Redo (Ctrl+Y)" className="px-2 py-1 text-xs rounded border border-border dark:border-gray-700 hover:bg-white/5 disabled:opacity-40">↪ Redo</button>
        </div>

        <HeaderSep />

        <div className="flex items-center gap-1.5">
          <button onClick={() => void handleSaveTemplate()} className="px-2.5 py-1 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white">Save Template</button>
          <button onClick={handleNewTemplate} className="px-2.5 py-1 text-xs rounded border border-border dark:border-gray-600 hover:bg-white/5">New</button>
        </div>

        <HeaderSep />

        <div className="flex items-center gap-1.5">
          <input
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder="Product ID"
            aria-label="Product ID"
            className="w-24 px-2 py-1 text-xs border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
          />
          <button onClick={() => void handleSaveProductLabel()} className="px-2 py-1 text-xs rounded border border-border dark:border-gray-600 hover:bg-white/5">Save</button>
          <button onClick={() => void handleLoadProductLabel()} className="px-2 py-1 text-xs rounded border border-border dark:border-gray-600 hover:bg-white/5">Load</button>
        </div>

        <HeaderSep />

        <div className="flex items-center gap-1.5">
          <button onClick={() => void handleExportPNG()} className="px-2.5 py-1 text-xs rounded border border-border dark:border-gray-600 hover:bg-white/5">Export PNG</button>
          <button onClick={() => void handlePrint()} className="px-2.5 py-1 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white">Print</button>
          <button onClick={() => void handlePreview()} className="px-2.5 py-1 text-xs rounded border border-blue-600 text-blue-600 dark:text-blue-400 hover:bg-blue-600/10">Preview &amp; Print</button>
        </div>

        {selectedIds.length > 0 && (
          <>
            <HeaderSep />
            <button onClick={deleteSelected} title="Delete selected (Del)" className="px-2.5 py-1 text-xs rounded bg-red-600 hover:bg-red-700 text-white">
              🗑 Delete Selected{selectedIds.length > 1 ? ` (${selectedIds.length})` : ""}
            </button>
          </>
        )}
      </header>

      {/* ── Main 3-panel area ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <aside className="w-52 shrink-0 border-r border-border dark:border-gray-800 bg-surface dark:bg-[#111] flex flex-col overflow-hidden">
          <div className="flex text-xs border-b border-border dark:border-gray-800">
            <button
              onClick={() => setLeftTab("elements")}
              className={`flex-1 px-2 py-2 font-medium ${leftTab === "elements" ? "bg-white/10 text-foreground" : "text-muted-foreground hover:bg-white/5"}`}
            >
              Elements
            </button>
            <button
              onClick={() => setLeftTab("templates")}
              className={`flex-1 px-2 py-2 font-medium ${leftTab === "templates" ? "bg-white/10 text-foreground" : "text-muted-foreground hover:bg-white/5"}`}
            >
              Templates
            </button>
          </div>

          {leftTab === "elements" ? (
            <div className="p-2 space-y-2 overflow-y-auto">
              {ELEMENT_DEFS.map((d) => (
                <button
                  key={d.type}
                  onClick={() => addElement(d.type)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-white dark:bg-[#1a1a2e] border border-border dark:border-gray-700 text-left shadow-sm hover:shadow-md hover:border-blue-500 transition-all"
                >
                  <span className="text-xl leading-none">{d.icon}</span>
                  <span>
                    <span className="block text-xs font-semibold">{d.label}</span>
                    <span className="block text-[10px] text-muted-foreground">{d.hint}</span>
                  </span>
                </button>
              ))}
              <p className="text-[10px] text-muted-foreground px-1 pt-1">Shift+Click to multi-select. Ctrl+Z / Ctrl+Y for undo/redo.</p>
            </div>
          ) : (
            <div className="flex flex-col flex-1 overflow-hidden">
              <div className="flex-1 overflow-y-auto p-2 space-y-2">
                {templates.length === 0 && (
                  <p className="text-[11px] text-muted-foreground px-1">No saved templates yet.</p>
                )}
                {templates.map((tpl) => (
                  <div
                    key={tpl.id}
                    className={`group flex flex-col gap-1 px-2 py-2 rounded cursor-pointer hover:bg-white/5 dark:hover:bg-white/10 ${currentTplId === tpl.id ? "bg-blue-600/10 ring-1 ring-blue-600/40" : ""}`}
                    onClick={() => handleLoadTemplate(tpl)}
                  >
                    <TemplateThumbnail width={tpl.canvas_width} height={tpl.canvas_height} elements={tpl.elements} />
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="truncate flex-1" title={tpl.name}>
                        {tpl.is_default ? "★ " : ""}{tpl.name}
                      </span>
                      <span className="text-muted-foreground whitespace-nowrap">{tpl.elements.length} els</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); void handleDeleteTemplate(tpl.id); }}
                      title="Delete template"
                      className="text-xs text-red-500 hover:text-red-400 px-1 opacity-0 group-hover:opacity-100 transition-opacity self-end -mr-1"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <div className="p-2 border-t border-border dark:border-gray-800">
                <button onClick={() => void handleSaveTemplate()} className="w-full px-2 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white">
                  Save as Template
                </button>
              </div>
            </div>
          )}
        </aside>

        {/* Center canvas with dot-grid */}
        <div
          className="flex flex-1 justify-center items-start overflow-auto p-8"
          style={{
            backgroundColor: "#e8eaf0",
            backgroundImage: "radial-gradient(#b9bec9 1px, transparent 1px)",
            backgroundSize: "16px 16px",
          }}
          onWheel={(e) => {
            if (e.ctrlKey) {
              e.preventDefault();
              const delta = e.deltaY > 0 ? -0.1 : 0.1;
              setZoom((z) => Math.min(3, Math.max(0.25, Math.round((z + delta) * 10) / 10)));
            }
          }}
        >
          <LabelCanvas
            width={canvasW}
            height={canvasH}
            elements={elements}
            selectedId={selectedId}
            selectedIds={selectedIds}
            onSelect={handleSelect}
            onMove={moveElement}
            onMoveMany={moveMany}
            onResize={resizeElement}
            onDragStart={beginGesture}
            background={canvasBg}
            zoom={zoom}
            snapToGrid={snapToGrid}
            gridSize={gridSize}
          />
        </div>

        {/* Right properties panel */}
        <LabelPropertiesPanel
          key={selectedId ?? "none"}
          element={selectedElem}
          selectedCount={selectedIds.length}
          canvasWidth={canvasW}
          canvasHeight={canvasH}
          canvasBg={canvasBg}
          onCanvasChange={(patch) => {
            if (patch.width !== undefined) setCanvasW(patch.width);
            if (patch.height !== undefined) setCanvasH(patch.height);
            if (patch.background !== undefined) setCanvasBg(patch.background);
            setDirty(true);
          }}
          onChange={updateElementProps}
          onGeometryChange={updateGeometry}
          onDelete={deleteOne}
        />
      </div>

      {/* ── Bottom status bar ── */}
      <footer className="flex items-center gap-4 px-3 py-1.5 border-t border-border dark:border-gray-800 bg-surface dark:bg-[#111] text-[11px] text-muted-foreground">
        <span>W: {canvasW} H: {canvasH} px</span>
        <span className="flex-1 text-center">
          {elements.length} element{elements.length === 1 ? "" : "s"}
          {selectedIds.length > 0 && ` · ${selectedIds.length} selected`}
          {dirty && " · unsaved"}
        </span>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={snapToGrid} onChange={(e) => setSnapToGrid(e.target.checked)} className="w-3.5 h-3.5" />
          Snap
        </label>
        {snapToGrid && (
          <input
            type="number"
            min={1}
            max={50}
            value={gridSize}
            onChange={(e) => setGridSize(Math.max(1, parseInt(e.target.value) || 5))}
            title="Grid size (px)"
            className="w-12 px-1 py-0.5 text-[11px] border border-border dark:border-gray-700 rounded bg-background dark:bg-[#1a1a2e]"
          />
        )}
        <span className="flex items-center gap-1">
          <button onClick={zoomOut} className="px-1.5 py-0.5 rounded border border-border dark:border-gray-700">−</button>
          <span className="w-11 text-center">Zoom: {Math.round(zoom * 100)}%</span>
          <button onClick={zoomIn} className="px-1.5 py-0.5 rounded border border-border dark:border-gray-700">+</button>
        </span>
      </footer>
    </div>
  );
}

function HeaderSep() {
  return <span className="text-xs text-border dark:text-gray-700 select-none">|</span>;
}
