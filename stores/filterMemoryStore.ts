import { create } from "zustand";

/**
 * Session-scoped per-route filter memory.
 *
 * When a user drills into a detail view (patient, batch edit, …) and comes
 * back, the list page restores its search/filters/tab instead of resetting to
 * defaults. Deliberately NOT persisted to localStorage: remembering filters
 * across app restarts is surprising; remembering them within a session is the
 * behavior users expect from a back button.
 */
interface FilterMemoryState {
  /** route.pathname -> arbitrary serializable filter state */
  memory: Record<string, unknown>;
  remember: (route: string, state: unknown) => void;
  recall: <T>(route: string) => T | null;
  forget: (route: string) => void;
}

export const useFilterMemoryStore = create<FilterMemoryState>((set, get) => ({
  memory: {},
  remember: (route, state) =>
    set((s) => ({ memory: { ...s.memory, [route]: state } })),
  recall: <T,>(route: string): T | null => {
    const v = get().memory[route];
    return (v as T) ?? null;
  },
  forget: (route) =>
    set((s) => {
      const next = { ...s.memory };
      delete next[route];
      return { memory: next };
    }),
}));
