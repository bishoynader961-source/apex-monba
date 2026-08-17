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
