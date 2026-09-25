import { create } from "zustand";
import * as inventoryApi from "../lib/api/inventory";
import type { ProductRead, PaginatedProducts, InventoryFilters } from "../types/contracts";

export interface InventoryState {
  products: ProductRead[];
  loading: boolean;
  total: number;
  page: number;
  filters: InventoryFilters;
  loadProducts: (params?: InventoryFilters) => Promise<void>;
  search: (query: string) => Promise<void>;
  setFilters: (filters: Partial<InventoryFilters>) => void;
  clearFilters: () => void;
  loadMore: () => Promise<void>;
}

export const useInventoryStore = create<InventoryState>((set, get) => ({
  products: [],
  loading: false,
  total: 0,
  page: 1,
  filters: {},

  loadProducts: async (params) => {
    set({ loading: true });
    try {
      const result = await inventoryApi.listProducts(params ?? get().filters);
      set({ products: result.items, total: result.total, page: result.page });
    } catch (e) {
      set({ products: [], total: 0 });
    } finally {
      set({ loading: false });
    }
  },

  search: async (query: string) => {
    set({ loading: true });
    try {
      const result = await inventoryApi.listProducts({ ...get().filters, page: 1 });
      set({ products: result.items, total: result.total, page: 1 });
    } catch {
      set({ products: [], loading: false });
    }
    set({ loading: false });
  },

  setFilters: (filters) => {
    set((state) => ({ filters: { ...state.filters, ...filters } }));
    get().loadProducts();
  },

  clearFilters: () => {
    set({ filters: {} });
    get().loadProducts();
  },

  loadMore: async () => {
    const { page, total, loading, products } = get();
    if (loading || products.length >= total) return;
    const nextPage = page + 1;
    set({ loading: true });
    try {
      const result = await inventoryApi.listProducts({ ...get().filters, page: nextPage });
      set((state) => ({
        products: [...state.products, ...result.items],
        total: result.total,
        page: result.page,
      }));
    } finally {
      set({ loading: false });
    }
  },
}));
