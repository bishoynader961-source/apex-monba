"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import type JsBarcodeType from "jsbarcode";
import type QRCodeType from "qrcode";

// jsbarcode/qrcode are only needed once a barcode/QR element renders; load
// them lazily so the main bundle stays lean (Phase 3 diagnostics: performance).
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

export type LabelElementType = "text" | "barcode" | "qr" | "shape" | "image";

export interface LabelElement {
  id: string;
  type: LabelElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  props: Record<string, unknown>;
}

interface Props {
  width: number;
  height: number;
  elements: LabelElement[];
  selectedId: string | null;
  /** Multi-select set. Optional for backward compat (preview page). */
  selectedIds?: string[];
  /**
   * Selection callback. Second arg is true when the click was additive
   * (Shift+Click). Extra args are ignored by legacy callers.
   */
  onSelect: (id: string | null, additive?: boolean) => void;
  onMove: (id: string, x: number, y: number) => void;
  /** Group move for multi-select drag. Optional. */
  onMoveMany?: (moves: Array<{ id: string; x: number; y: number }>) => void;
  onResize: (id: string, w: number, h: number) => void;
  /** Fired on drag/resize start so the page can push an undo snapshot. */
  onDragStart?: () => void;
  variables?: Record<string, string>;
  /** Canvas background fill. Defaults to white paper. */
  background?: string;
  /** Display zoom multiplier (CSS scaling only, internal resolution unchanged). */
  zoom?: number;
  snapToGrid?: boolean;
  gridSize?: number;
}

const HANDLE_SIZE = 8;

function resolveVars(text: string, vars?: Record<string, string>): string {
  if (!vars) return text;
  let out = text;
  for (const [k, v] of Object.entries(vars)) {
    out = out.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v);
  }
  return out;
}

function snapVal(v: number, snap: boolean, grid: number): number {
  if (!snap || grid <= 0) return Math.round(v);
  return Math.round(v / grid) * grid;
}

