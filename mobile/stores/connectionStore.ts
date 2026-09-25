import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "mobile_connection";

export interface ConnectionState {
  desktopIp: string | null;
  authToken: string | null;
  isConnected: boolean;
  setConnection: (ip: string, token: string) => Promise<void>;
  clearConnection: () => Promise<void>;
  hydrate: () => Promise<void>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  desktopIp: null,
  authToken: null,
  isConnected: false,

  setConnection: async (ip: string, token: string) => {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ desktopIp: ip, authToken: token }));
    set({ desktopIp: ip, authToken: token, isConnected: true });
  },

  clearConnection: async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    set({ desktopIp: null, authToken: null, isConnected: false });
  },

  hydrate: async () => {
    try {
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      if (stored) {
        const { desktopIp, authToken } = JSON.parse(stored);
        if (desktopIp && authToken) {
          set({ desktopIp, authToken, isConnected: true });
        }
      }
    } catch {
      // Ignore parse errors
    }
  },
}));