// Global UI state (M3-FL). Foundation for theme, navigation, modal, and toast
// state shared across pages. Not yet bound to any page — pages adopt these
// fields incrementally in later UI milestones.
import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
export type ToastKind = "info" | "error" | "success";

const THEME_KEY = "theme";
const BRIGHTNESS_KEY = "ui-brightness";

export const MIN_BRIGHTNESS = 0.8;
export const MAX_BRIGHTNESS = 1.2;

function clampBrightness(v: number): number {
  if (Number.isNaN(v)) return 1;
  return Math.min(MAX_BRIGHTNESS, Math.max(MIN_BRIGHTNESS, Math.round(v * 100) / 100));
}

function getInitialBrightness(): number {
  if (typeof window === "undefined") return 1;
  const saved = Number(localStorage.getItem(BRIGHTNESS_KEY));
  return saved ? clampBrightness(saved) : 1;
}

function applyBrightness(v: number) {
  if (typeof document === "undefined") return;
  document.documentElement.style.setProperty("--user-brightness", String(v));
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark" || saved === "system") return saved;
  return "light"; // Default: light mode. Users can switch in settings.
}

/** Resolve the effective class ("light" | "dark") for a given preference. */
function resolveThemeClass(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }
  return theme;
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  const resolved = resolveThemeClass(theme);
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(resolved);
  localStorage.setItem(THEME_KEY, theme);
}

interface UIState {
  theme: Theme;
  /** User brightness multiplier (0.8–1.2); applied via the --user-brightness CSS variable. */
  brightness: number;
  sidebarOpen: boolean;
  activeTab: string;
  modal: { type?: string; payload?: unknown } | null;
  toast: { message: string; kind: ToastKind } | null;
  /** Set theme explicitly ("light" | "dark" | "system"). */
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setBrightness: (v: number) => void;
  resetBrightness: () => void;
  toggleSidebar: () => void;
  setActiveTab: (tab: string) => void;
  openModal: (modal: { type: string; payload?: unknown }) => void;
  closeModal: () => void;
  showToast: (message: string, kind?: ToastKind) => void;
  clearToast: () => void;
}

export const useUiStore = create<UIState>((set) => ({
  theme: getInitialTheme(),
  brightness: getInitialBrightness(),
  sidebarOpen: true,
  activeTab: "dashboard",
  modal: null,
  toast: null,

  setTheme: (theme) =>
    set(() => {
      applyTheme(theme);
      return { theme };
    }),
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === "dark" ? "light" : "dark";
      applyTheme(next);
      return { theme: next };
    }),
  setBrightness: (v) =>
    set(() => {
      const b = clampBrightness(v);
      applyBrightness(b);
      if (typeof window !== "undefined") localStorage.setItem(BRIGHTNESS_KEY, String(b));
      return { brightness: b };
    }),
  resetBrightness: () =>
    set(() => {
      applyBrightness(1);
      if (typeof window !== "undefined") localStorage.removeItem(BRIGHTNESS_KEY);
      return { brightness: 1 };
    }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setActiveTab: (tab) => set({ activeTab: tab }),
  openModal: (modal) => set({ modal }),
  closeModal: () => set({ modal: null }),
  showToast: (message, kind = "info") => set({ toast: { message, kind } }),
  clearToast: () => set({ toast: null }),
}));
