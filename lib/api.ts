// Axios instance + interceptors for the Pharmacy Suite API.
// Mirrors the uniform error contract (see types/contracts.ts).
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
});

type RequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

function getErrorMessage(error: AxiosError): string {
  const data = error.response?.data as { error?: { message?: string } } | undefined;
  if (data?.error?.message) return data.error.message;
  if (error.code === "ERR_NETWORK") return "Unable to reach the server";
  return "Unexpected error";
}

// Attach bearer token to outgoing requests.
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    const token = getToken();
    if (token) {
      const headers = config.headers as unknown as Record<string, string>;
      headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: unknown) => Promise.reject(error),
);

// On 401: call /api/auth/refresh (reads HTTP-only refresh_token cookie server-side),
// store new access_token in localStorage, then retry the request once.
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status !== 401) {
      return Promise.reject(new Error(getErrorMessage(error)));
    }
    const original = (error.config || {}) as RequestConfig;
    if (original && !original._retry) {
      original._retry = true;
      return fetch("/api/auth/refresh", { method: "POST" })
        .then((res) => res.json())
        .then((data) => {
          if (!data.access_token) throw new Error("unauthorized");
          if (typeof window !== "undefined") {
            localStorage.setItem("access_token", data.access_token);
          }
          const headers = original.headers as unknown as Record<string, string>;
          headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        })
        .catch(() => {
          clearToken();
          return Promise.reject(new Error(getErrorMessage(error)));
        });
    }
    clearToken();
    return Promise.reject(new Error(getErrorMessage(error)));
  },
);
