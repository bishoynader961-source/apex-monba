// In-memory ring buffer of recent API errors, for the Support tab's
// "Copy Diagnostic Info" report (Spec 08). Deliberately NOT persisted to
// localStorage — session-scoped only, and contains no request/response
// bodies, so it cannot capture patient data or credentials.
import { create } from "zustand";

export interface ErrorEntry {
  timestamp: string;
  status: number;
  method: string;
  url: string;
  message: string;
}

interface ErrorLogState {
  entries: ErrorEntry[];
  addEntry: (entry: ErrorEntry) => void;
  getRecent: (n?: number) => ErrorEntry[];
  clear: () => void;
}

const MAX_ENTRIES = 50;

export const useErrorLogStore = create<ErrorLogState>()((set, get) => ({
  entries: [],
  addEntry: (entry) =>
    set((state) => ({
      entries: [entry, ...state.entries].slice(0, MAX_ENTRIES),
    })),
  getRecent: (n = 5) => get().entries.slice(0, n),
  clear: () => set({ entries: [] }),
}));

// Helper for use outside React components (e.g. axios interceptors).
export const getRecentErrors = (n = 5) =>
  useErrorLogStore.getState().getRecent(n);

export const addErrorEntry = (entry: ErrorEntry) =>
  useErrorLogStore.getState().addEntry(entry);
