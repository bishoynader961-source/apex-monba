// Global inventory state (M3-FL). Backs hooks/useInventory.ts so the dashboard
// inventory page and any future page share one catalog cache. Mutations refetch
// the list + stock levels to stay consistent.
import { create } from "zustand";

import * as inventoryApi from "@/lib/api/inventory";
import type {
  Batch,
  BatchUpdate,
  InventoryFilters,
  Medicine,
  MedicineUpdate,
  ReceiveBatch,
  StockLevel,
} from "@/types/contracts";

interface InventoryState {
  medicines: Medicine[] | null;
  stockLevels: StockLevel[] | null;
  suppliers: string[];
  filters: InventoryFilters;
  page: number;
  query: string | null;
  isLoading: boolean;
  error: string | null;

  setFilters: (f: InventoryFilters) => void;
  loadSuppliers: () => Promise<void>;
  applyFilters: (filters: InventoryFilters) => Promise<void>;
  search: (q: string) => Promise<void>;
  loadStockLevels: () => Promise<void>;
  refetch: () => Promise<void>;
  receiveBatch: (payload: ReceiveBatch) => Promise<Batch>;
  adjustBatch: (id: number, payload: BatchUpdate) => Promise<Batch>;
  updateMedicine: (id: number, payload: MedicineUpdate) => Promise<Medicine>;
  deleteMedicine: (id: number) => Promise<void>;
}

export const useInventoryStore = create<InventoryState>((set, get) => {
  const fetchMedicines = async () => {
    const { filters, page, query } = get();
    const params: Record<string, string | number | boolean> = {};
    if (filters.vendor) params.vendor = filters.vendor;
    if (filters.status) params.status = filters.status;
    if (filters.lowStockOnly) params.low_stock_only = true;
    params.page = page;
    if (query) params.q = query;
    set({ isLoading: true, error: null });
    try {
      const result = await inventoryApi.listMedicines(params);
      set({ medicines: result.items, page: result.page, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to load inventory",
      });
    }
  };

  return {
    medicines: null,
    stockLevels: null,
    suppliers: [],
    filters: {},
    page: 1,
    query: null,
    isLoading: false,
    error: null,

    setFilters: (f) => set({ filters: f }),

    loadSuppliers: async () => {
      try {
        const suppliers = await inventoryApi.listSuppliers();
        set({ suppliers: suppliers.map((s) => s.name) });
      } catch (err) {
        set({ error: err instanceof Error ? err.message : "Failed to load suppliers" });
      }
    },

    applyFilters: async (filters) => {
      set({ filters, page: 1 });
      await fetchMedicines();
    },

    search: async (q) => {
      set({ query: q || null, page: 1 });
      await fetchMedicines();
    },

    loadStockLevels: async () => {
      try {
        const levels = await inventoryApi.getStockLevels();
        set({ stockLevels: levels });
      } catch {
        set({ stockLevels: null });
      }
    },

    refetch: async () => {
      await fetchMedicines();
      await get().loadStockLevels();
    },

    receiveBatch: async (payload) => {
      const batch = await inventoryApi.receiveBatch(payload);
      await get().refetch();
      return batch;
    },

    adjustBatch: async (id, payload) => {
      const batch = await inventoryApi.adjustBatch(id, payload);
      await get().refetch();
      return batch;
    },

    updateMedicine: async (id, payload) => {
      const medicine = await inventoryApi.updateMedicine(id, payload);
      await get().refetch();
      return medicine;
    },

    deleteMedicine: async (id) => {
      await inventoryApi.deleteMedicine(id);
      await get().refetch();
    },
  };
});
