// Invoice parsing API service.
import { api } from "@/lib/api";

// ── Existing: Regex-based parsing ────────────────────────────────────────

export interface ParsedItem {
  product_name: string;
  active_ingredient: string;
  dosage_concentration: string;
  quantity_received: number;
  batch_number: string;
  expiration_date: string;
}

export interface ParseResponse {
  items: ParsedItem[];
  count: number;
}

// ── New: Hybrid OCR pipeline ─────────────────────────────────────────────

export interface HybridLineItem {
  description: string;
  quantity: number;
  unit_price: number;
}

export interface HardwareStatus {
  gpu_available: boolean;
  gpu_name: string | null;
  gpu_vram_gb: number;
  ram_total_gb: number;
  ram_available_gb: number;
  cpu_threads: number;
  cpu_physical_cores: number;
  tier: "capable" | "constrained" | "incompatible";
  recommended_mode: "hybrid" | "tesseract_only";
  warnings: string[];
}

export interface HybridParseResponse {
  invoice_number: string | null;
  total_amount: number | null;
  line_items: HybridLineItem[];
  metadata: Record<string, string>;
  confidence: { tesseract: number; paddleocr: number; overall: number };
  raw_text: string;
  engines_used: string[];
  processing_time_ms: number;
  hardware_status: HardwareStatus;
  warnings: string[];
}

// ── API functions ────────────────────────────────────────────────────────

const BASE = "/api/v1/invoice-parse";

export async function parseInvoiceText(text: string): Promise<ParseResponse> {
  const { data } = await api.post<ParseResponse>(`${BASE}/text`, { text });
  return data;
}

export async function parseInvoiceFile(file: File): Promise<ParseResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ParseResponse>(`${BASE}/file`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getHardwareStatus(): Promise<HardwareStatus> {
  const { data } = await api.get<HardwareStatus>(`${BASE}/hardware-status`);
  return data;
}

export async function parseInvoiceHybrid(
  file: File,
  mode: "auto" | "hybrid" | "tesseract_only" = "auto",
): Promise<HybridParseResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<HybridParseResponse>(
    `${BASE}/hybrid?mode=${mode}`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}
