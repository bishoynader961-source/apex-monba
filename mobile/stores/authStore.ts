import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import * as LocalAuthentication from "expo-local-authentication";
import * as api from "../lib/api/auth";
import {
  clearStoredTokens,
  getStoredAccessToken,
  storeTokens,
} from "../lib/api/client";
import { getSettingsValue, parseTimeoutMinutes } from "../lib/api/settings";
import { getStoredDeviceId } from "../lib/deviceId";
import type { CurrentUser, Token, LicenseValidationResult } from "../types/contracts";

const GRACE_PERIOD_DAYS = 7;
const BIOMETRICS_ENABLED_KEY = "ph_biometrics_enabled";

// Defaults mirror the desktop sessionStore (stores/sessionStore.ts) and the
// backend seeds (seed_service._DEFAULT_SESSION_SETTINGS). Runtime values come
// from the SystemSetting table so a desktop admin change applies to mobile.
const DEFAULT_IDLE_MINUTES = 15;
const DEFAULT_ABSOLUTE_MINUTES = 480;

export interface SessionTimeouts {
  idleMinutes: number;
  absoluteMinutes: number;
}

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
  // ── Session timeout (Step 1.3 — same minute values as desktop) ──
  timeouts: SessionTimeouts;
  lastActivityAt: number;
  /** Epoch bumped on every session (re)start/expire — screens can key on it. */
  sessionEpoch: number;
  /** Wall-clock deadline for the absolute timeout; null when logged out. */
  sessionDeadlineAt: number | null;
  // ── Biometric unlock (Step 1.3) ──
  biometricsEnabled: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithPin: (username: string, pin: string) => Promise<void>;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  initialize: () => Promise<void>;
  checkLicense: () => Promise<void>;
  validateLicense: (licenseKey: string) => Promise<LicenseValidationResult>;
  clearLicense: () => Promise<void>;
  loadSessionSettings: () => Promise<void>;
  noteActivity: () => void;
  startSessionWatch: (intervalMs?: number) => () => void;
  expireSession: () => Promise<void>;
  enableBiometrics: () => Promise<void>;
  disableBiometrics: () => Promise<void>;
  /** Returns true when a live session was unlocked via biometrics. */
  unlockWithBiometrics: () => Promise<boolean>;
}

let watcherTimer: ReturnType<typeof setInterval> | null = null;

