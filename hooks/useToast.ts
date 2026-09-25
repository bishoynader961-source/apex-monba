"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface Toast {
  id: string;
  title: string;
  message?: string;
  variant?: "default" | "destructive" | "success";
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  toast: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: string) => void;
}

const MAX_TOASTS = 5;

export const useToastStore = create<ToastState>()(
  persist(
    (set, get) => ({
      toasts: [],

      toast: (newToast) => {
        const id = Math.random().toString(36).slice(2, 9);
        const duration = newToast.duration ?? 4000;
        set((state) => ({
          toasts: [...state.toasts.slice(-(MAX_TOASTS - 1)), { ...newToast, id }],
        }));
        setTimeout(() => {
          get().dismiss(id);
        }, duration);
      },

      dismiss: (id) => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }));
      },
    }),
    {
      name: "toast-storage",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ toasts: [] }),
    }
  )
);

export function useToast() {
  const { toast, dismiss, toasts } = useToastStore();
  return { toast, dismiss, toasts };
}