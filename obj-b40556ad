import { api } from "@/lib/api";

export interface GiftCard {
  id: number;
  code: string;
  initial_balance: number;
  current_balance: number;
  status: string;
  issued_to_patient_id: number | null;
  issued_by_user_id: number | null;
  issued_at: string | null;
  redeemed_at: string | null;
  voided_at: string | null;
  note: string | null;
}

export async function issueGiftCard(data: {
  initial_balance: number;
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

export async function redeemGiftCard(cardId: number, amount: number): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/api/v1/gift-cards/${cardId}/redeem`, { amount });
  return data;
}

export async function voidGiftCard(cardId: number): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/api/v1/gift-cards/${cardId}/void`);
  return data;
}
