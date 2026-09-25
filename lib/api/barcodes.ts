// Typed Barcode API service — wraps the shared Axios instance (lib/api.ts).
import { api } from "@/lib/api";

export type BarcodeStrategy =
  | "random"
  | "sequential"
  | "manual"
  | "pattern"
  | "manufacturer";

export interface BarcodeGenerateRequest {
  strategy: BarcodeStrategy;
  value?: string;
  prefix?: string;
  pattern?: string;
  category?: string;
  manufacturer_barcode?: string;
}

export interface BarcodeGenerateResponse {
  barcode: string;
  strategy: BarcodeStrategy;
}

export interface ValidateBarcodeResponse {
  exists: boolean;
}

export async function generateBarcode(
  req: BarcodeGenerateRequest
): Promise<BarcodeGenerateResponse> {
  const { data } = await api.post<BarcodeGenerateResponse>(
    "/api/v1/barcodes/generate",
    req
  );
  return data;
}

export async function validateBarcode(
  barcode: string
): Promise<ValidateBarcodeResponse> {
  const { data } = await api.post<ValidateBarcodeResponse>(
    `/api/v1/barcodes/validate?barcode=${encodeURIComponent(barcode)}`
  );
  return data;
}

export async function getNextSequence(
  prefix: string
): Promise<{ next: number }> {
  const { data } = await api.get<{ next: number }>(
    `/api/v1/barcodes/next-sequence`,
    { params: { prefix } }
  );
  return data;
}
