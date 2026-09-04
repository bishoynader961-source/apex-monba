/**
 * Audit log API client — tamper-evident chain verification and export.
 */
import { api } from "@/lib/api";
import type { AuditLogRead, AuditVerifyResult } from "@/types/contracts";

export async function verifyAuditChain(): Promise<AuditVerifyResult> {
  const { data } = await api.get<AuditVerifyResult>("/api/v1/audit/verify");
  return data;
}

export async function exportAuditLogs(fmt: "json" | "csv" = "json"): Promise<Blob> {
  const { data } = await api.get("/api/v1/audit/export", {
    params: { fmt },
    responseType: "blob",
  });
  return data as Blob;
}
