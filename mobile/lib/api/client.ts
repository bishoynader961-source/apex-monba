import AsyncStorage from "@react-native-async-storage/async-storage";
// Security invariant #5: JWT and refresh tokens live in the device Keychain /
// Keystore via expo-secure-store — NEVER in AsyncStorage, which is plain
// unencrypted disk storage readable by any process with file access.
import * as SecureStore from "expo-secure-store";
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { useConnectionStore } from "../../stores/connectionStore";

function getApiBaseUrl(): string {
  const state = useConnectionStore.getState();
  if (state.desktopIp && state.authToken) {
    return `http://${state.desktopIp}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.API_BASE_URL ?? "http://localhost:8000";
}

export const api: AxiosInstance = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 15000,
});

export function updateApiBaseUrl(): void {
  api.defaults.baseURL = getApiBaseUrl();
}

type RequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };

// ── Token storage: SecureStore only ─────────────────────────────────────────
// Security note: SecureStore persists via iOS Keychain / Android Keystore
// (hardware-backed where available). Keys are stable string constants.
async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync("ph_access_token");
}

async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync("ph_access_token", token);
}

async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync("ph_refresh_token");
}

async function clearTokens(): Promise<void> {
  // Both keys deleted on any auth failure — no half-cleared sessions.
  await SecureStore.deleteItemAsync("ph_access_token");
  await SecureStore.deleteItemAsync("ph_refresh_token");
}

// AsyncStorage remains for NON-sensitive configuration only (desktop IP,
// device name). Tokens must never pass through here.
export const configStorage = AsyncStorage;

function getErrorMessage(error: AxiosError): string {
  const data = error.response?.data as { error?: { message?: string } } | undefined;
  if (data?.error?.message) return data.error.message;
  if (error.code === "ERR_NETWORK" || error.code === "ECONNABORTED")
    return "Unable to reach the server";
  return "Unexpected error";
}

export interface ApiError extends Error {
  isApiError: true;
  status?: number;
  code?: string;
}

// Augment plain Errors rejected by the interceptor with the HTTP status
// so diagnostics can classify failures without parsing messages.
declare module "axios" {
  export interface AxiosError {
    status?: number;
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof Error && (err as ApiError).isApiError === true;
}

api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig): Promise<InternalAxiosRequestConfig> => {
    updateApiBaseUrl();
    const token = await getToken();
    if (token) {
      const headers = config.headers as unknown as Record<string, string>;
      headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: unknown) => Promise.reject(error),
);

let isRefreshing = false;
let failedQueue: Array<() => void> = [];

function drainQueue() {
  failedQueue.forEach((cb) => cb());
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status !== 401) {
      return Promise.reject(new Error(getErrorMessage(error)));
    }
    const original = (error.config || {}) as RequestConfig;
    if (original && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push(() => {
            api(original).then(resolve).catch(reject);
          });
        });
      }
      original._retry = true;
      isRefreshing = true;
      try {
        const refreshToken = await getRefreshToken();
        if (!refreshToken) throw new Error("unauthorized");
        const resp = await axios.post<{ access_token: string }>(
          `${getApiBaseUrl()}/api/v1/auth/refresh`,
          { refresh_token: refreshToken },
        );
        const newToken = resp.data.access_token;
        await setToken(newToken);
        const headers = original.headers as unknown as Record<string, string>;
        headers.Authorization = `Bearer ${newToken}`;
        isRefreshing = false;
        drainQueue();
        return api(original);
      } catch (refreshError) {
        isRefreshing = false;
        drainQueue();
        await clearTokens();
        return Promise.reject(new Error("unauthorized"));
      }
    }
    await clearTokens();
    return Promise.reject(new Error(getErrorMessage(error)));
  },
);
