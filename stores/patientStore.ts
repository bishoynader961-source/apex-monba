// Global patient state (F3). Backs hooks/usePatients.ts so the patients page
// and POS patient-link selector share one catalog cache.
import { create } from "zustand";

import * as patientsApi from "@/lib/api/patients";
import type { PaginatedPatients, PatientRead, PatientCreate, PatientUpdate } from "@/types/contracts";

interface PatientState {
  patients: PaginatedPatients | null;
  selected: PatientRead | null;
  isLoading: boolean;
  error: string | null;
  page: number;

  loadPatients: (page?: number, q?: string) => Promise<void>;
  search: (q: string) => Promise<void>;
  getPatient: (id: number) => Promise<PatientRead>;
  createPatient: (payload: PatientCreate) => Promise<PatientRead>;
  updatePatient: (id: number, payload: PatientUpdate) => Promise<PatientRead>;
  deletePatient: (id: number) => Promise<PatientRead>;
  setSelected: (patient: PatientRead | null) => void;
  refetch: () => Promise<void>;
}

export const usePatientStore = create<PatientState>((set, get) => ({
  patients: null,
  selected: null,
  isLoading: false,
  error: null,
  page: 1,

  loadPatients: async (pageNum = 1, q) => {
    set({ isLoading: true, error: null });
    try {
      const result = await patientsApi.listPatients({ page: pageNum, q });
      set({ patients: result, page: pageNum, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to load patients",
      });
    }
  },

  search: async (q) => {
    set({ isLoading: true, error: null });
    try {
      const result = await patientsApi.listPatients({ page: 1, q });
      set({ patients: result, page: 1, isLoading: false });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to search patients",
      });
    }
  },

  getPatient: async (id) => {
    try {
      const patient = await patientsApi.getPatient(id);
      set({ selected: patient });
      return patient;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Failed to load patient" });
      throw err;
    }
  },

  createPatient: async (payload) => {
    const patient = await patientsApi.createPatient(payload);
    const current = get().patients;
    if (current) {
      set({ patients: { ...current, items: [...current.items, patient], total: current.total + 1 } });
    }
    return patient;
  },

  updatePatient: async (id, payload) => {
    const patient = await patientsApi.updatePatient(id, payload);
    const current = get().patients;
    if (current) {
      set({
        patients: {
          ...current,
          items: current.items.map((p) => (p.id === id ? patient : p)),
        },
      });
    }
    if (get().selected?.id === id) set({ selected: patient });
    return patient;
  },

  deletePatient: async (id) => {
    const patient = await patientsApi.deletePatient(id);
    const current = get().patients;
    if (current) {
      set({
        patients: {
          ...current,
          items: current.items.filter((p) => p.id !== id),
          total: current.total - 1,
        },
      });
    }
    return patient;
  },

  setSelected: (patient) => set({ selected: patient }),

  refetch: async () => {
    const { patients } = get();
    if (patients) {
      await get().loadPatients(patients.page, undefined);
    }
  },
}));
