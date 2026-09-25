import { api } from "@/lib/api";

export interface VersionInfo {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  download_url: string | null;
  release_notes: string | null;
}

export async function checkVersion(): Promise<VersionInfo> {
  const { data } = await api.get<VersionInfo>("/api/v1/version");
  return data;
}
