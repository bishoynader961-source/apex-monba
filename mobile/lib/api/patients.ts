// Typed Patients API service — mobile READ-ONLY subset (Step 1.1b).
// Mirrors desktop lib/api/patients.ts (list/search/get only): mobile v1 has
// no create/edit/delete. All calls hit the live API — patient data is never
// cached or persisted locally (Privacy: PHI stays server-side + memory only).
import { api } from "./client";
import type { PaginatedPatients, PatientRead } from "../../types/contracts";

const BASE = "/api/v1/patients";

export interface ListPatientsParams {
  page?: number;
  page_size?: number;
  /** Backend search term (patients_route list_patients `q` param). */
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
