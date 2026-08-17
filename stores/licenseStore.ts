// Global license state (M3-FL). Holds the validation result + loading/error so
// the license page and any future settings/activation UI share one source.
import { create } from "zustand";

import { validateLicense } from "@/lib/api/license";
import type { LicenseValidationResult } from "@/types/contracts";

interface LicenseState {
  status: LicenseValidationResult | null;
  loading: boolean;
  error: string | null;
  validate: (licenseKey: string, hardwareId: string) => Promise<void>;
  reset: () => void;
}

export const useLicenseStore = create<LicenseState>((set) => ({
  status: null,
  loading: false,
  error: null,

  validate: async (licenseKey, hardwareId) => {
    if (!licenseKey || !hardwareId) {
      set({ error: "license_key and hardware_id are required" });
      return;
    }
    set({ loading: true, error: null, status: null });
    try {
      const status = await validateLicense(licenseKey, hardwareId);
      set({ status, loading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Validation failed",
        loading: false,
      });
    }
  },

  reset: () => set({ status: null, loading: false, error: null }),
}));