function sessionDeadlines(absoluteMinutes: number): { lastActivityAt: number; sessionDeadlineAt: number } {
  const now = Date.now();
  return { lastActivityAt: now, sessionDeadlineAt: now + absoluteMinutes * 60_000 };
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  license: { status: "no_license", loading: false },
  loading: false,
  initialized: false,
  timeouts: { idleMinutes: DEFAULT_IDLE_MINUTES, absoluteMinutes: DEFAULT_ABSOLUTE_MINUTES },
  lastActivityAt: 0,
  sessionEpoch: 0,
  sessionDeadlineAt: null,
  biometricsEnabled: false,

  initialize: async () => {
    if (get().initialized) return;
    await Promise.all([get().hydrate(), get().checkLicense(), get().loadSessionSettings()]);
  },

  login: async (username, password) => {
    set({ loading: true });
    try {
      const token = await api.login({ username, password });
      // JWT + refresh live ONLY in SecureStore (Keychain/Keystore) — never in
      // AsyncStorage, which is plain unencrypted disk storage.
      await storeTokens(token.access_token, token.refresh_token);
      const user = await api.getCurrentUser();
      set((s) => ({
        token,
        user,
        loading: false,
        sessionEpoch: s.sessionEpoch + 1,
        ...sessionDeadlines(get().timeouts.absoluteMinutes),
      }));
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  loginWithPin: async (username, pin) => {
    set({ loading: true });
    try {
      const token = await api.loginWithPin({ username, pin });
      await storeTokens(token.access_token, token.refresh_token);
      const user = await api.getCurrentUser();
      set((s) => ({
        token,
        user,
        loading: false,
        sessionEpoch: s.sessionEpoch + 1,
        ...sessionDeadlines(get().timeouts.absoluteMinutes),
      }));
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  refresh: async () => {
    const refreshToken = await SecureStore.getItemAsync("ph_refresh_token");
    if (!refreshToken) {
      await get().logout();
      return;
    }
    try {
      const token = await api.refresh(refreshToken);
      await SecureStore.setItemAsync("ph_access_token", token.access_token);
      // Only overwrite the refresh token when the server rotated it.
      if (token.refresh_token) {
        await SecureStore.setItemAsync("ph_refresh_token", token.refresh_token);
      }
      const user = await api.getCurrentUser();
      set((s) => ({
        token,
        user,
        sessionEpoch: s.sessionEpoch + 1,
        ...sessionDeadlines(get().timeouts.absoluteMinutes),
      }));
    } catch {
      await clearStoredTokens();
      set({ token: null, user: null, sessionDeadlineAt: null });
    }
  },

  logout: async () => {
    // Drop the local session FIRST: api.logout() can itself 401 (session
    // already invalid), which would re-enter logout through the unauthorized
    // callback. With user=null the callback no-ops — no loop possible.
    set((s) => ({ token: null, user: null, sessionDeadlineAt: null, sessionEpoch: s.sessionEpoch + 1 }));
    try {
      await api.logout();
    } catch {
      /* ignore — local teardown must proceed regardless */
    }
    await clearStoredTokens();
    // Remove legacy AsyncStorage tokens from pre-1.3 builds, if any survived.
    await AsyncStorage.removeItem("access_token");
    await AsyncStorage.removeItem("refresh_token");
  },

  hydrate: async () => {
    // One-time migration: pre-Step-1.3 builds stored tokens in AsyncStorage.
    // Move them into SecureStore and scrub the plaintext copies.
    const legacyAccess = await AsyncStorage.getItem("access_token");
    const legacyRefresh = await AsyncStorage.getItem("refresh_token");
    if (legacyAccess || legacyRefresh) {
      if (legacyAccess) await SecureStore.setItemAsync("ph_access_token", legacyAccess);
      if (legacyRefresh) await SecureStore.setItemAsync("ph_refresh_token", legacyRefresh);
      await AsyncStorage.removeItem("access_token");
      await AsyncStorage.removeItem("refresh_token");
    }

    const [accessToken, refreshToken] = await Promise.all([
      SecureStore.getItemAsync("ph_access_token"),
      SecureStore.getItemAsync("ph_refresh_token"),
    ]);
    const biometricsEnabled = (await AsyncStorage.getItem(BIOMETRICS_ENABLED_KEY)) === "true";

    if (accessToken && refreshToken) {
      try {
        const user = await api.getCurrentUser();
        set((s) => ({
          token: {
            access_token: accessToken,
            refresh_token: refreshToken,
            token_type: "bearer",
            user: {} as any,
          },
          user,
          initialized: true,
          biometricsEnabled,
          sessionEpoch: s.sessionEpoch + 1,
          ...sessionDeadlines(get().timeouts.absoluteMinutes),
        }));
      } catch {
        set({ token: null, user: null, initialized: true, biometricsEnabled });
      }
    } else {
      set({ initialized: true, biometricsEnabled });
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

  loadSessionSettings: async () => {
    const [idleRaw, absoluteRaw] = await Promise.all([
      getSettingsValue("session_idle_minutes"),
      getSettingsValue("session_absolute_minutes"),
    ]);
    const idleMinutes = parseTimeoutMinutes(idleRaw, DEFAULT_IDLE_MINUTES);
    const absoluteMinutes = parseTimeoutMinutes(absoluteRaw, DEFAULT_ABSOLUTE_MINUTES);
    set((s) => ({
      timeouts: { idleMinutes, absoluteMinutes },
      sessionDeadlineAt: s.token ? Date.now() + absoluteMinutes * 60_000 : s.sessionDeadlineAt,
    }));
  },

  noteActivity: () => {
    const { token, timeouts } = get();
    if (!token) return;
    set({ lastActivityAt: Date.now(), sessionDeadlineAt: Date.now() + timeouts.absoluteMinutes * 60_000 });
  },

  startSessionWatch: (intervalMs = 30_000) => {
    if (watcherTimer) return () => clearInterval(watcherTimer);
    watcherTimer = setInterval(() => {
      const s = get();
      if (!s.token || !s.sessionDeadlineAt) return;
      const now = Date.now();
      // Absolute expiry is checked first — it cannot be reset by activity.
      if (now >= s.sessionDeadlineAt) {
        void s.expireSession();
        return;
      }
      const idleDeadline = s.lastActivityAt + s.timeouts.idleMinutes * 60_000;
      if (now >= idleDeadline) {
        void s.expireSession();
      }
    }, intervalMs);
    return () => {
      if (watcherTimer) {
        clearInterval(watcherTimer);
        watcherTimer = null;
      }
    };
  },

  expireSession: async () => {
    // Timeout expiry is a session teardown, NOT a license/token wipe beyond
    // the auth cleanup — same contract as the desktop sessionStore.
    await get().logout();
  },

  enableBiometrics: async () => {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    const enrolled = await LocalAuthentication.isEnrolledAsync();
    if (!hasHardware || !enrolled) {
      throw new Error("Biometric authentication is not available on this device");
    }
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: "Confirm to enable biometric unlock",
    });
    if (!result.success) {
      throw new Error("Biometric confirmation failed");
    }
    await AsyncStorage.setItem(BIOMETRICS_ENABLED_KEY, "true");
    set({ biometricsEnabled: true });
  },

  disableBiometrics: async () => {
    await AsyncStorage.removeItem(BIOMETRICS_ENABLED_KEY);
    set({ biometricsEnabled: false });
  },

  unlockWithBiometrics: async () => {
    if (!(await AsyncStorage.getItem(BIOMETRICS_ENABLED_KEY))) return false;
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: "Unlock Pharmacy Suite",
    });
    if (!result.success) return false;
    // A biometric match unlocks the EXISTING SecureStore session only. After
    // logout the tokens are gone, so biometrics can never resurrect a dead
    // session — the user must password-login again first.
    const accessToken = await getStoredAccessToken();
    if (!accessToken) return false;
    const user = await api.getCurrentUser();
    set((s) => ({
      token: { access_token: accessToken, refresh_token: "", token_type: "bearer", user: {} as any },
      user,
      sessionEpoch: s.sessionEpoch + 1,
      ...sessionDeadlines(get().timeouts.absoluteMinutes),
    }));
    return true;
  },
}));
