import { create } from "zustand";
import * as SecureStore from "expo-secure-store";
import {
  discoverDesktopUrl,
  MANUAL_ENTRY_REQUIRED,
} from "../lib/api/baseUrl";

const STORAGE_KEY = "mobile_connection";

export interface ConnectionState {
  desktopIp: string | null;
  authToken: string | null;
  isConnected: boolean;
  // Step 1.7: resolved desktop origin (SecureStore-backed, kept in sync by
  // resolveBaseUrl). Null only before the first successful resolution.
  mobileBaseUrl: string | null;
  setConnection: (ip: string, token: string) => Promise<void>;
  clearConnection: () => Promise<void>;
  hydrate: () => Promise<void>;
  /**
   * Step 1.7 (blueprint §1.3.3): resolve the desktop origin before any
   * request that has no base URL yet. Throws MANUAL_ENTRY_REQUIRED when the
   * cached URL is missing or dead — the axios request interceptor treats
   * that sentinel as "skip this request; ConnectScreen is being shown".
   */
  resolveBaseUrl: () => Promise<string>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  desktopIp: null,
  authToken: null,
  isConnected: false,
  mobileBaseUrl: null,

  setConnection: async (ip: string, token: string) => {
    // Audit M3: the desktop auth token is a credential — it lives in the
    // hardware-backed SecureStore (same pattern as `ph_desktop_url` in
    // lib/api/baseUrl.ts), never in plain AsyncStorage.
    await SecureStore.setItemAsync(
      STORAGE_KEY,
      JSON.stringify({ desktopIp: ip, authToken: token }),
    );
    set({ desktopIp: ip, authToken: token, isConnected: true });
  },

  clearConnection: async () => {
    await SecureStore.deleteItemAsync(STORAGE_KEY);
    set({ desktopIp: null, authToken: null, isConnected: false });
  },

  hydrate: async () => {
    try {
      const stored = await SecureStore.getItemAsync(STORAGE_KEY);
      if (stored) {
        const { desktopIp, authToken } = JSON.parse(stored);
        if (desktopIp && authToken) {
          set({ desktopIp, authToken, isConnected: true });
        }
      }
    } catch {
      // Ignore parse/keystore errors: the ConnectScreen path handles recovery.
    }
  },

  resolveBaseUrl: async () => {
    const existing = get().mobileBaseUrl;
    if (existing) return existing;
    try {
      const url = await discoverDesktopUrl();
      set({ mobileBaseUrl: url, isConnected: true });
      return url;
    } catch (e) {
      // Normalize every failure (missing, dead, SecureStore error) into the
      // one sentinel RootNavigator reacts to.
      throw new Error(MANUAL_ENTRY_REQUIRED, { cause: e });
    }
  },
}));
