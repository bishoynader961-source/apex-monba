// Clinical workflow API client: notes, allergies, attachments, review.
import { api } from "@/lib/api";
import type {
  ClinicalNoteCreate,
  ClinicalNoteRead,
  ClinicalNoteUpdate,
  AllergyRecordCreate,
  AllergyRecordRead,
  AllergyRecordUpdate,
  ClinicalAttachmentRead,
  ClinicalReviewSummary,
} from "@/types/contracts";

const BASE = "/api/v1/clinical";

// ── Clinical Notes ───────────────────────────────────────────────────────────

export async function createClinicalNote(payload: ClinicalNoteCreate): Promise<ClinicalNoteRead> {
  const { data } = await api.post<ClinicalNoteRead>(`${BASE}/notes`, payload);
  return data;
}

export async function listClinicalNotes(
  patientId: number,
  category?: string,
  limit = 50,
): Promise<ClinicalNoteRead[]> {
  const params: Record<string, unknown> = { patient_id: patientId, limit };
  if (category) params.category = category;
  const { data } = await api.get<ClinicalNoteRead[]>(`${BASE}/notes`, { params });
  return data;
}

export async function updateClinicalNote(
  noteId: number,
  payload: ClinicalNoteUpdate,
): Promise<ClinicalNoteRead> {
  const { data } = await api.put<ClinicalNoteRead>(`${BASE}/notes/${noteId}`, payload);
  return data;
}

export async function deleteClinicalNote(noteId: number): Promise<void> {
  await api.delete(`${BASE}/notes/${noteId}`);
}

// ── Allergy Records ──────────────────────────────────────────────────────────

export async function createAllergyRecord(payload: AllergyRecordCreate): Promise<AllergyRecordRead> {
  const { data } = await api.post<AllergyRecordRead>(`${BASE}/allergies`, payload);
  return data;
}

export async function listAllergyRecords(patientId: number): Promise<AllergyRecordRead[]> {
  const { data } = await api.get<AllergyRecordRead[]>(`${BASE}/allergies`, {
    params: { patient_id: patientId },
  });
  return data;
}

export async function updateAllergyRecord(
  recordId: number,
  payload: AllergyRecordUpdate,
): Promise<AllergyRecordRead> {
  const { data } = await api.put<AllergyRecordRead>(`${BASE}/allergies/${recordId}`, payload);
  return data;
}

export async function deleteAllergyRecord(recordId: number): Promise<void> {
  await api.delete(`${BASE}/allergies/${recordId}`);
}

// ── Attachments ──────────────────────────────────────────────────────────────

export async function listAttachments(patientId: number): Promise<ClinicalAttachmentRead[]> {
  const { data } = await api.get<ClinicalAttachmentRead[]>(`${BASE}/attachments`, {
    params: { patient_id: patientId },
  });
  return data;
}

export async function deleteAttachment(attachmentId: number): Promise<void> {
  await api.delete(`${BASE}/attachments/${attachmentId}`);
}

// ── Review Summary ───────────────────────────────────────────────────────────

export async function getClinicalReview(patientId: number): Promise<ClinicalReviewSummary> {
  const { data } = await api.get<ClinicalReviewSummary>(`${BASE}/review/${patientId}`);
  return data;
}
