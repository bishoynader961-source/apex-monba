// Global UI state (M3-FL). Foundation for theme, navigation, modal, and toast
// state shared across pages. Not yet bound to any page — pages adopt these
// fields incrementally in later UI milestones.
import { create } from "zustand";

export type Theme = "light" | "dark";
export type ToastKind = "info" | "error" | "success";

interface UIState {
  theme: Theme;
  sidebarOpen: boolean;
  activeTab: string;
  modal: { type?: string; payload?: unknown } | null;
  toast: { message: string; kind: ToastKind } | null;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setActiveTab: (tab: string) => void;
  openModal: (modal: { type: string; payload?: unknown }) => void;
  closeModal: () => void;
  showToast: (message: string, kind?: ToastKind) => void;
  clearToast: () => void;
}

export const useUiStore = create<UIState>((set) => ({
  theme: "dark",
  sidebarOpen: true,
  activeTab: "dashboard",
  modal: null,
  toast: null,

  toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setActiveTab: (tab) => set({ activeTab: tab }),
  openModal: (modal) => set({ modal }),
  closeModal: () => set({ modal: null }),
  showToast: (message, kind = "info") => set({ toast: { message, kind } }),
  clearToast: () => set({ toast: null }),
}));
