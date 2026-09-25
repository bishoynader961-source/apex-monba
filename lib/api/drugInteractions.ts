// Drug Interaction API service.
import { api } from "@/lib/api";
import type { DrugInteractionRead, DrugInteractionResult } from "@/types/contracts";

const BASE = "/api/v1/drug-interactions";

export async function checkDrugInteractions(drugNames: string[]): Promise<DrugInteractionResult[]> {
  const { data } = await api.post<DrugInteractionResult[]>(`${BASE}/check`, { drug_names: drugNames });
  return data;
}

export async function listDrugInteractions(): Promise<DrugInteractionRead[]> {
  const { data } = await api.get<DrugInteractionRead[]>(BASE);
  return data;
}

export async function createDrugInteraction(payload: {
  drug_a: string; drug_b: string; severity: string;
  description?: string; recommendation?: string;
}): Promise<DrugInteractionRead> {
  const { data } = await api.post<DrugInteractionRead>(BASE, payload);
  return data;
}

export async function updateDrugInteraction(id: number, payload: {
  severity?: string; description?: string; recommendation?: string; is_active?: number;
}): Promise<DrugInteractionRead> {
  const { data } = await api.put<DrugInteractionRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteDrugInteraction(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}
