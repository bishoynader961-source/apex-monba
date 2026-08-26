// Typed Dispense API service (mirrors backend app/api/routers/dispense_route.py).
import { api } from "@/lib/api";
import type { DispenseCreate, DispenseRead } from "@/types/contracts";

const BASE = "/api/v1/dispense";

export async function dispense(payload: DispenseCreate): Promise<DispenseRead> {
  const { data } = await api.post<DispenseRead>(BASE, payload);
  return data;
}

export async function getDispense(id: number): Promise<DispenseRead> {
  const { data } = await api.get<DispenseRead>(`${BASE}/${id}`);
  return data;
}

export async function getDispenseLabel(id: number): Promise<Blob> {
  const response = await api.get<Blob>(`${BASE}/${id}/label`, {
    responseType: "blob",
  });
  return response.data;
}
