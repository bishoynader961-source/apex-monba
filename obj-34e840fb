// Typed Region Strategy API service.
import { api } from "@/lib/api";
import type {
  PatientCostRequest,
  PatientCostResult,
  ClaimGenerationRequest,
  ClaimGenerationResult,
  PrescriptionValidationRequest,
  PrescriptionValidationResult,
  CredentialValidationRequest,
  CredentialValidationResult,
} from "@/types/contracts";

const BASE = "/api/v1/region-strategy";

export async function calculatePatientCost(
  payload: PatientCostRequest,
): Promise<PatientCostResult> {
  const { data } = await api.post<PatientCostResult>(`${BASE}/patient-cost`, payload);
  return data;
}

export async function generateClaim(
  payload: ClaimGenerationRequest,
): Promise<ClaimGenerationResult> {
  const { data } = await api.post<ClaimGenerationResult>(`${BASE}/generate-claim`, payload);
  return data;
}

export async function validatePrescription(
  payload: PrescriptionValidationRequest,
): Promise<PrescriptionValidationResult> {
  const { data } = await api.post<PrescriptionValidationResult>(
    `${BASE}/validate-prescription`,
    payload,
  );
  return data;
}

export async function validateCredentials(
  payload: CredentialValidationRequest,
): Promise<CredentialValidationResult> {
  const { data } = await api.post<CredentialValidationResult>(
    `${BASE}/validate-credentials`,
    payload,
  );
  return data;
}

export async function getSupportedRegions(): Promise<string[]> {
  const { data } = await api.get<string[]>(`${BASE}/supported-regions`);
  return data;
}