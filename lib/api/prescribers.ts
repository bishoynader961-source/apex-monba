/**
 * Prescriber API client — typed calls to FastAPI /api/v1/prescribers endpoints.
 */
import { api } from "@/lib/api";
import type { PrescriberCreate, PrescriberRead } from "@/types/contracts";

const BASE = "/api/v1/prescribers";

export async function listPrescribers(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}): Promise<PrescriberRead[]> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  if (params?.search) searchParams.set("search", params.search);
  const qs = searchParams.toString();
  const { data } = await api.get<PrescriberRead[]>(`${BASE}${qs ? `?${qs}` : ""}`);
  return data;
}

export async function getPrescriber(id: number): Promise<PrescriberRead> {
  const { data } = await api.get<PrescriberRead>(`${BASE}/${id}`);
  return data;
}

export async function createPrescriber(payload: PrescriberCreate): Promise<PrescriberRead> {
  const { data } = await api.post<PrescriberRead>(BASE, payload);
  return data;
}

export async function updatePrescriber(
  id: number,
  payload: PrescriberCreate,
): Promise<PrescriberRead> {
  const { data } = await api.put<PrescriberRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deletePrescriber(id: number): Promise<PrescriberRead> {
  const { data } = await api.delete<PrescriberRead>(`${BASE}/${id}`);
  return data;
}
