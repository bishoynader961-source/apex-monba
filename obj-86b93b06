import { create } from "zustand";

import * as receivingApi from "@/lib/api/receiving";
import type {
  PaginatedReceivingLog,
  ReceivingLogFilters,
  ReceivingLogRead,
} from "@/types/contracts";

interface ReceivingLogState {
  entries: ReceivingLogRead[] | null;
  vendors: string[];
  total: number;
  page: number;
  pageSize: number;
  filters: ReceivingLogFilters;
  isLoading: boolean;
  error: string | null;

  setFilters: (f: Partial<ReceivingLogFilters>) => Promise<void>;
  fetchEntries: (page?: number) => Promise<void>;
  fetchVendors: () => Promise<void>;
  refetch: () => Promise<void>;
}

export const useReceivingLogStore = create<ReceivingLogState>((set, get) => ({
  entries: null,
  vendors: [],
  total: 0,
  page: 1,
  pageSize: 50,
  filters: {},
  isLoading: false,
  error: null,

  setFilters: async (f) => {
    set((s) => ({ filters: { ...s.filters, ...f }, page: 1 }));
    await get().fetchEntries(1);
  },

  fetchEntries: async (page = 1) => {
    const { filters, pageSize } = get();
    set({ isLoading: true, error: null, page });
    try {
      const result: PaginatedReceivingLog = await receivingApi.listReceivingLog({
        ...filters,
        page,
        page_size: pageSize,
      });
      set({
        entries: result.items,
        total: result.total,
        page: result.page,
        pageSize: result.page_size,
        isLoading: false,
      });
    } catch {
      set({ isLoading: false, error: "Failed to load receiving log." });
    }
  },

  fetchVendors: async () => {
    try {
      const vendors = await receivingApi.listReceivingLogVendors();
      set({ vendors });
    } catch {
      set({ vendors: [], error: "Failed to load vendor list." });
    }
  },

  refetch: async () => {
    await get().fetchEntries(get().page);
  },
}));
