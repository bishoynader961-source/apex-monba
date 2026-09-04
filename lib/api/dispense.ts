// Typed Dispense API service (mirrors backend app/api/routers/dispense_route.py).
import { api } from "@/lib/api";
import type { DispenseCreate, DispenseRead, DispenseUpdate, TransferResult, VoidResult } from "@/types/contracts";

const BASE = "/api/v1/dispense";

export async function dispense(payload: DispenseCreate): Promise<DispenseRead> {
  const { data } = await api.post<DispenseRead>(BASE, payload);
  return data;
}

export async function getDispense(id: number): Promise<DispenseRead> {
  const { data } = await api.get<DispenseRead>(`${BASE}/${id}`);
  return data;
}

export async function getDispenseByRxNumber(rxNumber: string): Promise<DispenseRead> {
  const { data } = await api.get<DispenseRead>(`${BASE}/rx/${encodeURIComponent(rxNumber)}`);
  return data;
}

export async function getDispenseFills(rxNumber: string): Promise<DispenseRead[]> {
  const { data } = await api.get<DispenseRead[]>(`${BASE}/rx/${encodeURIComponent(rxNumber)}/fills`);
  return data;
}

export async function getDispenseLabel(id: number): Promise<Blob> {
  const response = await api.get<Blob>(`${BASE}/${id}/label`, {
    responseType: "blob",
  });
  return response.data;
}

export async function refillDispense(id: number, payload: DispenseCreate): Promise<DispenseRead> {
  const { data } = await api.post<DispenseRead>(`${BASE}/${id}/refill`, payload);
  return data;
}

export async function updateDispense(id: number, payload: DispenseUpdate): Promise<DispenseRead> {
  const { data } = await api.put<DispenseRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function reverseDispense(id: number, reason: string = ""): Promise<VoidResult> {
  const { data } = await api.post<VoidResult>(`${BASE}/${id}/reverse`, { reason });
  return data;
}

export async function transferDispense(
  id: number,
  payload: { pharmacy_name: string; pharmacy_phone: string; transfer_type: string; reason: string },
): Promise<TransferResult> {
  const { data } = await api.post<TransferResult>(`${BASE}/${id}/transfer`, payload);
  return data;
}
