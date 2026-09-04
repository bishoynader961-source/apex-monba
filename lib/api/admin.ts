/**
 * Admin API client — backup and system operations.
 */
import { api } from "@/lib/api";
import type { BackupResult } from "@/types/contracts";

export async function createBackup(): Promise<BackupResult> {
  const { data } = await api.post<BackupResult>("/api/v1/admin/backup");
  return data;
}
