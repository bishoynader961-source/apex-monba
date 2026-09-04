// Typed Demand Analytics API service. Wraps the shared Axios instance
// (lib/api.ts) so callers never pass raw string paths.
import { api } from "@/lib/api";
import type { DemandAnalyticsSummary, TopSellingResponse } from "@/types/contracts";

export interface DemandAnalyticsFilters {
  start_date?: string; // YYYY-MM-DD
  end_date?: string; // YYYY-MM-DD
  category?: string; // product category filter
  min_sales?: number; // exclude items below this demanded quantity
  sort_by?: "total_quantity" | "total_revenue" | "avg_daily_consumption";
  lead_time_days?: number; // days used for reorder suggestions
}

export async function getDemandAnalytics(
  params: DemandAnalyticsFilters = {},
): Promise<DemandAnalyticsSummary> {
  const { data } = await api.get<DemandAnalyticsSummary>("/api/v1/analytics/demand", {
    params,
  });
  return data;
}

export interface TopSellingFilters {
  start_date?: string;
  end_date?: string;
  limit?: number;
}

export async function getTopSelling(
  params: TopSellingFilters = {},
): Promise<TopSellingResponse> {
  const { data } = await api.get<TopSellingResponse>("/api/v1/analytics/top-selling", {
    params,
  });
  return data;
}
