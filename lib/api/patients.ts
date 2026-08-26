// Typed Patients API service (mirrors backend app/api/routers/patients_route.py).
import { api } from "@/lib/api";
import type {
  InsuranceBindRequest,
  PatientCreate,
  PatientHistoryEntry,
  PatientRead,
  PatientUpdate,
  PaginatedPatients,
  DispenseRead,
} from "@/types/contracts";

const BASE = "/api/v1/patients";

export interface ListPatientsParams {
  page?: number;
  page_size?: number;
  q?: string;
}

export async function listPatients(params: ListPatientsParams = {}): Promise<PaginatedPatients> {
  const { data } = await api.get<PaginatedPatients>(BASE, { params });
  return data;
}

export async function searchPatients(q: string): Promise<PatientRead[]> {
  const { data } = await api.get<PatientRead[]>(`${BASE}/search`, { params: { q } });
  return data;
}

export async function getPatient(id: number): Promise<PatientRead> {
  const { data } = await api.get<PatientRead>(`${BASE}/${id}`);
  return data;
}

export async function createPatient(payload: PatientCreate): Promise<PatientRead> {
  const { data } = await api.post<PatientRead>(BASE, payload);
  return data;
}

export async function updatePatient(id: number, payload: PatientUpdate): Promise<PatientRead> {
  const { data } = await api.put<PatientRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deletePatient(id: number): Promise<PatientRead> {
  const { data } = await api.delete<PatientRead>(`${BASE}/${id}`);
  return data;
}

export async function bindInsurance(id: number, payload: InsuranceBindRequest): Promise<PatientRead> {
  const { data } = await api.post<PatientRead>(`${BASE}/${id}/insurance`, payload);
  return data;
}

export async function listPatientDispenses(patientId: number): Promise<DispenseRead[]> {
  const { data } = await api.get<DispenseRead[]>(`${BASE}/${patientId}/dispenses`);
  return data;
}

export async function getPatientHistory(patientId: number, limit = 100): Promise<PatientHistoryEntry[]> {
  const { data } = await api.get<PatientHistoryEntry[]>(`${BASE}/${patientId}/history`, {
    params: { limit },
  });
  return data;
}

// Members / dependents — proxied through the members-groups router.
export async function listPatientMembers(patientId: number): Promise<any[]> {
  const { data } = await api.get<any[]>("/api/v1/members-groups", {
    params: { patient_id: patientId },
  });
  return data;
}

export async function createMember(payload: {
  patient_id: number;
  member_name: string;
  relationship: string;
  dob: string;
}): Promise<any> {
  const { data } = await api.post<any>("/api/v1/members-groups", payload);
  return data;
}
