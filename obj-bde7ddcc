import { create } from "zustand";

interface AlertCounts {
  expired: number;
  critical: number;
  warning: number;
  low_stock: number;
  total_products: number;
  checked_at: string | null;
}

interface AlertState {
  counts: AlertCounts;
  isLoading: boolean;
  lastError: string | null;
  dismissed: boolean;

  fetchAlerts: () => Promise<void>;
  dismiss: () => void;
  reset: () => void;
}

const POLL_INTERVAL_MS = 5 * 60_000;
let pollTimer: ReturnType<typeof setInterval> | null = null;

export const useAlertStore = create<AlertState>((set, get) => ({
  counts: {
    expired: 0,
    critical: 0,
    warning: 0,
    low_stock: 0,
    total_products: 0,
    checked_at: null,
  },
  isLoading: false,
  lastError: null,
  dismissed: false,

  fetchAlerts: async () => {
    set({ isLoading: true, lastError: null });
    try {
      const res = await fetch("/api/v1/alerts");
      if (!res.ok) {
        set({ isLoading: false, lastError: `HTTP ${res.status}` });
        return;
      }
      const data = await res.json();
      set({
        counts: {
          expired: data.expired ?? 0,
          critical: data.critical ?? 0,
          warning: data.warning ?? 0,
          low_stock: data.low_stock ?? 0,
          total_products: data.total_products ?? 0,
          checked_at: data.checked_at ?? null,
        },
        isLoading: false,
        dismissed: false,
      });
    } catch {
      set({ isLoading: false, lastError: "Network error" });
    }
  },

  dismiss: () => set({ dismissed: true }),
  reset: () => set({ dismissed: false }),
}));

export function startAlertPolling() {
  if (pollTimer) return;
  useAlertStore.getState().fetchAlerts();
  pollTimer = setInterval(() => {
    useAlertStore.getState().fetchAlerts();
  }, POLL_INTERVAL_MS);
}

export function stopAlertPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
