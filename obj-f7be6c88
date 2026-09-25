import { api } from "@/lib/api";

export interface RegionConfig {
  code: string;
  name: string;
  currency: string;
  currency_symbol: string;
  date_format: string;
  tax_label: string;
  default_tax_rate: number;
  supports_insurance: boolean;
  supports_workers_comp: boolean;
  rx_requires_ndc: boolean;
  language: string;
}

export interface RegionSummary {
  code: string;
  name: string;
  currency: string;
  currency_symbol: string;
}

export async function detectRegion(): Promise<RegionConfig> {
  const { data } = await api.get<RegionConfig>("/api/v1/region/detect");
  return data;
}

export async function listRegions(): Promise<RegionSummary[]> {
  const { data } = await api.get<RegionSummary[]>("/api/v1/region/regions");
  return data;
}

export async function getRegion(code: string): Promise<RegionConfig> {
  const { data } = await api.get<RegionConfig>(`/api/v1/region/${code}`);
  return data;
}
