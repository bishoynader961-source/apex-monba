/**
 * Admin API client — backup and system operations.
 */
import { api } from "@/lib/api";
import type { BackupResult } from "@/types/contracts";

export async function createBackup(): Promise<BackupResult> {
  const { data } = await api.post<BackupResult>("/api/v1/admin/backup");
  return data;
}

export interface BackupEntry {
  path: string;
  filename: string;
  size_bytes: number;
  modified: number;
}

export async function listBackups(): Promise<BackupEntry[]> {
  const { data } = await api.get<BackupEntry[]>("/api/v1/admin/backups");
  return data;
}

export async function restoreBackup(file: File): Promise<{ message: string }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<{ message: string }>("/api/v1/admin/restore", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
