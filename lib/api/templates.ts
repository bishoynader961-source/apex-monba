import { api } from "@/lib/api";

export interface ProductTemplate {
  id: number;
  name: string;
  price: number;
  vendor_name: string | null;
  category: string | null;
  dea_schedule: string | null;
  reorder_threshold: number | null;
  created_at: string | null;
}

export interface TemplateCreate {
  name: string;
  price: number;
  vendor_name?: string;
  category?: string;
  dea_schedule?: string;
  reorder_threshold?: number;
}

const BASE = "/api/v1/templates";

export async function listTemplates(): Promise<ProductTemplate[]> {
  const { data } = await api.get<ProductTemplate[]>(BASE);
  return data;
}

export async function createTemplate(template: TemplateCreate): Promise<ProductTemplate> {
  const { data } = await api.post<ProductTemplate>(BASE, template);
  return data;
}

export async function updateTemplate(id: number, template: Partial<TemplateCreate>): Promise<ProductTemplate> {
  const { data } = await api.put<ProductTemplate>(`${BASE}/${id}`, template);
  return data;
}

export async function deleteTemplate(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}
