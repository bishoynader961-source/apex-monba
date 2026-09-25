import { api } from "@/lib/api";
import type {
  ExcelImportResult,
  ExcelImportAnalyzeResult,
  ExcelImportDbField,
  ExcelImportPreviewResult,
  ExcelImportPreviewRow,
  ExcelImportCommitResult,
} from "@/types/contracts";

export async function exportInventoryExcel(): Promise<Blob> {
  const res = await api.get("/api/v1/excel/export/inventory", {
    responseType: "blob",
  });
  return res.data as Blob;
}

export async function importInventoryExcel(file: File): Promise<ExcelImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/v1/excel/import/inventory", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ExcelImportResult;
}

export async function importInventoryCsv(file: File): Promise<ExcelImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/v1/excel/import/csv", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ExcelImportResult;
}

export async function analyzeImport(file: File): Promise<ExcelImportAnalyzeResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/v1/excel/import/analyze", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ExcelImportAnalyzeResult;
}

export async function previewImport(
  file: File,
  mapping: Record<string, number>,
  defaults: Record<string, string>,
  limit: number = 20
): Promise<ExcelImportPreviewResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("mapping", JSON.stringify(mapping));
  form.append("defaults", JSON.stringify(defaults));
  form.append("limit", String(limit));
  const res = await api.post("/api/v1/excel/import/preview", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ExcelImportPreviewResult;
}

export async function commitImport(
  file: File,
  mapping: Record<string, number>,
  defaults: Record<string, string>,
  generateLabels: boolean = false
): Promise<ExcelImportCommitResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("mapping", JSON.stringify(mapping));
  form.append("defaults", JSON.stringify(defaults));
  if (generateLabels) form.append("generate_labels", "true");
  const res = await api.post("/api/v1/excel/import/commit", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data as ExcelImportCommitResult;
}
