import { create } from "zustand";

import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/api";
import { getCurrentUser, logoutUser } from "@/lib/api/auth";
import { initializeOfflineKey } from "@/lib/offlineKey";
import type { CurrentUser, LoginRequest, Token } from "@/types/contracts";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  /** False until the reload-time silent refresh has been attempted (audit M3). */
  bootstrapped: boolean;
  setUser: (user: CurrentUser | null) => void;
  setToken: (token: string | null) => void;
  /**
   * Silent session restore after a page reload. The access token is held in
   * memory only, so a reload starts logged out; the HttpOnly refresh-token
   * cookie (set by the backend, forwarded by /api/auth/refresh) is the one
   * credential that survives, and this method exchanges it for a new access
   * token. On failure the user stays logged out and the login page takes over.
   */
  bootstrap: () => Promise<void>;
  fetchCurrentUser: () => Promise<void>;
  login: (payload: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  isAuthenticated: () => boolean;
  // For Stage 7 - permission refresh on navigation
  lastPermissions: string[];
  setLastPermissions: (perms: string[]) => void;
  permissionsChanged: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // Audit M3: memory only — null on a fresh page load, repopulated by bootstrap().
  token: getAccessToken(),
  user: null,
  bootstrapped: false,
  lastPermissions: [],

  setUser: (user: CurrentUser | null) => {
    set({ user });
  },

  setToken: (token: string | null) => {
    // Keep the Axios interceptor's source of truth in sync with the store.
    setAccessToken(token);
    set({ token });
  },

  bootstrap: async () => {
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error("no session");
      const data = await res.json();
      if (!data.access_token) throw new Error("no session");
      get().setToken(data.access_token);
      await get().fetchCurrentUser();
    } catch {
      get().setToken(null);
      set({ user: null, lastPermissions: [] });
    } finally {
      set({ bootstrapped: true });
    }
  },

  fetchCurrentUser: async () => {
    try {
      const user = await getCurrentUser();
      set({ user, lastPermissions: user?.permissions ?? [] });
    } catch {
      set({ user: null, lastPermissions: [] });
    }
  },

  login: async (payload: LoginRequest) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      const msg = data?.error || "Login failed";
      throw new Error(msg);
    }

    const token: Token = data;
    // Audit M3: the login response no longer carries the refresh token
    // (HttpOnly cookie only), and the access token is never persisted.
    setAccessToken(token.access_token);
    if (typeof window !== "undefined") {
      // Initialize offline encryption key from token
      initializeOfflineKey(token.access_token);
    }
    set({ token: token.access_token });
    await get().fetchCurrentUser();
  },

  logout: async () => {
    // Clear the HttpOnly cookies on this origin (Next.js route)...
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // Best effort: the in-memory session is dropped regardless.
    }
    // ...and on the FastAPI sidecar itself (audit M3). Requires a live access
    // token, so this is best-effort; a failure must not block the local reset.
    try {
      await logoutUser();
    } catch {
      // Ignore: cookies/local state are cleared below either way.
    }
    clearAccessToken();
    set({ token: null, user: null, lastPermissions: [] });
  },

  hasPermission: (permission: string) => {
    const perms = get().user?.permissions ?? [];
    return perms.includes("*") || perms.includes(permission);
  },

  isAuthenticated: () => get().token !== null,

  setLastPermissions: (perms: string[]) => {
    set({ lastPermissions: perms });
  },

  permissionsChanged: () => {
    const { user, lastPermissions } = get();
    const current = user?.permissions ?? [];
    return current.length !== lastPermissions.length ||
      current.some((p) => !lastPermissions.includes(p)) ||
      lastPermissions.some((p) => !current.includes(p));
  },
}));

export const useCan = (permission: string): boolean =>
  useAuthStore((s) => {
    const perms = s.user?.permissions ?? [];
    return perms.includes("*") || perms.includes(permission);
  });
