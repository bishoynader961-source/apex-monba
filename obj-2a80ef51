// Axios instance + interceptors for the Pharmacy Suite API.
// Mirrors the uniform error contract (see types/contracts.ts).
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

import { BACKEND_URL as API_BASE } from "@/lib/backend-url";

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
  const data = error.response?.data as { detail?: string; error?: { message?: string } } | undefined;
  if (data?.detail) return data.detail;
  if (data?.error?.message) return data.error.message;
  if (error.code === "ERR_NETWORK") return "Unable to reach the server";
  return "Unexpected error";
}

// Attach bearer token to outgoing requests.
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    if (typeof window !== "undefined") {
      const setupType = localStorage.getItem("db_setup_configured");
      if (setupType === "client") {
        const serverIp = localStorage.getItem("server_ip");
        if (serverIp) {
          config.baseURL = `http://${serverIp}:8000`;
        } else {
          config.baseURL = "http://127.0.0.1:8000";
        }
      }
    }

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
// On 403/500: show toast notification to user.
// Every failure is recorded in the in-memory error log (Spec 08) so the
// Support tab's diagnostic report can show recent errors. Only status,
// method, URL and message are stored — never request/response bodies.
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status;

    // Record in the diagnostic error log (skip the 401 pre-refresh attempt
    // noise? No — keep it: a failing refresh is exactly what support needs
    // to see. Bodies are never stored.)
    if (typeof window !== "undefined") {
      import("@/stores/errorLogStore").then(({ addErrorEntry }) => {
        addErrorEntry({
          timestamp: new Date().toISOString(),
          status: status ?? 0,
          method: error.config?.method?.toUpperCase() ?? "?",
          url: error.config?.url ?? "?",
          message: getErrorMessage(error),
        });
      });
    }

    // 401 Unauthorized: attempt token refresh
    if (status === 401) {
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
    }

    // 403 Forbidden or 500 Server Error: show toast to user
    if (status === 403 || status === 500) {
      const msg = getErrorMessage(error);
      if (typeof window !== "undefined") {
        // Dynamic import to avoid circular dependency
        import("@/stores/uiStore").then(({ useUiStore }) => {
          useUiStore.getState().showToast(msg, "error");
        });
      }
      return Promise.reject(new Error(msg));
    }

    // Other errors: just reject with message
    return Promise.reject(new Error(getErrorMessage(error)));
  },
);
