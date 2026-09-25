import { api } from "@/lib/api";

export interface AlertCounts {
  expired: number;
  critical: number;
  warning: number;
  low_stock: number;
  total_products: number;
  checked_at: string;
}

export async function getAlerts(): Promise<AlertCounts> {
  const { data } = await api.get<AlertCounts>("/api/v1/alerts");
  return data;
}
