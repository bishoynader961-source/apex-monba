import { api } from "./client";

export interface SystemSettingRead {
  key: string;
  value: string;
}

/**
 * Read a single SystemSetting value. Session-timeout minute values mirror the
 * desktop sessionStore and backend seeds (session_idle_minutes=15,
 * session_absolute_minutes=480). Failures return null so callers fall back to
 * those defaults — a settings outage must never block login.
 */
export async function getSettingsValue(key: string): Promise<string | null> {
  try {
    const { data } = await api.get<SystemSettingRead>(
      `/api/v1/settings/${encodeURIComponent(key)}`,
    );
    return data?.value ?? null;
  } catch {
    return null;
  }
}

export function parseTimeoutMinutes(raw: string | null, fallback: number): number {
  const parsed = raw == null ? Number.NaN : Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}
