// Compound store — manages compound formulas and dispensing.
import { create } from "zustand";

import * as compoundApi from "@/lib/api/compound";
import type {
  CompoundCreate,
  CompoundRead,
  CompoundUpdate,
  CompoundDispenseRequest,
  CompoundDispenseResult,
  CompoundPriceCalculationRequest,
  CompoundPriceCalculationResult,
} from "@/types/contracts";

interface CompoundState {
  compounds: CompoundRead[];
  selectedCompound: CompoundRead | null;
  isLoading: boolean;
  error: string | null;

  fetchCompounds: () => Promise<void>;
  getCompound: (id: number) => Promise<CompoundRead>;
  createCompound: (payload: CompoundCreate) => Promise<CompoundRead>;
  updateCompound: (id: number, payload: CompoundUpdate) => Promise<CompoundRead>;
  deleteCompound: (id: number) => Promise<void>;
  calculatePrice: (payload: CompoundPriceCalculationRequest) => Promise<CompoundPriceCalculationResult>;
  dispenseCompound: (payload: CompoundDispenseRequest) => Promise<CompoundDispenseResult>;
  setSelectedCompound: (compound: CompoundRead | null) => void;
  clearError: () => void;
}

export const useCompoundStore = create<CompoundState>((set, get) => ({
  compounds: [],
  selectedCompound: null,
  isLoading: false,
  error: null,

  fetchCompounds: async () => {
    set({ isLoading: true, error: null });
    try {
      const compounds = await compoundApi.listCompounds();
      set({ compounds, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load compounds" });
    }
  },

  getCompound: async (id) => {
    set({ isLoading: true, error: null });
    try {
      const compound = await compoundApi.getCompound(id);
      set({ selectedCompound: compound, isLoading: false });
      return compound;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to load compound" });
      throw err;
    }
  },

  createCompound: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const compound = await compoundApi.createCompound(payload);
      set((state) => ({ compounds: [compound, ...state.compounds], isLoading: false }));
      return compound;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to create compound" });
      throw err;
    }
  },

  updateCompound: async (id, payload) => {
    set({ isLoading: true, error: null });
    try {
      const compound = await compoundApi.updateCompound(id, payload);
      set((state) => ({
        compounds: state.compounds.map((c) => (c.id === id ? compound : c)),
        selectedCompound: compound,
        isLoading: false,
      }));
      return compound;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to update compound" });
      throw err;
    }
  },

  deleteCompound: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await compoundApi.deleteCompound(id);
      set((state) => ({ compounds: state.compounds.filter((c) => c.id !== id), isLoading: false }));
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to delete compound" });
      throw err;
    }
  },

  calculatePrice: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const result = await compoundApi.calculateCompoundPrice(payload);
      set({ isLoading: false });
      return result;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to calculate price" });
      throw err;
    }
  },

  dispenseCompound: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const result = await compoundApi.dispenseCompound(payload);
      set({ isLoading: false });
      return result;
    } catch (err) {
      set({ isLoading: false, error: err instanceof Error ? err.message : "Failed to dispense compound" });
      throw err;
    }
  },

  setSelectedCompound: (compound) => set({ selectedCompound: compound }),
  clearError: () => set({ error: null }),
}));

// Selectors
export const useCompounds = () => useCompoundStore((s) => s.compounds);
export const useSelectedCompound = () => useCompoundStore((s) => s.selectedCompound);
export const useCompoundLoading = () => useCompoundStore((s) => s.isLoading);
export const useCompoundError = () => useCompoundStore((s) => s.error);