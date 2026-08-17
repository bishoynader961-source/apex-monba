// Typed manager-approval API (Concern 1).
import { api } from "@/lib/api";
import type { ApprovalRequest, ApprovalResponse } from "@/types/contracts";

const BASE = "/api/v1/pos";

export async function requestApproval(payload: ApprovalRequest): Promise<ApprovalResponse> {
  const { data } = await api.post<ApprovalResponse>(`${BASE}/approve`, payload);
  return data;
}
