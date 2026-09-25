import { api } from "./client";
import type {
  DemandAnalyticsSummary,
  TopSellingResponse,
} from "../../types/contracts";

const BASE = "/api/v1/analytics";

export interface DemandParams {
  start_date?: string;
  end_date?: string;
  category?: string;
  min_sales?: number;
  sort_by?: "total_quantity" | "total_revenue" | "avg_daily_consumption";
  lead_time_days?: number;
}

export async function getDemandAnalytics(params: DemandParams = {}): Promise<DemandAnalyticsSummary> {
  const { data } = await api.get<DemandAnalyticsSummary>(`${BASE}/demand`, { params });
  return data;
}

export async function getTopSelling(
  period?: "day" | "week" | "month",
  limit = 10,
): Promise<TopSellingResponse> {
  const { data } = await api.get<TopSellingResponse>(`${BASE}/top-selling`, {
    params: { period, limit },
  });
  return data;
}
