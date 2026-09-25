// Prior Auth store — manages PA requests with state machine workflow.
import { create } from "zustand";

import * as priorAuthApi from "@/lib/api/priorAuth";
import type {
  PriorAuthRead,
  PriorAuthFilters,
  PriorAuthListResponse,
  PriorAuthCreate,
  PriorAuthUpdate,
  PriorAuthStatusTransition,
} from "@/types/contracts";

interface PriorAuthState {
  items: PriorAuthRead[];
  selectedPA: PriorAuthRead | null;
  total: number;
  page: number;
  pageSize: number;
  filters: PriorAuthFilters;
  isLoading: boolean;
  error: string | null;

  fetchPAs: () => Promise<void>;
  getPA: (id: number) => Promise<PriorAuthRead>;
  createPA: (payload: PriorAuthCreate) => Promise<PriorAuthRead>;
  updatePA: (id: number, payload: PriorAuthUpdate) => Promise<PriorAuthRead>;
  transitionStatus: (id: number, payload: PriorAuthStatusTransition) => Promise<PriorAuthRead>;
  withdrawPA: (id: number) => Promise<PriorAuthRead>;
  setFilters: (filters: PriorAuthFilters) => void;
  setSelectedPA: (pa: PriorAuthRead | null) => void;
  clearError: () => void;
}

export const usePriorAuthStore = create<PriorAuthState>((set, get) => ({
  items: [],
  selectedPA: null,
  total: 0,
  page: 1,
  pageSize: 50,
  filters: {
    status: undefined,
    patient_id: undefined,
    prescriber_id: undefined,
    product_name: undefined,
    start_date: undefined,
    end_date: undefined,
    page: 1,
    page_size: 50,
  },
  isLoading: false,
  error: null,

  fetchPAs: async () => {
    set({ isLoading: true, error: null });
    try {
      const filters = get().filters;
      const params: Record<string, string | number | boolean> = {
        page: filters.page ?? 1,
        page_size: filters.page_size ?? 50,
      };
      if (filters.status) params.status = filters.status;
      if (filters.patient_id) params.patient_id = filters.patient_id;
      if (filters.prescriber_id) params.prescriber_id = filters.prescriber_id;
      if (filters.product_name) params.product_name = filters.product_name;
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;

      const result = await priorAuthApi.listPriorAuths(params);
      set({ items: result.items, total: result.total, page: result.page, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load PAs" });
    }
  },

  getPA: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const pa = await priorAuthApi.getPriorAuth(id);
      set({ selectedPA: pa, isLoading: false });
      return pa;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load PA" });
      throw err;
    }
  },

  createPA: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const pa = await priorAuthApi.createPriorAuth(payload);
      set((state) => ({ items: [pa, ...state.items], total: state.total + 1, isLoading: false }));
      return pa;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to create PA" });
      throw err;
    }
  },

  updatePA: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const pa = await priorAuthApi.updatePriorAuth(id, payload);
      set((state) => ({
        items: state.items.map((p) => (p.id === id ? pa : p)),
        selectedPA: pa,
        isLoading: false,
      }));
      return pa;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to update PA" });
      throw err;
    }
  },

  transitionStatus: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const pa = await priorAuthApi.transitionPriorAuthStatus(id, payload);
      set((state) => ({
        items: state.items.map((p) => (p.id === id ? pa : p)),
        selectedPA: pa,
        isLoading: false,
      }));
      return pa;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to transition PA status" });
      throw err;
    }
  },

  withdrawPA: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const pa = await priorAuthApi.withdrawPriorAuth(id);
      set((state) => ({
        items: state.items.map((p) => (p.id === id ? pa : p)),
        selectedPA: pa,
        isLoading: false,
      }));
      return pa;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to withdraw PA" });
      throw err;
    }
  },

  setFilters: (filters) => set({ filters, page: 1 }),

  setSelectedPA: (pa) => set({ selectedPA: pa }),

  clearError: () => set({ error: null }),
}));

// Selectors
export const usePriorAuths = () => usePriorAuthStore((s) => s.items);
export const useSelectedPA = () => usePriorAuthStore((s) => s.selectedPA);
export const usePATotal = () => usePriorAuthStore((s) => s.total);
export const usePALoading = () => usePriorAuthStore((s) => s.isLoading);
export const usePAError = () => usePriorAuthStore((s) => s.error);
export const usePAFilters = () => usePriorAuthStore((s) => s.filters);