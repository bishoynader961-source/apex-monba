import { create } from "zustand";

import * as dashboardApi from "@/lib/api/dashboard";
import type { DashboardAnalytics } from "@/lib/api/dashboard";

/**
 * Zustand store for the dashboard analytics summary.
 * It caches the result of `getDashboardAnalytics` and exposes loading/error state.
 */
interface DashboardAnalyticsState {
  data: DashboardAnalytics | null;
  isLoading: boolean;
  error: string | null;
  fetch: () => Promise<void>;
  reset: () => void;
}

export const useDashboardAnalyticsStore = create<DashboardAnalyticsState>((set) => ({
  data: null,
  isLoading: false,
  error: null,
  fetch: async () => {
    set({ isLoading: true, error: null });
    try {
      const analytics = await dashboardApi.getDashboardAnalytics();
      set({ data: analytics, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to load dashboard analytics",
      });
    }
  },
  reset: () => set({ data: null, isLoading: false, error: null }),
}));
