"use client";

import { useRef, useState } from "react";
import type { LabelElement } from "./LabelCanvas";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/useToast";

interface Props {
  element: LabelElement | null;
  selectedCount?: number;
  canvasWidth: number;
  canvasHeight: number;
  canvasBg: string;
  onCanvasChange: (patch: { width?: number; height?: number; background?: string }) => void;
  onChange: (id: string, props: Record<string, unknown>) => void;
  onGeometryChange: (id: string, patch: { x?: number; y?: number; width?: number; height?: number }) => void;
  onDelete: (id: string) => void;
}

const FONTS = ["Arial", "Helvetica", "Times New Roman", "Courier New", "Courier", "Verdana", "Georgia", "monospace"];
const SHAPES = ["rectangle", "ellipse", "rounded-rectangle", "line"];
const BARCODE_FORMATS = ["CODE128", "CODE39", "EAN13", "UPC"];
const EC_LEVELS = ["L", "M", "Q", "H"];

const inputClasses = "w-full px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500";
const labelClasses = "text-[10px] font-semibold text-gray-500 dark:text-gray-400 block mb-1";
const selectClasses = "w-full px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500";
const colorInputClasses = "w-full h-7 p-0.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 cursor-pointer";

export default function LabelPropertiesPanel({
  element,
  selectedCount = 0,
  canvasWidth,
  canvasHeight,
  canvasBg,
  onCanvasChange,
  onChange,
  onGeometryChange,
  onDelete,
}: Props) {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  if (!element) {
    return (
      <div className="w-[280px] shrink-0 p-4 border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 overflow-y-auto">
        <h3 className="text-sm font-semibold mb-1 text-gray-900 dark:text-gray-100">Properties</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">Click an element to edit its properties.</p>
        <div className="space-y-2">
          <Field label="Canvas width">
            <input
              type="number"
              min={50}
              max={2000}
              value={canvasWidth}
              onChange={(e) => onCanvasChange({ width: Math.max(50, parseInt(e.target.value) || canvasWidth) })}
              className={inputClasses}
            />
          </Field>
          <Field label="Canvas height">
            <input
              type="number"
              min={50}
              max={2000}
              value={canvasHeight}
              onChange={(e) => onCanvasChange({ height: Math.max(50, parseInt(e.target.value) || canvasHeight) })}
              className={inputClasses}
            />
          </Field>
          <Field label="Background">
            <input
              type="color"
              value={canvasBg}
              onChange={(e) => onCanvasChange({ background: e.target.value })}
              className={colorInputClasses}
            />
          </Field>
        </div>
      </div>
    );
  }

  const update = (key: string, value: unknown) => {
    onChange(element.id, { ...element.props, [key]: value });
  };

  return (
    <div className="w-[280px] shrink-0 p-4 border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 overflow-y-auto">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Properties</h3>
        <button onClick={() => onDelete(element.id)} className="text-xs text-red-600 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300">
          Delete
        </button>
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
        Type: <strong>{element.type}</strong>
        {selectedCount > 1 && <span className="ml-1">({selectedCount} selected)</span>}
        <span className="block">Pos: ({element.x}, {element.y}) | Size: {element.width}×{element.height}</span>
      </div>

      {element.type === "text" && (
        <TextFields element={element} update={update} />
      )}

      {element.type === "shape" && (
        <div className="space-y-2">
          <Field label="Shape">
            <select value={String(element.props.shape ?? "rectangle")} onChange={(e) => update("shape", e.target.value)} className={selectClasses}>
              {SHAPES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Fill color">
            <input type="color" value={String(element.props.fill_color ?? "#cccccc")} onChange={(e) => update("fill_color", e.target.value)} className={colorInputClasses} />
          </Field>
          <Field label="Border color">
            <input type="color" value={String(element.props.border_color ?? "#000000")} onChange={(e) => update("border_color", e.target.value)} className={colorInputClasses} />
          </Field>
          <Field label="Border width">
            <input type="number" min={0} max={20} value={Number(element.props.border_width ?? 2)} onChange={(e) => update("border_width", parseInt(e.target.value) || 0)} className={inputClasses} />
          </Field>
          <Field label="Border radius">
            <input type="number" min={0} max={100} value={Number(element.props.border_radius ?? 0)} onChange={(e) => update("border_radius", parseInt(e.target.value) || 0)} className={inputClasses} />
          </Field>
        </div>
      )}

      {element.type === "barcode" && (
        <BarcodeFields element={element} update={update} toastError={(m) => toast({ title: "Error", message: m, variant: "destructive" })} />
      )}

      {element.type === "qr" && (
        <div className="space-y-2">
          <Field label="Data">
            <input value={String(element.props.data ?? "")} onChange={(e) => update("data", e.target.value)} className={inputClasses} />
          </Field>
          <Field label="Error correction">
            <select value={String(element.props.ec_level ?? "M")} onChange={(e) => update("ec_level", e.target.value)} className={selectClasses}>
              {EC_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
          <Field label="Fill">
            <input type="color" value={String(element.props.fill_color ?? "#000000")} onChange={(e) => update("fill_color", e.target.value)} className={colorInputClasses} />
          </Field>
          <Field label="Background">
            <input type="color" value={String(element.props.back_color ?? "#ffffff")} onChange={(e) => update("back_color", e.target.value)} className={colorInputClasses} />
          </Field>
        </div>
      )}

      {element.type === "image" && (
        <div className="space-y-2">
          <Field label="Image source (URL or data URL)">
            <textarea
              value={String(element.props.src ?? "")}
              onChange={(e) => update("src", e.target.value)}
              rows={3}
              placeholder="https://… or paste data URL"
              className={inputClasses}
            />
          </Field>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const reader = new FileReader();
            reader.onload = () => update("src", String(reader.result ?? ""));
            reader.readAsDataURL(f);
          }} />
          <button onClick={() => fileRef.current?.click()} className="w-full px-2 py-1.5 text-xs rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800">
            Upload image…
          </button>
          {String(element.props.src ?? "").startsWith("data:") && (
            <p className="text-[10px] text-gray-500">Embedded image ({Math.round(String(element.props.src ?? "").length / 1024)} KB)</p>
          )}
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <Field label="X">
          <input type="number" value={element.x} onChange={(e) => onGeometryChange(element.id, { x: parseInt(e.target.value) || 0 })} className={inputClasses} />
        </Field>
        <Field label="Y">
          <input type="number" value={element.y} onChange={(e) => onGeometryChange(element.id, { y: parseInt(e.target.value) || 0 })} className={inputClasses} />
        </Field>
        <Field label="W">
          <input type="number" min={10} value={element.width} onChange={(e) => onGeometryChange(element.id, { width: Math.max(10, parseInt(e.target.value) || element.width) })} className={inputClasses} />
        </Field>
        <Field label="H">
          <input type="number" min={10} value={element.height} onChange={(e) => onGeometryChange(element.id, { height: Math.max(10, parseInt(e.target.value) || element.height) })} className={inputClasses} />
        </Field>
      </div>
    </div>
  );
}

function TextFields({ element, update }: { element: LabelElement; update: (k: string, v: unknown) => void }) {
  const align = String(element.props.align ?? "left");
  const toggle = (key: "bold" | "italic" | "underline") => update(key, !Boolean(element.props[key]));
  return (
    <div className="space-y-2">
      <Field label="Content">
        <textarea value={String(element.props.text ?? "")} onChange={(e) => update("text", e.target.value)} rows={3} className={inputClasses} />
      </Field>
      <Field label="Font">
        <select value={String(element.props.font ?? "Arial")} onChange={(e) => update("font", e.target.value)} className={selectClasses}>
          {FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>
      <Field label="Size">
        <input type="number" min={6} max={200} value={Number(element.props.font_size ?? 16)} onChange={(e) => update("font_size", parseInt(e.target.value) || 16)} className={inputClasses} />
      </Field>
      <div className="flex gap-1">
        {(["bold", "italic", "underline"] as const).map((k) => (
          <button
            key={k}
            onClick={() => toggle(k)}
            title={k}
            className={`flex-1 px-2 py-1 text-xs rounded border ${Boolean(element.props[k]) ? "bg-blue-600 text-white border-blue-600" : "border-gray-300 dark:border-gray-600"}`}
          >
            {k === "bold" ? "B" : k === "italic" ? "I" : "U"}
          </button>
        ))}
      </div>
      <Field label="Color">
        <input type="color" value={String(element.props.color ?? "#000000")} onChange={(e) => update("color", e.target.value)} className={colorInputClasses} />
      </Field>
      <Field label="Alignment">
        <div className="flex gap-1">
          {(["left", "center", "right"] as const).map((a) => (
            <button
              key={a}
              onClick={() => update("align", a)}
              className={`flex-1 px-2 py-1 text-xs rounded border capitalize ${align === a ? "bg-blue-600 text-white border-blue-600" : "border-gray-300 dark:border-gray-600"}`}
            >
              {a}
            </button>
          ))}
        </div>
      </Field>
    </div>
  );
}

function BarcodeFields({
  element,
  update,
  toastError,
}: {
  element: LabelElement;
  update: (k: string, v: unknown) => void;
  toastError: (m: string) => void;
}) {
  const [mode, setMode] = useState<"Manual" | "Auto">(
    element.props.barcodeMode === "Auto" ? "Auto" : "Manual"
  );
  const [prefix, setPrefix] = useState(String(element.props.barcodePrefix ?? "PHARMA-"));
  const [separator, setSeparator] = useState(String(element.props.barcodeSeparator ?? "-"));
  const [numberType, setNumberType] = useState<"Sequential" | "Random">(
    element.props.barcodeNumberType === "Random" ? "Random" : "Sequential"
  );
  const [scope, setScope] = useState<"Unique" | "Shared">(
    element.props.barcodeScope === "Shared" ? "Shared" : "Unique"
  );
  const [preview, setPreview] = useState(String(element.props.data ?? ""));
  const [generating, setGenerating] = useState(false);

  const changeMode = (m: "Manual" | "Auto") => {
    setMode(m);
    update("barcodeMode", m);
  };

  const generate = async () => {
    setGenerating(true);
    try {
      if (numberType === "Random") {
        const random = Math.floor(100000 + Math.random() * 900000);
        const val = `${prefix}${separator}${random}`;
        setPreview(val);
        update("data", val);
        return;
      }
      const resp = await api.get<{ next: number }>(`/api/v1/barcodes/next-sequence?prefix=${encodeURIComponent(prefix)}`);
      const val = `${prefix}${separator}${String(resp.data.next).padStart(6, "0")}`;
      setPreview(val);
      update("data", val);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Barcode generation failed");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex rounded border border-gray-300 dark:border-gray-600 overflow-hidden text-xs">
        {(["Manual", "Auto"] as const).map((m) => (
          <button
            key={m}
            onClick={() => changeMode(m)}
            className={`flex-1 px-2 py-1 ${mode === m ? "bg-blue-600 text-white" : ""}`}
          >
            {m === "Auto" ? "Auto-generate" : "Manual"}
          </button>
        ))}
      </div>

      {mode === "Manual" ? (
        <Field label="Data">
          <input value={String(element.props.data ?? "")} onChange={(e) => update("data", e.target.value)} className={inputClasses} />
        </Field>
      ) : (
        <div className="space-y-2">
          <Field label="Prefix">
            <input value={prefix} onChange={(e) => { setPrefix(e.target.value); update("barcodePrefix", e.target.value); }} className={inputClasses} placeholder="PHARMA-" />
          </Field>
          <Field label="Separator">
            <input value={separator} onChange={(e) => { setSeparator(e.target.value); update("barcodeSeparator", e.target.value); }} className={inputClasses} maxLength={1} />
          </Field>
          <Field label="Number type">
            <select value={numberType} onChange={(e) => { const v = e.target.value as "Sequential" | "Random"; setNumberType(v); update("barcodeNumberType", v); }} className={selectClasses}>
              <option value="Sequential">Sequential</option>
              <option value="Random">Random</option>
            </select>
          </Field>
          <Field label="Scope">
            <select value={scope} onChange={(e) => { const v = e.target.value as "Unique" | "Shared"; setScope(v); update("barcodeScope", v); }} className={selectClasses}>
              <option value="Unique">Unique per item</option>
              <option value="Shared">Shared per batch</option>
            </select>
          </Field>
          <Field label="Preview">
            <input value={preview} readOnly className={`${inputClasses} bg-gray-100 dark:bg-gray-700`} />
          </Field>
          <div className="flex justify-end">
            <button
              onClick={() => void generate()}
              disabled={generating}
              className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded transition-colors"
            >
              {generating ? "Generating…" : "Generate"}
            </button>
          </div>
        </div>
      )}

      <Field label="Format">
        <select value={String(element.props.barcode_format ?? "CODE128")} onChange={(e) => update("barcode_format", e.target.value)} className={selectClasses}>
          {BARCODE_FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>

      <label className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300">
        <input type="checkbox" checked={Boolean(element.props.show_text ?? true)} onChange={(e) => update("show_text", e.target.checked)} className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" />
        Show text below barcode
      </label>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelClasses}>{label}</label>
      {children}
    </div>
  );
}
