import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as api from "../lib/api/auth";
import { getStoredDeviceId } from "../lib/deviceId";
import type { CurrentUser, Token, LicenseValidationResult } from "../types/contracts";

const GRACE_PERIOD_DAYS = 7;

export interface LicenseState {
  status: "valid" | "no_license" | "expired" | "grace";
  expiresAt?: string | null;
  graceUntil?: string | null;
  loading: boolean;
}

export interface AuthState {
  user: CurrentUser | null;
  token: Token | null;
  license: LicenseState;
  loading: boolean;
  initialized: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithPin: (username: string, pin: string) => Promise<void>;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  initialize: () => Promise<void>;
  checkLicense: () => Promise<void>;
  validateLicense: (licenseKey: string) => Promise<LicenseValidationResult>;
  clearLicense: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  license: { status: "no_license", loading: false },
  loading: false,
  initialized: false,

  initialize: async () => {
    if (get().initialized) return;
    await Promise.all([get().hydrate(), get().checkLicense()]);
  },

  login: async (username, password) => {
    set({ loading: true });
    try {
      const token = await api.login({ username, password });
      await AsyncStorage.setItem("access_token", token.access_token);
      await AsyncStorage.setItem("refresh_token", token.refresh_token);
      const user = await api.getCurrentUser();
      set({ token, user, loading: false });
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  loginWithPin: async (username, pin) => {
    set({ loading: true });
    try {
      const token = await api.loginWithPin({ username, pin });
      await AsyncStorage.setItem("access_token", token.access_token);
      await AsyncStorage.setItem("refresh_token", token.refresh_token);
      const user = await api.getCurrentUser();
      set({ token, user, loading: false });
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  refresh: async () => {
    const refreshToken = await AsyncStorage.getItem("refresh_token");
    if (!refreshToken) {
      get().logout();
      return;
    }
    try {
      const token = await api.refresh(refreshToken);
      await AsyncStorage.setItem("access_token", token.access_token);
      const user = await api.getCurrentUser();
      set({ token, user });
    } catch {
      await AsyncStorage.removeItem("access_token");
      await AsyncStorage.removeItem("refresh_token");
      set({ token: null, user: null });
    }
  },

  logout: async () => {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    await AsyncStorage.removeItem("access_token");
    await AsyncStorage.removeItem("refresh_token");
  },

  hydrate: async () => {
    const accessToken = await AsyncStorage.getItem("access_token");
    const refreshToken = await AsyncStorage.getItem("refresh_token");
    if (accessToken && refreshToken) {
      try {
        const user = await api.getCurrentUser();
        set({
          token: {
            access_token: accessToken,
            refresh_token: refreshToken,
            token_type: "bearer",
            user: {} as any,
          },
          user,
          initialized: true,
        });
      } catch {
        set({ token: null, user: null, initialized: true });
      }
    } else {
      set({ initialized: true });
    }
  },

  checkLicense: async () => {
    set((s) => ({ license: { ...s.license, loading: true } }));
    try {
      const stored = await AsyncStorage.getItem("license_status");
      const statusResp = await api.getLicenseStatus();
      const now = new Date();
      const graceMs = GRACE_PERIOD_DAYS * 24 * 3600 * 1000;

      if (statusResp.status === "valid") {
        await AsyncStorage.setItem("license_status", "valid");
        set({ license: { status: "valid", loading: false } });
      } else if (statusResp.status === "expired") {
        const graceUntil = await AsyncStorage.getItem("license_grace_until");
        if (graceUntil && new Date(graceUntil).getTime() > now.getTime()) {
          set({
            license: {
              status: "grace",
              graceUntil,
              loading: false,
            },
          });
        } else {
          const until = new Date(now.getTime() + graceMs).toISOString();
          await AsyncStorage.setItem("license_grace_until", until);
          set({
            license: {
              status: "grace",
              graceUntil: until,
              loading: false,
            },
          });
        }
      } else {
        await AsyncStorage.setItem("license_status", "no_license");
        set({ license: { status: "no_license", loading: false } });
      }
    } catch (e) {
      const graceUntil = await AsyncStorage.getItem("license_grace_until");
      if (graceUntil && new Date(graceUntil).getTime() > Date.now()) {
        set({ license: { status: "grace", graceUntil, loading: false } });
      } else if (get().user) {
        const until = new Date(Date.now() + GRACE_PERIOD_DAYS * 24 * 3600 * 1000).toISOString();
        await AsyncStorage.setItem("license_grace_until", until);
        set({ license: { status: "grace", graceUntil: until, loading: false } });
      } else {
        await AsyncStorage.removeItem("license_grace_until");
        set({ license: { status: "no_license", loading: false } });
      }
    }
  },

  validateLicense: async (licenseKey) => {
    const deviceId = await getStoredDeviceId();
    const result = await api.validateLicense(licenseKey, deviceId);
    await AsyncStorage.setItem("license_status", "valid");
    await AsyncStorage.removeItem("license_grace_until");
    set({
      license: {
        status: "valid",
        expiresAt: result.expires_at ?? null,
        loading: false,
      },
    });
    return result;
  },

  clearLicense: async () => {
    await AsyncStorage.removeItem("license_status");
    await AsyncStorage.removeItem("license_grace_until");
    set({ license: { status: "no_license", loading: false } });
  },
}));
