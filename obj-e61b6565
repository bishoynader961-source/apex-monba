// Typed Quick-SIG Template API service.
import { api } from "@/lib/api";
import type {
  QuickSigTemplateCreate,
  QuickSigTemplateRead,
  QuickSigTemplateUpdate,
} from "@/types/contracts";

const BASE = "/api/v1/quick-sig";

export async function listQuickSigTemplates(params?: {
  favorites_only?: boolean;
  q?: string;
}): Promise<QuickSigTemplateRead[]> {
  const { data } = await api.get<QuickSigTemplateRead[]>(BASE, { params });
  return data;
}

export async function getQuickSigTemplate(id: number): Promise<QuickSigTemplateRead> {
  const { data } = await api.get<QuickSigTemplateRead>(`${BASE}/${id}`);
  return data;
}

export async function createQuickSigTemplate(payload: QuickSigTemplateCreate): Promise<QuickSigTemplateRead> {
  const { data } = await api.post<QuickSigTemplateRead>(BASE, payload);
  return data;
}

export async function updateQuickSigTemplate(id: number, payload: QuickSigTemplateUpdate): Promise<QuickSigTemplateRead> {
  const { data } = await api.put<QuickSigTemplateRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteQuickSigTemplate(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}

export async function toggleQuickSigFavorite(id: number): Promise<QuickSigTemplateRead> {
  const { data } = await api.post<QuickSigTemplateRead>(`${BASE}/${id}/favorite`);
  return data;
}

export async function incrementQuickSigUsage(id: number): Promise<QuickSigTemplateRead> {
  const { data } = await api.post<QuickSigTemplateRead>(`${BASE}/${id}/use`);
  return data;
}

export async function searchQuickSigSuggestions(q: string): Promise<QuickSigTemplateRead[]> {
  const { data } = await api.get<QuickSigTemplateRead[]>(`${BASE}/search/suggestions`, { params: { q } });
  return data;
}
