// Typed Users API service (admin surface).
import { api } from "@/lib/api";
import type { UserPublic } from "@/types/contracts";

const BASE = "/api/v1/users";

export async function listUsers(): Promise<UserPublic[]> {
  const { data } = await api.get<UserPublic[]>(`${BASE}`);
  return data;
}

export async function getUser(id: number): Promise<UserPublic> {
  const { data } = await api.get<UserPublic>(`${BASE}/${id}`);
  return data;
}

export async function updateUser(id: number, payload: { display_name?: string; role_id?: number }): Promise<UserPublic> {
  const { data } = await api.put<UserPublic>(`${BASE}/${id}`, payload);
  return data;
}

export async function setUserActive(id: number, active: boolean): Promise<UserPublic> {
  const { data } = await api.patch<UserPublic>(`${BASE}/${id}/active?active=${active}`);
  return data;
}
