import { api } from "@/lib/api";

export interface DashboardMetrics {
  total_products: number;
  total_inventory_value: number;
  today_receipts: number;
  today_revenue: number;
  active_patients: number;
  pending_rx_count: number;
  low_stock: { name: string; on_hand: number; threshold: number; barcode: string }[];
  expiring_soon: { name: string; on_hand: number; expiry: string; barcode: string }[];
  recent_activity: { action: string; details: string; time: string }[];
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  const res = await api.get("/api/v1/dashboard/metrics");
  return res.data as DashboardMetrics;
}

// ---------------------------------------------------------------------------
// Dashboard analytics (mock summary) — new endpoint `/api/v1/dashboard/analytics`
// ---------------------------------------------------------------------------

export interface DashboardAnalyticsTopItem {
  product_name: string;
  total_quantity: number;
  total_revenue: number;
}

export interface DashboardAnalytics {
  total_sales: number;
  total_customers: number;
  top_items: DashboardAnalyticsTopItem[];
}

/**
 * Retrieve a static analytics summary for the dashboard. The backend currently
 * returns deterministic mock data; this function provides a typed wrapper for
 * the endpoint.
 */
export async function getDashboardAnalytics(): Promise<DashboardAnalytics> {
  const res = await api.get("/api/v1/dashboard/analytics");
  return res.data as DashboardAnalytics;
}
