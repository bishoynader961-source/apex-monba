// Typed EPCS API service.
import { api } from "@/lib/api";
import type {
  EPCSPrescriptionCreate,
  EPCSPrescriptionRead,
  EPCSPrescriptionListResponse,
  EPCSPrescriptionUpdate,
  EPCSFilters,
  EPCSSignRequest,
  EPCSSignResult,
  EPCSTransmitRequest,
  EPCSTransmitResult,
  EPCSIdentityProofingRequest,
  EPCSIdentityProofingResult,
  EPCSIdentityProofingStatus,
} from "@/types/contracts";

const BASE = "/api/v1/epcs";

export async function listEpcsPrescriptions(
  params: EPCSFilters = {},
): Promise<EPCSPrescriptionListResponse> {
  const { data } = await api.get<EPCSPrescriptionListResponse>(BASE, { params });
  return data;
}

export async function getEpcsPrescription(rxId: number): Promise<EPCSPrescriptionRead> {
  const { data } = await api.get<EPCSPrescriptionRead>(`${BASE}/${rxId}`);
  return data;
}

export async function createEpcsPrescription(payload: EPCSPrescriptionCreate): Promise<EPCSPrescriptionRead> {
  const { data } = await api.post<EPCSPrescriptionRead>(BASE, payload);
  return data;
}

export async function updateEpcsPrescription(rxId: number, payload: EPCSPrescriptionUpdate): Promise<EPCSPrescriptionRead> {
  const { data } = await api.put<EPCSPrescriptionRead>(`${BASE}/${rxId}`, payload);
  return data;
}

export async function transitionEpcsStatus(rxId: number, status: string): Promise<EPCSPrescriptionRead> {
  const { data } = await api.patch<EPCSPrescriptionRead>(`${BASE}/${rxId}/status`, { status });
  return data;
}

export async function signEpcsPrescription(rxId: number, payload: EPCSSignRequest): Promise<EPCSSignResult> {
  const { data } = await api.post<EPCSSignResult>(`${BASE}/${rxId}/sign`, payload);
  return data;
}

export async function transmitEpcsPrescription(rxId: number, payload: EPCSTransmitRequest): Promise<EPCSTransmitResult> {
  const { data } = await api.post<EPCSTransmitResult>(`${BASE}/${rxId}/transmit`, payload);
  return data;
}

export async function getIdentityProofingStatus(prescriberId: number): Promise<EPCSIdentityProofingStatus> {
  const { data } = await api.get<EPCSIdentityProofingStatus>(`${BASE}/prescriber/${prescriberId}/identity`);
  return data;
}

export async function enrollIdentityProofing(prescriberId: number, payload: EPCSIdentityProofingRequest): Promise<EPCSIdentityProofingResult> {
  const { data } = await api.post<EPCSIdentityProofingResult>(`${BASE}/prescriber/${prescriberId}/identity`, payload);
  return data;
}