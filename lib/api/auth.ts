// Typed Auth API service.
//
// NOTE: Login / logout / refresh that WRITE the HTTP-only cookies intentionally
// remain in `stores/authStore.ts` + the Next.js route handlers under
// `app/api/auth/*` (they set `httpOnly` + `sameSite=strict` cookies). This
// module exposes the cookie-free read path (`getCurrentUser`) and PIN-based
// auth so the service layer is complete without risking the secure cookie flow.
import { api } from "@/lib/api";
import type { CurrentUser, Token, UserPublic } from "@/types/contracts";

const BASE = "/api/v1/auth";

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await api.get<CurrentUser>(`${BASE}/me`);
  return data;
}

export async function pinLogin(username: string, pin: string): Promise<Token> {
  const { data } = await api.post<Token>(`${BASE}/login/pin`, { username, pin });
  return data;
}

export async function setPin(username: string, pin: string): Promise<void> {
  await api.post(`${BASE}/pin`, { username, pin });
}

export async function registerUser(payload: {
  username: string;
  display_name?: string;
  password: string;
  role_id?: number;
}): Promise<UserPublic> {
  const { data } = await api.post<UserPublic>(`${BASE}/register`, payload);
  return data;
}

export async function logoutUser(): Promise<{ status: string; message: string }> {
  const { data } = await api.post<{ status: string; message: string }>(`${BASE}/logout`);
  return data;
}

export async function rotatePepper(): Promise<{
  rotated: boolean;
  pin_pepper_version: number;
  pepper_bytes: string;
}> {
  const { data } = await api.post<{
    rotated: boolean;
    pin_pepper_version: number;
    pepper_bytes: string;
  }>(`${BASE}/rotate-pepper`);
  return data;
}

export async function changePassword(payload: {
  current_password: string;
  new_password: string;
  target_user_id?: number;
}): Promise<{ status: string; message: string }> {
  const { data } = await api.post<{ status: string; message: string }>(
    `${BASE}/change-password`,
    payload
  );
  return data;
}
