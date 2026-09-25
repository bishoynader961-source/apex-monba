import { create } from "zustand";

interface RegionInfo {
  code: string;
  name: string;
  currency: string;
  currency_symbol: string;
  date_format: string;
  tax_label: string;
  default_tax_rate: number;
  supports_insurance: boolean;
  supports_workers_comp: boolean;
  rx_requires_ndc: boolean;
  language: string;
}

interface RegionState {
  region: RegionInfo | null;
  isLoading: boolean;
  detected: boolean;
  bannerDismissed: boolean;

  detect: () => Promise<void>;
  setRegion: (code: string) => Promise<void>;
  dismissBanner: () => void;
  resetBanner: () => void;
}

const STORAGE_KEY = "pharmacy_region";
const BANNER_DISMISS_KEY = "pharmacy_region_banner_dismissed";

function getCachedRegion(): RegionInfo | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function cacheRegion(region: RegionInfo) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(region));
}

function isBannerDismissedForRegion(code: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = localStorage.getItem(BANNER_DISMISS_KEY);
    if (!raw) return false;
    const dismissed: Record<string, boolean> = JSON.parse(raw);
    return dismissed[code] === true;
  } catch {
    return false;
  }
}

function setBannerDismissedForRegion(code: string, dismissed: boolean) {
  if (typeof window === "undefined") return;
  try {
    const raw = localStorage.getItem(BANNER_DISMISS_KEY);
    const data: Record<string, boolean> = raw ? JSON.parse(raw) : {};
    data[code] = dismissed;
    localStorage.setItem(BANNER_DISMISS_KEY, JSON.stringify(data));
  } catch {
    // ignore
  }
}

export const useRegionStore = create<RegionState>((set, get) => ({
  region: getCachedRegion(),
  isLoading: false,
  detected: false,
  bannerDismissed: false,

  detect: async () => {
    set({ isLoading: true });
    try {
      const res = await fetch("/api/v1/region/detect", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (res.ok) {
        const data: RegionInfo = await res.json();
        cacheRegion(data);
        const dismissed = isBannerDismissedForRegion(data.code);
        set({ region: data, detected: true, isLoading: false, bannerDismissed: dismissed });
      } else {
        set({ isLoading: false });
      }
    } catch {
      set({ isLoading: false });
    }
  },

  setRegion: async (code: string) => {
    set({ isLoading: true });
    try {
      const res = await fetch(`/api/v1/region/${code}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      if (res.ok) {
        const data: RegionInfo = await res.json();
        cacheRegion(data);
        const dismissed = isBannerDismissedForRegion(data.code);
        set({ region: data, detected: true, isLoading: false, bannerDismissed: dismissed });
      }
    } catch {
      set({ isLoading: false });
    }
  },

  dismissBanner: () => {
    const { region } = get();
    if (region) {
      setBannerDismissedForRegion(region.code, true);
    }
    set({ bannerDismissed: true });
  },

  resetBanner: () => {
    const { region } = get();
    if (region) {
      setBannerDismissedForRegion(region.code, false);
    }
    set({ bannerDismissed: false });
  },
}));
