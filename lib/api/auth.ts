// Typed Auth API service (read path).
//
// NOTE: Login / logout / refresh that WRITE the HTTP-only cookies intentionally
// remain in `stores/authStore.ts` + the Next.js route handlers under
// `app/api/auth/*` (they set `httpOnly` + `sameSite=strict` cookies). This
// module exposes only the cookie-free read path (`getCurrentUser`) so the
// service layer is complete without risking the secure cookie flow.
import { api } from "@/lib/api";
import type { CurrentUser } from "@/types/contracts";

const BASE = "/api/v1/auth";

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await api.get<CurrentUser>(`${BASE}/me`);
  return data;
}