export default function LabelCanvas({
  width,
  height,
  elements,
  selectedId,
  selectedIds,
  onSelect,
  onMove,
  onMoveMany,
  onResize,
  onDragStart,
  variables,
  background = "#ffffff",
  zoom = 1,
  snapToGrid = false,
  gridSize = 5,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const qrCache = useRef<Map<string, string>>(new Map());
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());
  const [dragging, setDragging] = useState<{
    id: string;
    offsetX: number;
    offsetY: number;
    startMx: number;
    startMy: number;
    origins: Map<string, { x: number; y: number }>;
    moved: boolean;
  } | null>(null);
  const [resizing, setResizing] = useState<{
    id: string;
    handle: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    origW: number;
    origH: number;
  } | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const selection: string[] = selectedIds ?? (selectedId ? [selectedId] : []);
  const selectionSet = new Set(selection);

  const draw = useCallback(async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = background || "#ffffff";
    ctx.fillRect(0, 0, width, height);

    for (const elem of elements) {
      ctx.save();

      if (elem.type === "text") {
        const text = resolveVars(String(elem.props.text ?? "Text"), variables);
        const font = String(elem.props.font ?? "Arial");
        const fontSize = Number(elem.props.font_size ?? 16);
        const color = String(elem.props.color ?? "#000000");
        const bold = Boolean(elem.props.bold);
        const italic = Boolean(elem.props.italic);
        const underline = Boolean(elem.props.underline);
        const align = String(elem.props.align ?? "left") as "left" | "center" | "right";
        ctx.font = `${italic ? "italic " : ""}${bold ? "bold " : ""}${fontSize}px ${font}, sans-serif`;
        ctx.fillStyle = color;
        ctx.textBaseline = "middle";
        ctx.textAlign = align;
        const tx = align === "center" ? elem.x + elem.width / 2 : align === "right" ? elem.x + elem.width : elem.x;
        const ty = elem.y + elem.height / 2;
        ctx.fillText(text, tx, ty, elem.width);
        if (underline) {
          const w = Math.min(ctx.measureText(text).width, elem.width);
          const ux = align === "center" ? tx - w / 2 : align === "right" ? tx - w : tx;
          ctx.strokeStyle = color;
          ctx.lineWidth = Math.max(1, fontSize / 12);
          ctx.beginPath();
          ctx.moveTo(ux, ty + fontSize / 2 + 1);
          ctx.lineTo(ux + w, ty + fontSize / 2 + 1);
          ctx.stroke();
        }
        ctx.textAlign = "left";
      } else if (elem.type === "shape") {
        const shape = String(elem.props.shape ?? "rectangle");
        const fill = String(elem.props.fill_color ?? "#cccccc");
        const stroke = String(elem.props.border_color ?? "#000000");
        const lineW = Number(elem.props.border_width ?? 2);
        const radius = Number(elem.props.border_radius ?? 0);
        ctx.fillStyle = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineW;
        if (shape === "ellipse") {
          ctx.beginPath();
          ctx.ellipse(elem.x + elem.width / 2, elem.y + elem.height / 2, elem.width / 2, elem.height / 2, 0, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        } else if (shape === "rounded-rectangle") {
          const r = radius > 0 ? Math.min(radius, elem.width / 2, elem.height / 2) : Math.min(10, elem.width / 4, elem.height / 4);
          ctx.beginPath();
          if (typeof ctx.roundRect === "function") {
            ctx.roundRect(elem.x, elem.y, elem.width, elem.height, r);
          } else {
            ctx.rect(elem.x, elem.y, elem.width, elem.height);
          }
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
        const data = resolveVars(String(elem.props.data ?? ""), variables);
        const format = String(elem.props.barcode_format ?? "CODE128");
        try {
          if (!data) throw new Error("empty");
          const JsBarcode = await loadJsBarcode();
          const tempCanvas = document.createElement("canvas");
          JsBarcode(tempCanvas, data, {
            format,
            width: 2,
            height: 40,
            displayValue: Boolean(elem.props.show_text ?? true),
            fontSize: 12,
            margin: 0,
          });
          ctx.drawImage(tempCanvas, elem.x, elem.y, elem.width, elem.height);
        } catch {
          ctx.fillStyle = "#ff0000";
          ctx.font = "10px Arial";
          ctx.textBaseline = "middle";
          ctx.fillText("[Barcode Error]", elem.x, elem.y + 10);
        }
      } else if (elem.type === "qr") {
        const data = resolveVars(String(elem.props.data ?? ""), variables);
        const ecLevel = String(elem.props.ec_level ?? "M");
        const cacheKey = `${data}_${elem.width}_${elem.height}_${ecLevel}`;
        if (!qrCache.current.has(cacheKey)) {
          try {            const QRCode = await loadQrCode();
            const dataUrl = await QRCode.toDataURL(data || " ", {
              width: Math.max(32, Math.round(elem.width)),
              margin: 0,
              errorCorrectionLevel: ecLevel as "L" | "M" | "Q" | "H",
              color: { dark: String(elem.props.fill_color ?? "#000000"), light: String(elem.props.back_color ?? "#ffffff") },
            });
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
          try {
            if (img.complete && img.naturalWidth > 0) {
              ctx.drawImage(img, elem.x, elem.y, elem.width, elem.height);
            } else {
              await new Promise<void>((resolve) => {
                const im = img as HTMLImageElement;
                im.onload = () => {
                  try { ctx.drawImage(im, elem.x, elem.y, elem.width, elem.height); } catch { /* ignore */ }
                  resolve();
                };
                im.onerror = () => resolve();
              });
            }
          } catch { /* ignore draw errors */ }
        }
      } else if (elem.type === "image") {
        const src = String(elem.props.src ?? "");
        if (!src) {
          ctx.fillStyle = "#e5e7eb";
          ctx.fillRect(elem.x, elem.y, elem.width, elem.height);
          ctx.fillStyle = "#6b7280";
          ctx.font = "11px Arial";
          ctx.textBaseline = "middle";
          ctx.fillText("No image", elem.x + 6, elem.y + elem.height / 2);
        } else {
          const cacheKey = `${src}_${elem.width}_${elem.height}`;
          let img = imgCache.current.get(cacheKey);
          if (!img) {
            img = new Image();
            img.src = src;
            imgCache.current.set(cacheKey, img);
          }
          try {
            if (img.complete && img.naturalWidth > 0) {
              ctx.drawImage(img, elem.x, elem.y, elem.width, elem.height);
            } else {
              await new Promise<void>((resolve) => {
                const im = img as HTMLImageElement;
                im.onload = () => {
                  try { ctx.drawImage(im, elem.x, elem.y, elem.width, elem.height); } catch { /* ignore */ }
                  resolve();
                };
                im.onerror = () => resolve();
              });
            }
          } catch {
            ctx.fillStyle = "#ff0000";
            ctx.font = "10px Arial";
            ctx.fillText("[Image Error]", elem.x, elem.y + 10);
          }
        }
      }

      // Selection outlines (all selected get solid outline, primary gets dashed + handles)
      if (selectionSet.has(elem.id)) {
        const isPrimary = elem.id === selectedId || (selection.length > 0 && elem.id === selection[selection.length - 1]);
        ctx.strokeStyle = isPrimary ? "#2563eb" : "#60a5fa";
        ctx.lineWidth = 1.5;
        if (isPrimary) ctx.setLineDash([5, 3]);
        ctx.strokeRect(elem.x - 2, elem.y - 2, elem.width + 4, elem.height + 4);
        ctx.setLineDash([]);

        if (isPrimary) {
          const handles = getHandlePositions(elem);
          for (const [, hx, hy] of handles) {
            ctx.fillStyle = "#2563eb";
            ctx.fillRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.strokeRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
          }
        }
      } else if (elem.id === hoverId) {
        ctx.strokeStyle = "rgba(37, 99, 235, 0.5)";
        ctx.lineWidth = 1;
        ctx.strokeRect(elem.x - 1, elem.y - 1, elem.width + 2, elem.height + 2);
      }

      ctx.restore();
    }
  }, [width, height, elements, selectedId, selection, hoverId, variables, background]);

  useEffect(() => { void draw(); }, [draw]);

  function getHandlePositions(elem: LabelElement) {
    return [
      ["se", elem.x + elem.width, elem.y + elem.height],
      ["sw", elem.x, elem.y + elem.height],
      ["ne", elem.x + elem.width, elem.y],
      ["nw", elem.x, elem.y],
      ["s", elem.x + elem.width / 2, elem.y + elem.height],
      ["e", elem.x + elem.width, elem.y + elem.height / 2],
    ] as const;
  }

  function hitTest(mx: number, my: number): { type: "element"; id: string } | { type: "handle"; handle: string } | null {
    // Handles only for the primary (last) selection
    const primaryId = selection.length > 0 ? selection[selection.length - 1] : selectedId;
    if (primaryId) {
      const sel = elements.find((e) => e.id === primaryId);
      if (sel) {
        for (const [name, hx, hy] of getHandlePositions(sel)) {
          if (Math.abs(mx - hx) <= HANDLE_SIZE && Math.abs(my - hy) <= HANDLE_SIZE) {
            return { type: "handle", handle: name };
          }
        }
      }
    }
    for (let i = elements.length - 1; i >= 0; i--) {
      const e = elements[i];
      if (mx >= e.x && mx <= e.x + e.width && my >= e.y && my <= e.y + e.height) {
        return { type: "element", id: e.id };
      }
    }
    return null;
  }

  function getCanvasCoords(e: React.MouseEvent): [number, number] {
    const canvas = canvasRef.current;
    if (!canvas) return [0, 0];
    const rect = canvas.getBoundingClientRect();
    const scaleX = width / rect.width;
    const scaleY = height / rect.height;
    return [(e.clientX - rect.left) * scaleX, (e.clientY - rect.top) * scaleY];
  }

  function handleMouseDown(e: React.MouseEvent) {
    const [mx, my] = getCanvasCoords(e);
    const hit = hitTest(mx, my);
    if (!hit) {
      onSelect(null, false);
      return;
    }
    const primaryId = selection.length > 0 ? selection[selection.length - 1] : selectedId;
    if (hit.type === "handle" && primaryId) {
      const sel = elements.find((el) => el.id === primaryId);
      if (!sel) return;
      onDragStart?.();
      setResizing({ id: primaryId, handle: hit.handle, startX: mx, startY: my, origX: sel.x, origY: sel.y, origW: sel.width, origH: sel.height });
    } else if (hit.type === "element") {
      const additive = e.shiftKey;
      onSelect(hit.id, additive);
      const el = elements.find((elem) => elem.id === hit.id);
      if (!el) return;
      onDragStart?.();
      // Origins for group move: if clicked element is (or will be) in a
      // multi-selection, move the whole group.
      const nextSel = additive
        ? (selectionSet.has(hit.id) ? selection.filter((id) => id !== hit.id) : [...selection, hit.id])
        : [hit.id];
      const groupIds = additive ? nextSel : selectionSet.has(hit.id) && selection.length > 1 ? selection : [hit.id];
      const origins = new Map<string, { x: number; y: number }>();
      for (const id of groupIds) {
        const g = elements.find((elem) => elem.id === id);
        if (g) origins.set(id, { x: g.x, y: g.y });
      }
      if (!origins.has(hit.id)) origins.set(hit.id, { x: el.x, y: el.y });
      setDragging({ id: hit.id, offsetX: mx - el.x, offsetY: my - el.y, startMx: mx, startMy: my, origins, moved: false });
    }
  }

  function handleMouseMove(e: React.MouseEvent) {
    const [mx, my] = getCanvasCoords(e);
    if (!dragging && !resizing) {
      const hit = hitTest(mx, my);
      setHoverId(hit && hit.type === "element" ? hit.id : null);
      return;
    }

    if (dragging) {
      const dx = mx - dragging.startMx;
      const dy = my - dragging.startMy;
      const moves: Array<{ id: string; x: number; y: number }> = [];
      for (const [id, o] of dragging.origins) {
        const nx = Math.max(0, Math.min(snapVal(o.x + dx, snapToGrid, gridSize), width - 10));
        const ny = Math.max(0, Math.min(snapVal(o.y + dy, snapToGrid, gridSize), height - 10));
        moves.push({ id, x: nx, y: ny });
      }
      if (moves.length === 1) {
        onMove(moves[0].id, moves[0].x, moves[0].y);
      } else if (onMoveMany) {
        onMoveMany(moves);
      } else {
        for (const m of moves) onMove(m.id, m.x, m.y);
      }
      setDragging({ ...dragging, moved: true });
    }

    if (resizing) {
      const dx = mx - resizing.startX;
      const dy = my - resizing.startY;
      const h = resizing.handle;
      let newW = resizing.origW;
      let newH = resizing.origH;
      if (h.includes("e")) newW = Math.max(20, resizing.origW + dx);
      if (h.includes("s")) newH = Math.max(20, resizing.origH + dy);
      if (h === "sw" || h === "nw") newW = Math.max(20, resizing.origW - dx);
      if (h === "ne" || h === "nw") newH = Math.max(20, resizing.origH - dy);
      onResize(resizing.id, Math.round(newW), Math.round(newH));
    }
  }

  function handleMouseUp() {
    setDragging(null);
    setResizing(null);
  }

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      data-label-canvas="true"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => { handleMouseUp(); setHoverId(null); }}
      className="label-canvas"
      style={{
        cursor: dragging ? "grabbing" : resizing ? "nwse-resize" : "crosshair",
        maxWidth: "100%",
        width: zoom !== 1 ? width * zoom : undefined,
        height: zoom !== 1 ? height * zoom : undefined,
        boxShadow: "0 4px 24px rgba(0,0,0,0.25)",
        borderRadius: 2,
      }}
    />
  );
}

export function createDefaultElements(barcode?: string, name?: string, price?: string, expiry?: string): LabelElement[] {
  const elems: LabelElement[] = [];
  let y = 10;
  if (barcode) {
    elems.push({ id: crypto.randomUUID().slice(0, 8), type: "barcode", x: 20, y, width: 200, height: 60, props: { data: barcode, show_text: true, barcode_format: "CODE128" } });
    y += 70;
  }
  if (name) {
    elems.push({ id: crypto.randomUUID().slice(0, 8), type: "text", x: 20, y, width: 280, height: 30, props: { text: name, font: "Arial", font_size: 16, color: "#000000" } });
    y += 35;
  }
  if (price) {
    elems.push({ id: crypto.randomUUID().slice(0, 8), type: "text", x: 20, y, width: 120, height: 24, props: { text: price, font: "Arial", font_size: 14, color: "#000000" } });
    y += 28;
  }
  if (expiry) {
    elems.push({ id: crypto.randomUUID().slice(0, 8), type: "text", x: 20, y, width: 180, height: 20, props: { text: `Exp: ${expiry}`, font: "Arial", font_size: 11, color: "#666666" } });
  }
  return elems;
}
