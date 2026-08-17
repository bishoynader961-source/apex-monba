// Typed Settings API service (read-only).
import { api } from "@/lib/api";
import type { SystemSettingRead } from "@/types/contracts";

const BASE = "/api/v1/settings";

export async function listSettings(): Promise<SystemSettingRead[]> {
  const { data } = await api.get<SystemSettingRead[]>(`${BASE}`);
  return data;
}

export async function getSetting(key: string): Promise<SystemSettingRead> {
  const { data } = await api.get<SystemSettingRead>(`${BASE}/${key}`);
  return data;
}
