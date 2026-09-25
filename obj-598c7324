// EPCS store — manages EPCS prescriptions with DEA-compliant workflow.
import { create } from "zustand";

import * as epcsApi from "@/lib/api/epcs";
import type {
  EPCSPrescriptionCreate,
  EPCSPrescriptionRead,
  EPCSPrescriptionUpdate,
  EPCSPrescriptionListResponse,
  EPCSFilters,
  EPCSSignRequest,
  EPCSSignResult,
  EPCSTransmitRequest,
  EPCSTransmitResult,
  EPCSIdentityProofingRequest,
  EPCSIdentityProofingResult,
  EPCSIdentityProofingStatus,
} from "@/types/contracts";

interface EPCSState {
  items: EPCSPrescriptionRead[];
  selectedEpcs: EPCSPrescriptionRead | null;
  total: number;
  page: number;
  pageSize: number;
  filters: EPCSFilters;
  isLoading: boolean;
  error: string | null;

  fetchEpcs: () => Promise<void>;
  getEpcs: (id: number) => Promise<EPCSPrescriptionRead>;
  createEpcs: (payload: EPCSPrescriptionCreate) => Promise<EPCSPrescriptionRead>;
  updateEpcs: (id: number, payload: EPCSPrescriptionUpdate) => Promise<EPCSPrescriptionRead>;
  transitionStatus: (id: number, status: string) => Promise<EPCSPrescriptionRead>;
  signEpcs: (id: number, payload: EPCSSignRequest) => Promise<EPCSSignResult>;
  transmitEpcs: (id: number, payload: EPCSTransmitRequest) => Promise<EPCSTransmitResult>;
  getIdentityStatus: (id: number) => Promise<EPCSIdentityProofingStatus>;
  enrollIdentity: (id: number, payload: EPCSIdentityProofingRequest) => Promise<EPCSIdentityProofingResult>;
  setFilters: (filters: EPCSFilters) => void;
  setSelectedEpcs: (epcs: EPCSPrescriptionRead | null) => void;
  clearError: () => void;
}

export const useEpcsStore = create<EPCSState>((set, get) => ({
  items: [],
  selectedEpcs: null,
  total: 0,
  page: 1,
  pageSize: 50,
  filters: {
    status: undefined,
    schedule: undefined,
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

  fetchEpcs: async () => {
    set({ isLoading: true, error: null });
    try {
      const filters = get().filters;
      const params: Record<string, string | number | boolean> = {
        page: filters.page ?? 1,
        page_size: filters.page_size ?? 50,
      };
      if (filters.status) params.status = filters.status;
      if (filters.schedule) params.schedule = filters.schedule;
      if (filters.patient_id) params.patient_id = filters.patient_id;
      if (filters.prescriber_id) params.prescriber_id = filters.prescriber_id;
      if (filters.product_name) params.product_name = filters.product_name;
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;

      const result = await epcsApi.listEpcsPrescriptions(params);
      set({ items: result.items, total: result.total, page: result.page, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load EPCS prescriptions" });
    }
  },

  getEpcs: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const epcs = await epcsApi.getEpcsPrescription(id);
      set({ selectedEpcs: epcs, isLoading: false });
      return epcs;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load EPCS" });
      throw err;
    }
  },

  createEpcs: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const epcs = await epcsApi.createEpcsPrescription(payload);
      set((state) => ({ items: [epcs, ...state.items], total: state.total + 1, isLoading: false }));
      return epcs;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to create EPCS" });
      throw err;
    }
  },

  updateEpcs: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const epcs = await epcsApi.updateEpcsPrescription(id, payload);
      set((state) => ({
        items: state.items.map((e) => (e.id === id ? epcs : e)),
        selectedEpcs: epcs,
        isLoading: false,
      }));
      return epcs;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to update EPCS" });
      throw err;
    }
  },

  transitionStatus: async (id, status) => {
    set({ isLoading: true, error: null });
    try {
      const epcs = await epcsApi.transitionEpcsStatus(id, status);
      set((state) => ({
        items: state.items.map((e) => (e.id === id ? epcs : e)),
        selectedEpcs: epcs,
        isLoading: false,
      }));
      return epcs;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to transition EPCS status" });
      throw err;
    }
  },

  signEpcs: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const result = await epcsApi.signEpcsPrescription(id, payload);
      set({ isLoading: false });
      return result;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to sign EPCS" });
      throw err;
    }
  },

  transmitEpcs: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const result = await epcsApi.transmitEpcsPrescription(id, payload);
      set({ isLoading: false });
      return result;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to transmit EPCS" });
      throw err;
    }
  },

  getIdentityStatus: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const status = await epcsApi.getIdentityProofingStatus(id);
      set({ isLoading: false });
      return status;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load identity status" });
      throw err;
    }
  },

  enrollIdentity: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const result = await epcsApi.enrollIdentityProofing(id, payload);
      set({ isLoading: false });
      return result;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to enroll identity" });
      throw err;
    }
  },

  setFilters: (filters) => set({ filters, page: 1 }),

  setSelectedEpcs: (epcs) => set({ selectedEpcs: epcs }),

  clearError: () => set({ error: null }),
}));

// Selectors
export const useEpcs = () => useEpcsStore((s) => s.items);
export const useSelectedEpcs = () => useEpcsStore((s) => s.selectedEpcs);
export const useEpcsTotal = () => useEpcsStore((s) => s.total);
export const useEpcsLoading = () => useEpcsStore((s) => s.isLoading);
export const useEpcsError = () => useEpcsStore((s) => s.error);
export const useEpcsFilters = () => useEpcsStore((s) => s.filters);