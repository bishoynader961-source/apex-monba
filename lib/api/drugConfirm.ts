// Typed Drug Confirmation API service (mirrors backend GET /api/v1/drugs/confirm/{ndc}).
import { api } from "@/lib/api";
import type { DrugConfirmResult } from "@/types/contracts";

export async function confirmDrug(ndc: string): Promise<DrugConfirmResult> {
  const response = await api.get<DrugConfirmResult>(`/api/v1/drugs/confirm/${encodeURIComponent(ndc)}`);
  return response.data;
}