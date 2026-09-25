import AsyncStorage from "@react-native-async-storage/async-storage";
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

async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem("access_token");
}

async function clearTokens(): Promise<void> {
  await AsyncStorage.removeItem("access_token");
  await AsyncStorage.removeItem("refresh_token");
}

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
        const refreshToken = await AsyncStorage.getItem("refresh_token");
        if (!refreshToken) throw new Error("unauthorized");
        const resp = await axios.post<{ access_token: string }>(
          `${getApiBaseUrl()}/api/v1/auth/refresh`,
          { refresh_token: refreshToken },
        );
        const newToken = resp.data.access_token;
        await AsyncStorage.setItem("access_token", newToken);
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
