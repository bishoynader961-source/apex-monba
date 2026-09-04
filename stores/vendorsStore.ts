import { create } from "zustand";
import {
  listVendors,
  createVendor,
  updateVendor,
  getVendorPurchases,
  receiveShipment,
  type Vendor,
  type PurchaseHistoryEntry,
  type CreateVendorPayload,
  type ReceiveShipmentPayload,
} from "@/lib/api/vendors";

interface VendorsState {
  vendors: Vendor[];
  selected: Vendor | null;
  purchases: PurchaseHistoryEntry[];
  isLoading: boolean;
  error: string | null;
  feedback: { type: "success" | "error"; msg: string } | null;

  fetchVendors: (q?: string) => Promise<void>;
  setSelected: (v: Vendor | null) => void;
  fetchPurchases: (vendorId: string) => Promise<void>;
  addVendor: (payload: CreateVendorPayload) => Promise<void>;
  editVendor: (id: string, payload: Partial<CreateVendorPayload & { is_active: number }>) => Promise<void>;
  deactivateVendor: (id: string) => Promise<void>;
  receiveStock: (payload: ReceiveShipmentPayload) => Promise<string>;
  clearFeedback: () => void;
}

export const useVendorsStore = create<VendorsState>((set, get) => ({
  vendors: [],
  selected: null,
  purchases: [],
  isLoading: false,
  error: null,
  feedback: null,

  fetchVendors: async (q?: string) => {
    set({ isLoading: true, error: null });
    try {
      const vendors = await listVendors({ active_only: false, q });
      set({ vendors });
    } catch {
      set({ error: "Failed to load vendors." });
    } finally {
      set({ isLoading: false });
    }
  },

  setSelected: (v) => set({ selected: v, purchases: [] }),

  fetchPurchases: async (vendorId: string) => {
    try {
      const purchases = await getVendorPurchases(vendorId);
      set({ purchases });
    } catch {
      set({ error: "Failed to load purchase history." });
    }
  },

  addVendor: async (payload) => {
    try {
      await createVendor(payload);
      set({ feedback: { type: "success", msg: "Vendor created successfully." } });
      await get().fetchVendors();
    } catch {
      set({ feedback: { type: "error", msg: "Failed to create vendor." } });
    }
  },

  editVendor: async (id, payload) => {
    try {
      await updateVendor(id, payload);
      set({ feedback: { type: "success", msg: "Vendor updated." } });
      await get().fetchVendors();
    } catch {
      set({ feedback: { type: "error", msg: "Failed to update vendor." } });
    }
  },

  deactivateVendor: async (id) => {
    try {
      await updateVendor(id, { is_active: 0 });
      set({ feedback: { type: "success", msg: "Vendor deactivated." } });
      await get().fetchVendors();
    } catch {
      set({ feedback: { type: "error", msg: "Failed to deactivate vendor." } });
    }
  },

  receiveStock: async (payload) => {
    try {
      const result = await receiveShipment(payload);
      set({ feedback: { type: "success", msg: result.message } });
      await get().fetchVendors();
      return result.message;
    } catch {
      set({ feedback: { type: "error", msg: "Failed to process shipment." } });
      return "";
    }
  },

  clearFeedback: () => set({ feedback: null }),
}));
