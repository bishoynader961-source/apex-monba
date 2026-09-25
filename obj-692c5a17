// Typed Compound API service.
import { api } from "@/lib/api";
import type {
  CompoundCreate,
  CompoundRead,
  CompoundUpdate,
  CompoundDispenseRequest,
  CompoundDispenseResult,
  CompoundPriceCalculationRequest,
  CompoundPriceCalculationResult,
} from "@/types/contracts";

const BASE = "/api/v1/compounds";

export async function listCompounds(
  page = 1,
  pageSize = 50,
): Promise<CompoundRead[]> {
  const { data } = await api.get<CompoundRead[]>(BASE, { params: { page, page_size: pageSize } });
  return data;
}

export async function getCompound(compoundId: number): Promise<CompoundRead> {
  const { data } = await api.get<CompoundRead>(`${BASE}/${compoundId}`);
  return data;
}

export async function createCompound(payload: CompoundCreate): Promise<CompoundRead> {
  const { data } = await api.post<CompoundRead>(BASE, payload);
  return data;
}

export async function updateCompound(compoundId: number, payload: CompoundUpdate): Promise<CompoundRead> {
  const { data } = await api.put<CompoundRead>(`${BASE}/${compoundId}`, payload);
  return data;
}

export async function deleteCompound(compoundId: number): Promise<void> {
  await api.delete(`${BASE}/${compoundId}`);
}

export async function calculateCompoundPrice(
  payload: CompoundPriceCalculationRequest,
): Promise<CompoundPriceCalculationResult> {
  const { data } = await api.post<CompoundPriceCalculationResult>(`${BASE}/${payload.compound_id}/price`, payload);
  return data;
}

export async function dispenseCompound(payload: CompoundDispenseRequest): Promise<CompoundDispenseResult> {
  const { data } = await api.post<CompoundDispenseResult>(`${BASE}/dispense`, payload);
  return data;
}