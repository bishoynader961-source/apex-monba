// Label Template + Product Label API service.
import { api } from "@/lib/api";

export type LabelElementType = "text" | "barcode" | "qr" | "shape" | "image";

export interface LabelElement {
  id: string;
  type: LabelElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  props: Record<string, unknown>;
}

export interface LabelTemplateRead {
  id: number;
  name: string;
  canvas_width: number;
  canvas_height: number;
  elements: LabelElement[];
  is_default: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProductLabelRead {
  id: number;
  product_id: number;
  canvas_width: number;
  canvas_height: number;
  elements: LabelElement[];
  updated_at?: string | null;
}

const TPL_BASE = "/api/v1/label-templates";
const PL_BASE = "/api/v1/product-labels";

export async function listLabelTemplates(): Promise<LabelTemplateRead[]> {
  const { data } = await api.get<LabelTemplateRead[]>(TPL_BASE);
  return data;
}

export async function getLabelTemplate(id: number): Promise<LabelTemplateRead> {
  const { data } = await api.get<LabelTemplateRead>(`${TPL_BASE}/${id}`);
  return data;
}

export async function createLabelTemplate(payload: {
  name: string; canvas_width?: number; canvas_height?: number;
  elements?: LabelElement[]; is_default?: number;
}): Promise<LabelTemplateRead> {
  const { data } = await api.post<LabelTemplateRead>(TPL_BASE, payload);
  return data;
}

export async function updateLabelTemplate(id: number, payload: {
  name?: string; canvas_width?: number; canvas_height?: number;
  elements?: LabelElement[]; is_default?: number;
}): Promise<LabelTemplateRead> {
  const { data } = await api.put<LabelTemplateRead>(`${TPL_BASE}/${id}`, payload);
  return data;
}

export async function deleteLabelTemplate(id: number): Promise<void> {
  await api.delete(`${TPL_BASE}/${id}`);
}

export async function getProductLabel(productId: number): Promise<ProductLabelRead | null> {
  try {
    const { data } = await api.get<ProductLabelRead>(`${PL_BASE}/${productId}`);
    return data;
  } catch {
    return null;
  }
}

export async function saveProductLabel(productId: number, payload: {
  canvas_width: number; canvas_height: number; elements: LabelElement[];
}): Promise<ProductLabelRead> {
  const { data } = await api.put<ProductLabelRead>(`${PL_BASE}/${productId}`, payload);
  return data;
}
