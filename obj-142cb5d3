import { api } from "./client";
import type { LoginRequest, RefreshRequest, Token, CurrentUser, UserPublic, PinLoginRequest, LicenseValidationResult } from "../../types/contracts";

const AUTH_BASE = "/api/v1/auth";

export async function login(credentials: LoginRequest): Promise<Token> {
  const { data } = await api.post<Token>(`${AUTH_BASE}/login`, credentials);
  return data;
}

export async function loginWithPin(payload: PinLoginRequest): Promise<Token> {
  const { data } = await api.post<Token>(`${AUTH_BASE}/login-pin`, payload);
  return data;
}

export async function refresh(refreshToken: string): Promise<Token> {
  const { data } = await api.post<Token>(`${AUTH_BASE}/refresh`, { refresh_token: refreshToken });
  return data;
}

export async function logout(): Promise<void> {
  await api.post(`${AUTH_BASE}/logout`);
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const { data } = await api.get<CurrentUser>(`${AUTH_BASE}/me`);
  return data;
}

export async function getUsers(): Promise<UserPublic[]> {
  const { data } = await api.get<UserPublic[]>("/api/v1/users");
  return data;
}

export async function validateLicense(licenseKey: string, hardwareId: string): Promise<LicenseValidationResult> {
  const { data } = await api.post<LicenseValidationResult>(
    "/api/v1/license/validate",
    { license_key: licenseKey, hardware_id: hardwareId },
  );
  return data;
}

export async function getLicenseStatus(): Promise<{ status: string; http_status: number }> {
  const { data } = await api.get<{ status: string; http_status: number }>("/api/v1/license/status");
  return data;
}
