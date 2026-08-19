// Typed POS API service.
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import type {
  CheckoutRequest,
  CheckoutResult,
  DrawerMovementCreate,
  DrawerMovementRead,
  RefundRead,
  RefundRequest,
  SalesReport,
} from "@/types/contracts";

const BASE = "/api/v1/pos";

// Enrich a checkout request with the client timestamp + (untrusted) cashier token
// derived from the current session so the server can attribute the sale (B.7/B.8).
export async function checkout(payload: CheckoutRequest): Promise<CheckoutResult> {
  const token = useAuthStore.getState().token;
  const enriched: CheckoutRequest = {
    ...payload,
    client_timestamp: new Date().toISOString(),
    cashier_token: token ?? undefined,
  };
  const { data } = await api.post<CheckoutResult>(`${BASE}/checkout`, enriched);
  return data;
}

export async function drawerMovement(
  payload: DrawerMovementCreate,
  approvalToken: string,
): Promise<DrawerMovementRead> {
  const token = useAuthStore.getState().token;
  const enriched: DrawerMovementCreate = {
    ...payload,
    client_timestamp: new Date().toISOString(),
    cashier: useAuthStore.getState().user?.username ?? payload.cashier ?? "",
  };
  const { data } = await api.post<DrawerMovementRead>(`${BASE}/drawer/movement`, enriched, {
    headers: { "X-Approval-Token": approvalToken, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  return data;
}

// B5: reverse a sale. Requires the `pos.checkout` permission server-side.
export async function refundSale(payload: RefundRequest): Promise<RefundRead> {
  const { data } = await api.post<RefundRead>(`${BASE}/refund`, payload);
  return data;
}

// B5: aggregated sales + refunds summary. Requires `inventory.reports`.
export async function getSalesReport(): Promise<SalesReport> {
  const { data } = await api.get<SalesReport>(`${BASE}/reports/sales`);
  return data;
}
