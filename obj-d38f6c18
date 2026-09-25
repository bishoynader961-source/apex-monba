// Rx Queue store — manages the 3-tab prescription queue (Processing/Rejects/Ready)
// with pagination, filters, and status transitions.
import { create } from "zustand";

import * as rxQueueApi from "@/lib/api/rxQueue";
import type {
  PaginatedRxQueue,
  RxBulkStatusRequest,
  RxBulkStatusResult,
  RxQueueCounts,
  RxQueueFilters,
  RxQueueItem,
  RxStatusTransition,
} from "@/types/contracts";

interface RxQueueState {
  tabs: ("processing" | "rejects" | "ready")[];
  activeTab: "processing" | "rejects" | "ready";
  items: Record<"processing" | "rejects" | "ready", RxQueueItem[]>;
  total: Record<"processing" | "rejects" | "ready", number>;
  page: Record<"processing" | "rejects" | "ready", number>;
  filters: Record<"processing" | "rejects" | "ready", RxQueueFilters>;
  isLoading: Record<"processing" | "rejects" | "ready", boolean>;
  counts: RxQueueCounts | null;

  setActiveTab: (tab: "processing" | "rejects" | "ready") => void;
  fetchTab: (tab: "processing" | "rejects" | "ready", resetPage?: boolean) => Promise<void>;
  refreshAllTabs: () => Promise<void>;
  refreshCounts: () => Promise<void>;
  transitionStatus: (rxId: number, status: string) => Promise<void>;
  bulkTransition: (payload: RxBulkStatusRequest) => Promise<RxBulkStatusResult>;
}

const TABS = ["processing", "rejects", "ready"] as const;
type TabKey = (typeof TABS)[number];

function makeEmptyState<T>() {
  return {
    processing: [] as T,
    rejects: [] as T,
    ready: [] as T,
  };
}

export const useRxQueueStore = create<RxQueueState>((set, get) => ({
  tabs: [...TABS],
  activeTab: "processing",
  items: makeEmptyState<RxQueueItem[]>(),
  total: makeEmptyState<number>(),
  page: makeEmptyState<number>(),
  filters: makeEmptyState<RxQueueFilters>(),
  isLoading: makeEmptyState<boolean>(),
  counts: null,

  setActiveTab: (tab) => set({ activeTab: tab }),

  fetchTab: async (tab, resetPage = true) => {
    const state = get();
    const currentFilters = state.filters[tab];
    const page = resetPage ? 1 : state.page[tab];

    set({ isLoading: { ...state.isLoading, [tab]: true } });

    try {
      const filters: RxQueueFilters = {
        ...currentFilters,
        page,
        // Status is determined by the tab
        status: tab === "processing" ? "Pending" : tab === "rejects" ? "Rejected" : "Filled",
      };

      const result = await rxQueueApi.listRxQueue(filters);
      set({
        items: { ...state.items, [tab]: result.items },
        total: { ...state.total, [tab]: result.total },
        page: { ...state.page, [tab]: result.page },
        isLoading: { ...state.isLoading, [tab]: false },
      });
    } catch (err) {
      set({ isLoading: { ...state.isLoading, [tab]: false } });
      console.error(`Failed to fetch ${tab} queue:`, err);
    }
  },

  refreshAllTabs: async () => {
    const state = get();
    await Promise.all(state.tabs.map((tab) => state.fetchTab(tab, true)));
  },

  refreshCounts: async () => {
    try {
      const counts = await rxQueueApi.getRxQueueCounts();
      set({ counts });
    } catch (err) {
      console.error("Failed to fetch Rx queue counts:", err);
    }
  },

  transitionStatus: async (rxId, status) => {
    try {
      await rxQueueApi.transitionRxStatus(rxId, { status: status as RxStatusTransition["status"] });
      // Refresh the tab containing this Rx (we don't know which, so refresh all)
      await get().refreshAllTabs();
    } catch (err) {
      console.error("Failed to transition Rx status:", err);
      throw err;
    }
  },

  bulkTransition: async (payload) => {
    try {
      const result = await rxQueueApi.bulkTransitionStatus(payload);
      await get().refreshAllTabs();
      return result;
    } catch (err) {
      console.error("Failed to bulk transition Rx status:", err);
      throw err;
    }
  },
}));

// Selector for the current tab's items
export const useRxQueueItems = (tab: "processing" | "rejects" | "ready") =>
  useRxQueueStore((s) => s.items[tab]);

export const useRxQueueTotal = (tab: "processing" | "rejects" | "ready") =>
  useRxQueueStore((s) => s.total[tab]);

export const useRxQueuePage = (tab: "processing" | "rejects" | "ready") =>
  useRxQueueStore((s) => s.page[tab]);

export const useRxQueueLoading = (tab: "processing" | "rejects" | "ready") =>
  useRxQueueStore((s) => s.isLoading[tab]);

export const useRxQueueActiveTab = () =>
  useRxQueueStore((s) => s.activeTab);

export const useRxQueueCounts = () =>
  useRxQueueStore((s) => s.counts);