// Typed shift-lifecycle API (Concern 1 / A1).
import { api } from "@/lib/api";
import type {
  ShiftCloseRequest,
  ShiftCloseResult,
  ShiftOpenRequest,
  ShiftPreviewResult,
  ShiftRead,
} from "@/types/contracts";

const BASE = "/api/v1/pos";

export async function openShift(payload: ShiftOpenRequest): Promise<ShiftRead> {
  const { data } = await api.post<ShiftRead>(`${BASE}/shift/open`, payload);
  return data;
}

export async function previewShift(shiftId: number): Promise<ShiftPreviewResult> {
  const { data } = await api.get<ShiftPreviewResult>(`${BASE}/shift/${shiftId}/preview`);
  return data;
}

export async function closeShift(payload: ShiftCloseRequest): Promise<ShiftCloseResult> {
  const { data } = await api.post<ShiftCloseResult>(`${BASE}/shift/close`, payload);
  return data;
}
