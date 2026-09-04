/**
 * Workers' Compensation Claims API client.
 */
import { api } from "@/lib/api";
import type { WCClaimCreate, WCClaimRead, WCClaimUpdate } from "@/types/contracts";

const BASE = "/api/v1/wc-claims";

export async function listWCClaims(params?: {
  patient_id?: number;
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<WCClaimRead[]> {
  const searchParams = new URLSearchParams();
  if (params?.patient_id) searchParams.set("patient_id", String(params.patient_id));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const qs = searchParams.toString();
  const { data } = await api.get<WCClaimRead[]>(`${BASE}${qs ? `?${qs}` : ""}`);
  return data;
}

export async function getWCClaim(id: number): Promise<WCClaimRead> {
  const { data } = await api.get<WCClaimRead>(`${BASE}/${id}`);
  return data;
}

export async function createWCClaim(payload: WCClaimCreate): Promise<WCClaimRead> {
  const { data } = await api.post<WCClaimRead>(BASE, payload);
  return data;
}

export async function updateWCClaim(id: number, payload: WCClaimUpdate): Promise<WCClaimRead> {
  const { data } = await api.put<WCClaimRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteWCClaim(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}
