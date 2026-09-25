import { api } from "@/lib/api";

export interface PatientField {
  id: number;
  patient_id: number;
  field_name: string;
  field_value: string | null;
}

export async function listPatientFields(patientId: number): Promise<PatientField[]> {
  const { data } = await api.get<PatientField[]>(`/api/v1/patients/${patientId}/fields`);
  return data;
}

export async function upsertPatientField(
  patientId: number,
  fieldName: string,
  fieldValue: string | null
): Promise<PatientField> {
  const { data } = await api.post<PatientField>(`/api/v1/patients/${patientId}/fields`, {
    patient_id: patientId,
    field_name: fieldName,
    field_value: fieldValue,
  });
  return data;
}

export async function deletePatientField(patientId: number, fieldName: string): Promise<void> {
  await api.delete(`/api/v1/patients/${patientId}/fields/${encodeURIComponent(fieldName)}`);
}
