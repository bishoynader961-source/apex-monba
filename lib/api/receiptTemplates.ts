// Typed Receipt Template API service.
import { api } from "@/lib/api";
import type {
  ReceiptTemplateCreate,
  ReceiptTemplateRead,
  ReceiptTemplateUpdate,
} from "@/types/contracts";

const BASE = "/api/v1/receipt-templates";

export async function listReceiptTemplates(templateType = ""): Promise<ReceiptTemplateRead[]> {
  const { data } = await api.get<ReceiptTemplateRead[]>(BASE, { params: { template_type: templateType } });
  return data;
}

export async function getDefaultTemplate(templateType = "receipt"): Promise<ReceiptTemplateRead | null> {
  try {
    const { data } = await api.get<ReceiptTemplateRead>(`${BASE}/default`, { params: { template_type: templateType } });
    return data;
  } catch {
    return null;
  }
}

export async function getReceiptTemplate(id: number): Promise<ReceiptTemplateRead> {
  const { data } = await api.get<ReceiptTemplateRead>(`${BASE}/${id}`);
  return data;
}

export async function createReceiptTemplate(payload: ReceiptTemplateCreate): Promise<ReceiptTemplateRead> {
  const { data } = await api.post<ReceiptTemplateRead>(BASE, payload);
  return data;
}

export async function updateReceiptTemplate(id: number, payload: ReceiptTemplateUpdate): Promise<ReceiptTemplateRead> {
  const { data } = await api.put<ReceiptTemplateRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteReceiptTemplate(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}
