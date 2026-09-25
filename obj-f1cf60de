"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useRouter } from "next/navigation";
import { RouteGuard } from "@/components/RouteGuard";
import { listMedicines } from "@/lib/api/inventory";
import {
  listLabelTemplates,
  getProductLabel,
  type LabelTemplateRead,
  type ProductLabelRead,
  type LabelElement,
} from "@/lib/api/labelTemplates";
import { Printer, FileText, CheckSquare, Square, Search, Loader2, Download, X, Maximize2 } from "lucide-react";
import { useToast } from "@/hooks/useToast";

interface ProductForLabel {
  id: number;
  name: string;
  manufacturer_barcode: string;
  internal_unique_barcode: string;
  vendor_name: string;
  expiry_date: string;
  price: string;
  form?: string | null;
  strength?: string | null;
  category?: string | null;
  selected: boolean;
  label?: ProductLabelRead | null;
  template?: LabelTemplateRead | null;
}

const INPUT_STYLE = "w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm";

export default function BulkLabelPrintPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
const canRead = useCan("bulkLabelPrint.read");
const canWrite = useCan("inventory.write");
  const { toast } = useToast();

  const [products, setProducts] = useState<ProductForLabel[]>([]);
  const [templates, setTemplates] = useState<LabelTemplateRead[]>([]);
  const [defaultTemplateId, setDefaultTemplateId] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedCount, setSelectedCount] = useState(0);
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());

  if (!isAuthenticated()) {
    if (typeof window !== "undefined") router.replace("/login");
    return null;
  }

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [medicinesRes, templatesRes] = await Promise.all([
        listMedicines({ limit: 500 }),
        listLabelTemplates(),
      ]);
      const meds = medicinesRes.items ?? medicinesRes;
      const tpls = templatesRes;
      setTemplates(tpls);
      const def = tpls.find((t) => t.is_default);
      if (def) setDefaultTemplateId(def.id);
      const enriched: ProductForLabel[] = await Promise.all(
        meds.map(async (m) => {
          const productLabel = await getProductLabel(m.id).catch(() => null);
          return {
            id: m.id,
            name: m.name,
            manufacturer_barcode: m.manufacturer_barcode,
            internal_unique_barcode: m.internal_unique_barcode,
            vendor_name: m.vendor_name,
            expiry_date: m.expiry_date,
            price: m.price,
            form: m.form,
            strength: m.strength,
            category: m.category,
            selected: false,
            label: productLabel,
            template: productLabel ? null : def ?? tpls[0] ?? null,
          };
        })
      );
      setProducts(enriched);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to load data", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void loadData(); }, [loadData]);

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
  };

  const filteredProducts = products.filter((p) =>
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.internal_unique_barcode.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.manufacturer_barcode.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.vendor_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const toggleSelect = (id: number) => {
    setProducts((prev) => prev.map((p) => (p.id === id ? { ...p, selected: !p.selected } : p)));
  };

  const toggleSelectAll = () => {
    const allSelected = filteredProducts.every((p) => p.selected);
    setProducts((prev) =>
      prev.map((p) => (filteredProducts.some((fp) => fp.id === p.id) ? { ...p, selected: !allSelected } : p))
    );
  };

  useEffect(() => {
    const count = products.filter((p) => p.selected).length;
    setSelectedCount(count);
  }, [products]);

  const getLabelElements = (product: ProductForLabel): LabelElement[] => {
    if (product.label) return product.label.elements;
    if (product.template) return product.template.elements;
    return [];
  };

  const getLabelCanvasSize = (product: ProductForLabel): { width: number; height: number } => {
    if (product.label) return { width: product.label.canvas_width, height: product.label.canvas_height };
    if (product.template) return { width: product.template.canvas_width, height: product.template.canvas_height };
    return { width: 400, height: 300 };
  };

  const resolveVariables = (text: string, product: ProductForLabel): string => {
    const vars: Record<string, string> = {
      NAME: product.name,
      BARCODE: product.internal_unique_barcode,
      MFG_BARCODE: product.manufacturer_barcode,
      VENDOR: product.vendor_name,
      EXPIRY: product.expiry_date,
      PRICE: product.price,
      FORM: product.form ?? "",
      STRENGTH: product.strength ?? "",
      CATEGORY: product.category ?? "",
    };
    let out = text;
    for (const [k, v] of Object.entries(vars)) {
      out = out.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v);
    }
    return out;
  };

  const drawLabelToCanvas = useCallback(async (product: ProductForLabel, canvas: HTMLCanvasElement) => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const elements = getLabelElements(product);
    const { width, height } = getLabelCanvasSize(product);
    canvas.width = width;
    canvas.height = height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    for (const elem of elements) {
      ctx.save();
      if (elem.type === "text") {
        const text = resolveVariables(String(elem.props.text ?? "Text"), product);
        const font = String(elem.props.font ?? "Arial");
        const fontSize = Number(elem.props.font_size ?? 16);
        const color = String(elem.props.color ?? "#000000");
        ctx.font = `${fontSize}px ${font}`;
        ctx.fillStyle = color;
        ctx.textBaseline = "middle";
        ctx.fillText(text, elem.x, elem.y + elem.height / 2, elem.width);
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
        } else if (shape === "rounded-rectangle") {
          const r = Math.min(10, elem.width / 4, elem.height / 4);
          ctx.beginPath();
          ctx.roundRect(elem.x, elem.y, elem.width, elem.height, r);
          ctx.fill();
          ctx.stroke();
        } else {
          ctx.fillRect(elem.x, elem.y, elem.width, elem.height);
          ctx.strokeRect(elem.x, elem.y, elem.width, elem.height);
        }
      } else if (elem.type === "barcode") {
        const data = resolveVariables(String(elem.props.data ?? ""), product);
        try {
          const JsBarcode = (await import("jsbarcode")).default;
          const tempCanvas = document.createElement("canvas");
          JsBarcode(tempCanvas, data, {
            format: "CODE128",
            width: 2,
            height: 40,
            displayValue: Boolean(elem.props.show_text),
            fontSize: 12,
            margin: 0,
          });
          ctx.drawImage(tempCanvas, elem.x, elem.y, elem.width, elem.height);
        } catch {
          ctx.fillStyle = "#ff0000";
          ctx.font = "10px Arial";
          ctx.fillText("[Barcode Error]", elem.x, elem.y + 10);
        }
      } else if (elem.type === "qr") {
        const data = resolveVariables(String(elem.props.data ?? ""), product);
        try {
          const QRCode = (await import("qrcode")).default;
          const dataUrl = await QRCode.toDataURL(data, {
            width: elem.width,
            margin: 0,
            color: { dark: String(elem.props.fill_color ?? "#000000"), light: String(elem.props.back_color ?? "#ffffff") },
          });
          const img = new Image();
          img.src = dataUrl;
          await new Promise<void>((resolve) => {
            img.onload = () => { ctx.drawImage(img, elem.x, elem.y, elem.width, elem.height); resolve(); };
            img.onerror = () => resolve();
          });
        } catch {
          ctx.fillStyle = "#ff0000";
          ctx.font = "10px Arial";
          ctx.fillText("[QR Error]", elem.x, elem.y + 10);
        }
      }
      ctx.restore();
    }
  }, []);

  const generatePreview = async () => {
    const selected = products.filter((p) => p.selected);
    if (selected.length === 0) return;
    setSaving(true);
    try {
      for (const product of selected) {
        const canvas = canvasRefs.current.get(product.id);
        if (canvas) await drawLabelToCanvas(product, canvas);
      }
      setPreviewOpen(true);
      toast({ title: "Success", message: `Generated preview for ${selected.length} labels`, variant: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate preview");
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to generate preview", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handlePrint = () => {
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      toast({ title: "Error", message: "Popup blocked. Please allow popups.", variant: "destructive" });
      return;
    }
    const selected = products.filter((p) => p.selected);
    let html = `
      <html>
      <head>
        <title>Bulk Label Print</title>
        <style>
          body { margin: 0; padding: 10px; font-family: Arial, sans-serif; }
          .label-page { page-break-after: always; display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; }
          .label { border: 1px solid #ccc; box-sizing: border-box; background: white; }
          @media print { .no-print { display: none; } }
        </style>
      </head>
      <body>
        <div class="no-print" style="text-align:center; margin-bottom: 20px;">
          <button onclick="window.print()" style="padding: 10px 20px; font-size: 16px;">Print All Labels</button>
          <button onclick="window.close()" style="padding: 10px 20px; font-size: 16px; margin-left: 10px;">Close</button>
        </div>
    `;
    for (const product of selected) {
      const canvas = canvasRefs.current.get(product.id);
      if (canvas) {
        const dataUrl = canvas.toDataURL("image/png");
        const { width, height } = getLabelCanvasSize(product);
        html += `<div class="label-page"><img class="label" src="${dataUrl}" style="width:${width}px;height:${height}px" /></div>`;
      }
    }
    html += `</body></html>`;
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    toast({ title: "Print", message: `Opened print dialog for ${selected.length} labels`, variant: "success" });
  };

  const handleDownloadAll = async () => {
    const selected = products.filter((p) => p.selected);
    if (selected.length === 0) return;
    try {
      const JSZip = (await import("jszip")).default;
      const zip = new JSZip();
      for (const product of selected) {
        const canvas = canvasRefs.current.get(product.id);
        if (canvas) {
          const dataUrl = canvas.toDataURL("image/png");
          const base64 = dataUrl.split(",")[1];
          zip.file(`${product.name.replace(/[^a-z0-9]/gi, "_")}_${product.internal_unique_barcode}.png`, base64, { base64: true });
        }
      }
      const blob = await zip.generateAsync({ type: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bulk-labels-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: "Success", message: `Downloaded ${selected.length} labels as ZIP`, variant: "success" });
    } catch (err) {
      setError("Failed to create zip. JSZip may not be installed.");
      toast({ title: "Error", message: err instanceof Error ? err.message : "Failed to create zip", variant: "destructive" });
    }
  };

  return (
    <DashboardLayout>
      <RouteGuard permission="bulkLabelPrint.read">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <FileText className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Bulk Label Printing</h1>
        </div>

        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Select products, choose templates, and generate labels for batch printing or export.
        </p>

        {/* Toolbar */}
        <div className="flex flex-wrap gap-3 mb-4 bg-[#1a1a2e] border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search products..."
              value={searchTerm}
              onChange={handleSearch}
              className={INPUT_STYLE}
              style={{ width: 280 }}
            />
          </div>
          <button
            onClick={toggleSelectAll}
            className="px-4 py-2 border border-gray-600 bg-gray-800 text-gray-300 hover:bg-gray-700 rounded-md text-sm font-medium transition-colors"
          >
            {filteredProducts.every((p) => p.selected) && filteredProducts.length > 0 ? (
              <>
                <X className="w-4 h-4 mr-1" /> Deselect All
              </>
            ) : (
              <>
                <CheckSquare className="w-4 h-4 mr-1" /> Select All ({filteredProducts.length})
              </>
            )}
          </button>
          <span className="flex items-center text-sm text-gray-600 dark:text-gray-400 px-3">
            {selectedCount} of {products.length} selected
          </span>
        </div>

        {error && (
          <div className="mb-4 px-4 py-2.5 bg-red-600/15 border border-red-600/30 text-red-400 rounded-lg text-sm flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-xs">Dismiss</button>
          </div>
        )}

        {/* Product Grid */}
        <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center p-12">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4 max-h-[60vh] overflow-y-auto">
                {filteredProducts.map((product) => (
                  <div
                    key={product.id}
                    className={`relative border rounded-lg p-3 transition-colors ${product.selected ? "border-blue-500 bg-blue-500/10" : "border-gray-700 hover:border-gray-500"}`}
                  >
                    <label className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        aria-label={`Select ${product.name}`}
                        checked={product.selected}
                        onChange={() => toggleSelect(product.id)}
                        className="mt-1 w-4 h-4 accent-blue-500 border-gray-600 rounded"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gray-800 dark:text-gray-100 truncate">{product.name}</div>
                        <div className="text-xs text-gray-500 truncate">{product.vendor_name}</div>
                        <div className="text-xs text-gray-500 font-mono">{product.internal_unique_barcode}</div>
                        {product.expiry_date && (
                          <div className="text-xs text-amber-400">Exp: {product.expiry_date}</div>
                        )}
                      </div>
                    </label>
                    <div className="mt-2 flex items-center gap-2 text-xs">
                      {product.label && <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded">Custom</span>}
                      {product.template && !product.label && <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">Template</span>}
                      {!product.template && !product.label && <span className="px-2 py-0.5 bg-gray-500/20 text-gray-400 rounded">No Label</span>}
                    </div>
                  </div>
                ))}
              </div>

              {filteredProducts.length === 0 && !loading && (
                <div className="p-12 text-center text-gray-500">No products match your search.</div>
              )}
            </>
          )}
        </div>

        {/* Action Bar */}
        {selectedCount > 0 && (
          <div className="mt-4 flex flex-wrap gap-3 bg-[#1a1a2e] border border-gray-800 rounded-lg p-4">
            <button
              onClick={generatePreview}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors disabled:opacity-50"
            >
              <Loader2 className={`w-4 h-4 ${saving ? "animate-spin" : ""}`} />
              {saving ? "Generating..." : "Generate Preview"}
            </button>
            <button
              onClick={handlePrint}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors disabled:opacity-50"
            >
              <Printer className="w-4 h-4" />
              Print Labels
            </button>
            <button
              onClick={handleDownloadAll}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2.5 border border-gray-600 bg-gray-800 text-gray-300 hover:bg-gray-700 rounded-md font-medium transition-colors disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
              Download ZIP
            </button>
          </div>
        )}

        {/* Preview Modal */}
        {previewOpen && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50" onClick={() => setPreviewOpen(false)}>
            <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg w-full max-w-5xl max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between p-4 border-b border-gray-800">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Label Preview ({selectedCount} labels)</h3>
                <button onClick={() => setPreviewOpen(false)} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
              </div>
              <div className="p-4 max-h-[70vh] overflow-y-auto">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {products.filter((p) => p.selected).map((product) => (
                    <div key={product.id} className="flex flex-col items-center">
                      <div className="text-xs text-gray-600 dark:text-gray-400 mb-1 text-center truncate w-full">{product.name}</div>
                      <canvas
                        ref={(el) => { if (el) canvasRefs.current.set(product.id, el); }}
                        className="border border-gray-700 bg-white"
                        style={{ maxWidth: "100%", height: "auto" }}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-3 p-4 border-t border-gray-800">
                <button onClick={() => setPreviewOpen(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">Close</button>
                <button onClick={handlePrint} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700">
                  <Printer className="w-4 h-4 inline mr-1" />
                  Print
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}