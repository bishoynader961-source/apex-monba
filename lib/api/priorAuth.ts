// Typed Prior Authorization API service.
import { api } from "@/lib/api";
import type {
  PriorAuthCreate,
  PriorAuthRead,
  PriorAuthListResponse,
  PriorAuthFilters,
  PriorAuthUpdate,
  PriorAuthStatusTransition,
} from "@/types/contracts";

const BASE = "/api/v1/prior-auth";

export async function listPriorAuths(
  params: PriorAuthFilters = {},
): Promise<PriorAuthListResponse> {
  const { data } = await api.get<PriorAuthListResponse>(BASE, { params });
  return data;
}

export async function getPriorAuth(paId: number): Promise<PriorAuthRead> {
  const { data } = await api.get<PriorAuthRead>(`${BASE}/${paId}`);
  return data;
}

export async function createPriorAuth(payload: PriorAuthCreate): Promise<PriorAuthRead> {
  const { data } = await api.post<PriorAuthRead>(BASE, payload);
  return data;
}

export async function updatePriorAuth(paId: number, payload: PriorAuthUpdate): Promise<PriorAuthRead> {
  const { data } = await api.put<PriorAuthRead>(`${BASE}/${paId}`, payload);
  return data;
}

export async function transitionPriorAuthStatus(
  paId: number,
  payload: PriorAuthStatusTransition,
): Promise<PriorAuthRead> {
  const { data } = await api.patch<PriorAuthRead>(`${BASE}/${paId}/status`, payload);
  return data;
}

export async function withdrawPriorAuth(paId: number): Promise<PriorAuthRead> {
  const { data } = await api.post<PriorAuthRead>(`${BASE}/${paId}/withdraw`);
  return data;
}