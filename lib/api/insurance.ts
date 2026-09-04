// Typed Insurance API service (mirrors backend app/api/routers/insurance_route.py).
import { api } from "@/lib/api";
import type {
  EligibilityCheckResult,
  InsurancePlanCreate,
  InsurancePlanRead,
  InsuranceValidateRequest,
  InsuranceValidationResult,
} from "@/types/contracts";

const BASE = "/api/v1/insurance";

export async function listPlans(): Promise<InsurancePlanRead[]> {
  const { data } = await api.get<InsurancePlanRead[]>(`${BASE}/plans`);
  return data;
}

export async function getPlan(id: number): Promise<InsurancePlanRead> {
  const { data } = await api.get<InsurancePlanRead>(`${BASE}/plans/${id}`);
  return data;
}

export async function createPlan(payload: InsurancePlanCreate): Promise<InsurancePlanRead> {
  const { data } = await api.post<InsurancePlanRead>(`${BASE}/plans`, payload);
  return data;
}

export async function updatePlan(id: number, payload: InsurancePlanCreate): Promise<InsurancePlanRead> {
  const { data } = await api.put<InsurancePlanRead>(`${BASE}/plans/${id}`, payload);
  return data;
}

export async function deletePlan(id: number): Promise<InsurancePlanRead> {
  const { data } = await api.delete<InsurancePlanRead>(`${BASE}/plans/${id}`);
  return data;
}

export async function validatePlan(payload: InsuranceValidateRequest): Promise<InsuranceValidationResult> {
  const { data } = await api.post<InsuranceValidationResult>(`${BASE}/plans/validate`, payload);
  return data;
}

export async function checkEligibility(patientId: number): Promise<EligibilityCheckResult> {
  const { data } = await api.post<EligibilityCheckResult>(`${BASE}/eligibility`, { patient_id: patientId });
  return data;
}
