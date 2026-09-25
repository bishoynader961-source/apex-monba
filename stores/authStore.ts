import { create } from "zustand";

import { getCurrentUser } from "@/lib/api/auth";
import { initializeOfflineKey } from "@/lib/offlineKey";
import type { CurrentUser, LoginRequest, Token } from "@/types/contracts";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  setUser: (user: CurrentUser | null) => void;
  setToken: (token: string | null) => void;
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
  token: typeof window !== "undefined" ? localStorage.getItem("access_token") : null,
  user: null,
  lastPermissions: [],

  setUser: (user: CurrentUser | null) => {
    set({ user });
  },

  setToken: (token: string | null) => {
    set({ token });
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
      if (typeof window !== "undefined") {
        localStorage.setItem("access_token", token.access_token);
        localStorage.setItem("refresh_token", token.refresh_token);
        // Initialize offline encryption key from token
        initializeOfflineKey(token.access_token);
      }
    set({ token: token.access_token });
    await get().fetchCurrentUser();
  },

  logout: async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
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
