// Typed Coupon API service.
import { api } from "@/lib/api";
import type {
  CouponCreate,
  CouponRead,
  CouponUpdate,
  CouponValidateResult,
} from "@/types/contracts";

const BASE = "/api/v1/coupons";

export async function listCoupons(activeOnly = false): Promise<CouponRead[]> {
  const { data } = await api.get<CouponRead[]>(BASE, { params: { active_only: activeOnly } });
  return data;
}

export async function getCoupon(id: number): Promise<CouponRead> {
  const { data } = await api.get<CouponRead>(`${BASE}/${id}`);
  return data;
}

export async function createCoupon(payload: CouponCreate): Promise<CouponRead> {
  const { data } = await api.post<CouponRead>(BASE, payload);
  return data;
}

export async function updateCoupon(id: number, payload: CouponUpdate): Promise<CouponRead> {
  const { data } = await api.put<CouponRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function deleteCoupon(id: number): Promise<CouponRead> {
  const { data } = await api.delete<CouponRead>(`${BASE}/${id}`);
  return data;
}

export async function validateCoupon(code: string, subtotal: number): Promise<CouponValidateResult> {
  const { data } = await api.post<CouponValidateResult>(`${BASE}/validate`, { code, subtotal });
  return data;
}
