// Global demand-analytics state (M99-FL). Backs hooks/useAnalytics.ts so the
// Demand Analytics page and any future consumer share one cache of the computed
// summary + active filters. Mutations refetch to stay consistent.
import { create } from "zustand";

import * as analyticsApi from "@/lib/api/analytics";
import type { DemandAnalyticsFilters } from "@/lib/api/analytics";
import type { DemandAnalyticsSummary } from "@/types/contracts";

interface AnalyticsState {
  filters: DemandAnalyticsFilters;
  summary: DemandAnalyticsSummary | null;
  isLoading: boolean;
  error: string | null;

  setFilters: (f: Partial<DemandAnalyticsFilters>) => void;
  fetch: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_FILTERS: DemandAnalyticsFilters = {
  sort_by: "total_quantity",
  lead_time_days: 7,
};

export const useAnalyticsStore = create<AnalyticsState>((set, get) => ({
  filters: { ...DEFAULT_FILTERS },
  summary: null,
  isLoading: false,
  error: null,

  setFilters: (f) => set({ filters: { ...get().filters, ...f } }),

  fetch: async () => {
    set({ isLoading: true, error: null });
    try {
      const summary = await analyticsApi.getDemandAnalytics(get().filters);
      set({ summary, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to load analytics",
      });
    }
  },

  reset: () => set({ filters: { ...DEFAULT_FILTERS }, summary: null, error: null }),
}));
