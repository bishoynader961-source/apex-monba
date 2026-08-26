/**
 * Patient data hook (F3).
 *
 * Mirrors the useInventory pattern: state lives in a zustand store
 * (stores/patientStore.ts), and this hook wires up initial load, search
 * with 300ms debounce, and RBAC-gated mutation helpers.
 */
import { useEffect, useRef, useState } from "react";

import { useAuthStore, useCan } from "@/stores/authStore";
import { usePatientStore } from "@/stores/patientStore";
import type { PatientRead } from "@/types/contracts";

export function usePatients(initialQuery = "") {
  const patients = usePatientStore((s) => s.patients);
  const isLoading = usePatientStore((s) => s.isLoading);
  const error = usePatientStore((s) => s.error);
  const total = patients?.total ?? 0;
  const page = patients?.page ?? 1;

  const loadPatients = usePatientStore((s) => s.loadPatients);
  const search = usePatientStore((s) => s.search);
  const getPatient = usePatientStore((s) => s.getPatient);
  const createPatient = usePatientStore((s) => s.createPatient);
  const updatePatient = usePatientStore((s) => s.updatePatient);
  const deletePatient = usePatientStore((s) => s.deletePatient);
  const refetch = usePatientStore((s) => s.refetch);

  const hasPermission = useAuthStore((s) => s.hasPermission);
  const canWrite = hasPermission("patients.write");
  const canDelete = hasPermission("patients.delete");

  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const debouncedSearchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    void loadPatients();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = (q: string) => {
    setSearchQuery(q);
    if (debouncedSearchRef.current) clearTimeout(debouncedSearchRef.current);
    debouncedSearchRef.current = setTimeout(() => {
      void search(q);
    }, 300);
  };

  return {
    patients,
    isLoading,
    error,
    total,
    page,
    searchQuery,
    canWrite,
    canDelete,
    search: handleSearch,
    getPatient,
    createPatient,
    updatePatient,
    deletePatient,
    refetch,
  };
}

export function usePatient(id: number | null) {
  const [patient, setPatient] = useState<PatientRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id === null) {
      setPatient(null);
      return;
    }
    setLoading(true);
    setError(null);
    void usePatientStore
      .getState()
      .getPatient(id)
      .then((p) => setPatient(p))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"))
      .finally(() => setLoading(false));
  }, [id]);

  return { patient, loading, error };
}

export type { usePatientStore };
