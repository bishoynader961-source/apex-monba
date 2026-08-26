// Typed Dictionaries API service (mirrors backend app/api/routers/dictionaries_route.py).
import { api } from "@/lib/api";
import type {
  BatchRead,
  PriceCodeCreate,
  PriceCodeRead,
  SigCodeCreate,
  SigCodeParseResult,
  SigCodeRead,
} from "@/types/contracts";

const BASE = "/api/v1/dictionaries";

export async function listSigCodes(): Promise<SigCodeRead[]> {
  const { data } = await api.get<SigCodeRead[]>(`${BASE}/sig-codes`);
  return data;
}

export async function createSigCode(payload: SigCodeCreate): Promise<SigCodeRead> {
  const { data } = await api.post<SigCodeRead>(`${BASE}/sig-codes`, payload);
  return data;
}

export async function parseSigCode(code: string): Promise<SigCodeParseResult> {
  const { data } = await api.get<SigCodeParseResult>(`${BASE}/sig-codes/parse`, {
    params: { code },
  });
  return data;
}

export async function listPriceCodes(): Promise<PriceCodeRead[]> {
  const { data } = await api.get<PriceCodeRead[]>(`${BASE}/price-codes`);
  return data;
}

export async function createPriceCode(payload: PriceCodeCreate): Promise<PriceCodeRead> {
  const { data } = await api.post<PriceCodeRead>(`${BASE}/price-codes`, payload);
  return data;
}

export interface NdcLookupResult {
  found: boolean;
  q: string;
  item?: BatchRead | null;
}

export async function ndcLookup(q: string): Promise<NdcLookupResult> {
  const { data } = await api.get<NdcLookupResult>(`${BASE}/ndc/lookup`, {
    params: { q },
  });
  return data;
}
