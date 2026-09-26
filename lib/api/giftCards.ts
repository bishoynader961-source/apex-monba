import { api } from "@/lib/api";

// Money-safety invariant: balances are decimal strings (backend Decimal),
// never JS numbers. Any consumer needing arithmetic must use
// lib/decimalCurrency (bigint cents) — parseFloat/Number are forbidden here.
export interface GiftCard {
  id: number;
  code: string;
  initial_balance: Money;
  current_balance: Money;
  status: string;
  issued_to_patient_id: number | null;
  issued_by_user_id: number | null;
  issued_at: string | null;
  redeemed_at: string | null;
  voided_at: string | null;
  note: string | null;
}

/** Decimal money string ("12.34") — serialized from backend Decimal. */
type Money = string;

export async function issueGiftCard(data: {
  initial_balance: Money;
  issued_to_patient_id?: number;
  note?: string;
}): Promise<GiftCard> {
  const { data: card } = await api.post<GiftCard>("/api/v1/gift-cards", data);
  return card;
}

export async function listGiftCards(status?: string): Promise<GiftCard[]> {
  const params = status ? { status } : {};
  const { data } = await api.get<GiftCard[]>("/api/v1/gift-cards", { params });
  return data;
}

export async function lookupGiftCard(code: string): Promise<GiftCard> {
  const { data } = await api.get<GiftCard>(`/api/v1/gift-cards/lookup/${code}`);
  return data;
}

export async function redeemGiftCard(cardId: number, amount: Money): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/api/v1/gift-cards/${cardId}/redeem`, { amount });
  return data;
}

export async function voidGiftCard(cardId: number): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/api/v1/gift-cards/${cardId}/void`);
  return data;
}
