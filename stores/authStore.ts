import { create } from "zustand";

import { getCurrentUser } from "@/lib/api/auth";
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
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: typeof window !== "undefined" ? localStorage.getItem("access_token") : null,
  user: null,

  setUser: (user: CurrentUser | null) => {
    set({ user });
  },

  setToken: (token: string | null) => {
    set({ token });
  },

  fetchCurrentUser: async () => {
    try {
      const user = await getCurrentUser();
      set({ user });
    } catch {
      set({ user: null });
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
    set({ token: null, user: null });
  },

  hasPermission: (permission: string) =>
    (get().user?.permissions ?? []).includes(permission),

  isAuthenticated: () => get().token !== null,
}));
