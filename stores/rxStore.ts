// Rx workflow state machine — powers the /rx Processing Toolbar.
// Centralises patient/drug/sig/insurance selection + dispense submission.
"use client";

import { create } from "zustand";

import * as dispenseApi from "@/lib/api/dispense";
import * as dictionariesApi from "@/lib/api/dictionaries";
import * as inventoryApi from "@/lib/api/inventory";
import * as insuranceApi from "@/lib/api/insurance";
import * as patientsApi from "@/lib/api/patients";
import * as prescribersApi from "@/lib/api/prescribers";
import type {
  DispenseRead,
  InsurancePlanRead,
  InsuranceValidationResult,
  Medicine,
  PatientRead,
  PrescriberRead,
  SigCodeRead,
} from "@/types/contracts";

export type ActiveModal =
  | "newRx"
  | "refill"
  | "editRx"
  | "reverseRx"
  | "eligibility"
  | "transferRx"
  | "priceCheck"
  | "dur"
  | "fillsForRx"
  | "drugEducation"
  | null;

interface RxState {
  activeModal: ActiveModal;

  // Selections
  selectedPatient: PatientRead | null;
  selectedDrug: Medicine | null;
  selectedSigCode: SigCodeRead | null;
  selectedPrescriber: PrescriberRead | null;
  selectedInsurancePlan: InsurancePlanRead | null;
  insuranceValidation: InsuranceValidationResult | null;
  useInsurance: boolean;

  // Rx fields
  quantity: number;
  daysSupply: number | null;
  refillsAuthorized: number;
  fillDate: string;
  rxNumber: string | null;

  // Results
  lastDispenseResult: DispenseRead | null;
  isProcessing: boolean;
  error: string | null;

  // Actions
  openModal: (type: ActiveModal) => void;
  closeModal: () => void;

  setPatient: (patient: PatientRead | null) => void;
  setDrug: (drug: Medicine | null) => void;
  setSigCode: (sig: SigCodeRead | null) => void;
  setPrescriber: (prescriber: PrescriberRead | null) => void;
  setInsurancePlan: (plan: InsurancePlanRead | null) => void;
  setUseInsurance: (v: boolean) => void;

  setQuantity: (q: number) => void;
  setDaysSupply: (d: number | null) => void;
  setRefillsAuthorized: (r: number) => void;
  setFillDate: (d: string) => void;
  setRxNumber: (n: string | null) => void;

  // Async
  searchPatients: (q: string) => Promise<PatientRead[]>;
  searchDrugs: (q: string) => Promise<Medicine[]>;
  lookupNdc: (q: string) => Promise<{ found: boolean; item?: import("@/types/contracts").BatchRead | null }>;
  parseSig: (code: string) => Promise<SigCodeRead | null>;
  searchPrescribers: (q: string) => Promise<PrescriberRead[]>;
  validateInsurance: (planId: number) => Promise<InsuranceValidationResult | null>;
  fetchDispenseByRx: (rxNumber: string) => Promise<DispenseRead | null>;
  fetchFillsByRx: (rxNumber: string) => Promise<DispenseRead[]>;

  submitNewRx: () => Promise<DispenseRead>;
  submitRefill: (dispenseId: number) => Promise<DispenseRead>;
  editDispense: (dispenseId: number) => Promise<DispenseRead>;
  reverseDispense: (dispenseId: number, reason: string) => Promise<void>;
  transferDispense: (dispenseId: number, pharmacyName: string, pharmacyPhone: string, transferType: string, reason: string) => Promise<void>;

  reset: () => void;
}

const today = (): string => new Date().toISOString().split("T")[0];

const initialState = {
  activeModal: null as ActiveModal,
  selectedPatient: null as PatientRead | null,
  selectedDrug: null as Medicine | null,
  selectedSigCode: null as SigCodeRead | null,
  selectedPrescriber: null as PrescriberRead | null,
  selectedInsurancePlan: null as InsurancePlanRead | null,
  insuranceValidation: null as InsuranceValidationResult | null,
  useInsurance: false,
  quantity: 0,
  daysSupply: null as number | null,
  refillsAuthorized: 0,
  fillDate: today(),
  rxNumber: null as string | null,
  lastDispenseResult: null as DispenseRead | null,
  isProcessing: false,
  error: null as string | null,
};

export const useRxStore = create<RxState>((set, get) => ({
  ...initialState,

  openModal: (type) => set({ activeModal: type }),
  closeModal: () => set({ activeModal: null }),

  setPatient: (patient) => {
    set({ selectedPatient: patient });
    // Auto-load patient's insurance plan if bound
    if (patient?.insurance_plan_id) {
      insuranceApi.getPlan(patient.insurance_plan_id).then((plan) => {
        set({ selectedInsurancePlan: plan, useInsurance: true });
      }).catch(() => {
        set({ selectedInsurancePlan: null, useInsurance: false });
      });
    } else {
      set({ selectedInsurancePlan: null, useInsurance: false });
    }
  },
  setDrug: (drug) => set({ selectedDrug: drug }),
  setSigCode: (sig) => {
    set({ selectedSigCode: sig });
    // Auto-fill days supply from SigCode.days_accumulated if > 0
    if (sig && sig.days_accumulated && Number(sig.days_accumulated) > 0) {
      const qty = get().quantity;
      if (qty > 0) {
        set({ daysSupply: Math.ceil(Number(sig.days_accumulated) * qty) });
      }
    }
  },
  setPrescriber: (prescriber) => set({ selectedPrescriber: prescriber }),
  setInsurancePlan: (plan) => set({ selectedInsurancePlan: plan }),
  setUseInsurance: (v) => set({ useInsurance: v }),

  setQuantity: (q) => {
    set({ quantity: q });
    // Recalculate days supply if sig has days_accumulated
    const sig = get().selectedSigCode;
    if (sig && sig.days_accumulated && Number(sig.days_accumulated) > 0 && q > 0) {
      set({ daysSupply: Math.ceil(Number(sig.days_accumulated) * q) });
    }
  },
  setDaysSupply: (d) => set({ daysSupply: d }),
  setRefillsAuthorized: (r) => set({ refillsAuthorized: r }),
  setFillDate: (d) => set({ fillDate: d }),
  setRxNumber: (n) => set({ rxNumber: n }),

  // ── Async lookups ─────────────────────────────────────────────────────────
  searchPatients: async (q) => {
    try {
      return await patientsApi.searchPatients(q);
    } catch {
      return [];
    }
  },

  searchDrugs: async (q) => {
    try {
      return await inventoryApi.searchMedicines(q);
    } catch {
      return [];
    }
  },

  lookupNdc: async (q) => {
    try {
      return await dictionariesApi.ndcLookup(q);
    } catch {
      return { found: false };
    }
  },

  parseSig: async (code) => {
    try {
      const result = await dictionariesApi.parseSigCode(code);
      if (result.matched) {
        // Fetch full SigCode details
        const all = await dictionariesApi.listSigCodes();
        const match = all.find((s) => s.code === result.code);
        if (match) {
          set({ selectedSigCode: match });
          return match;
        }
      }
      return null;
    } catch {
      return null;
    }
  },

  searchPrescribers: async (q) => {
    try {
      return await prescribersApi.listPrescribers({ search: q });
    } catch {
      return [];
    }
  },

  validateInsurance: async (planId) => {
    try {
      const result = await insuranceApi.validatePlan({ plan_id: planId });
      set({ insuranceValidation: result });
      return result;
    } catch {
      set({ insuranceValidation: null });
      return null;
    }
  },

  fetchDispenseByRx: async (rxNumber) => {
    try {
      const result = await dispenseApi.getDispenseByRxNumber(rxNumber);
      set({ rxNumber: result.rx_number });
      return result;
    } catch {
      return null;
    }
  },

  fetchFillsByRx: async (rxNumber) => {
    try {
      return await dispenseApi.getDispenseFills(rxNumber);
    } catch {
      return [];
    }
  },

  // ── Submit new Rx ─────────────────────────────────────────────────────────
  submitNewRx: async () => {
    const state = get();
    if (!state.selectedPatient) throw new Error("Patient is required");
    if (!state.selectedDrug) throw new Error("Drug is required");
    if (!state.selectedSigCode) throw new Error("Sig code is required");
    if (state.quantity <= 0) throw new Error("Quantity must be greater than 0");

    set({ isProcessing: true, error: null });

    const payload = {
      patient_id: state.selectedPatient.id,
      product_name: state.selectedDrug.name,
      ndc_code: state.selectedDrug.ndc_code ?? "",
      sig_code: state.selectedSigCode.code,
      quantity: state.quantity,
      fill_date: state.fillDate,
      price_at_time: "0",
      insurance_copay: "0",
      insurance_amount: "0",
      internal_barcode: state.selectedDrug.internal_unique_barcode ?? "",
      cashier: "",
      client_tx_id: crypto.randomUUID(),
      price_code: null as string | null,
      insurance_plan_id: state.useInsurance ? (state.selectedInsurancePlan?.id ?? null) : null,
      refills_authorized: state.refillsAuthorized,
      prescriber_id: state.selectedPrescriber?.id ?? null,
      days_supply: state.daysSupply,
    };

    try {
      const result = await dispenseApi.dispense(payload);
      set({
        lastDispenseResult: result,
        rxNumber: result.rx_number,
        isProcessing: false,
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Dispense failed";
      set({ isProcessing: false, error: message });
      throw err;
    }
  },

  // ── Submit refill ─────────────────────────────────────────────────────────
  submitRefill: async (dispenseId) => {
    const state = get();
    set({ isProcessing: true, error: null });

    const payload = {
      patient_id: state.selectedPatient?.id ?? 0,
      product_name: state.selectedDrug?.name ?? "",
      ndc_code: state.selectedDrug?.ndc_code ?? "",
      sig_code: state.selectedSigCode?.code ?? "",
      quantity: state.quantity || 0,
      fill_date: state.fillDate,
      price_at_time: "0",
      insurance_copay: "0",
      insurance_amount: "0",
      internal_barcode: state.selectedDrug?.internal_unique_barcode ?? "",
      cashier: "",
      client_tx_id: crypto.randomUUID(),
    };

    try {
      const result = await dispenseApi.refillDispense(dispenseId, payload);
      set({
        lastDispenseResult: result,
        rxNumber: result.rx_number,
        isProcessing: false,
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Refill failed";
      set({ isProcessing: false, error: message });
      throw err;
    }
  },

  // ── Edit dispense ──────────────────────────────────────────────────────────
  editDispense: async (dispenseId) => {
    const state = get();
    set({ isProcessing: true, error: null });

    try {
      const result = await dispenseApi.updateDispense(dispenseId, {
        sig_code: state.selectedSigCode?.code ?? undefined,
        quantity: state.quantity || undefined,
        days_supply: state.daysSupply ?? undefined,
        refills_authorized: state.refillsAuthorized || undefined,
        prescriber_id: state.selectedPrescriber?.id ?? undefined,
        fill_date: state.fillDate || undefined,
      });
      set({
        lastDispenseResult: result,
        rxNumber: result.rx_number,
        isProcessing: false,
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Edit failed";
      set({ isProcessing: false, error: message });
      throw err;
    }
  },

  // ── Reverse (void) dispense ───────────────────────────────────────────────
  reverseDispense: async (dispenseId, reason) => {
    set({ isProcessing: true, error: null });
    try {
      await dispenseApi.reverseDispense(dispenseId, reason);
      set({ lastDispenseResult: null, rxNumber: null, isProcessing: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Reverse failed";
      set({ isProcessing: false, error: message });
      throw err;
    }
  },

  // ── Transfer dispense ─────────────────────────────────────────────────────
  transferDispense: async (dispenseId, pharmacyName, pharmacyPhone, transferType, reason) => {
    set({ isProcessing: true, error: null });
    try {
      await dispenseApi.transferDispense(dispenseId, {
        pharmacy_name: pharmacyName,
        pharmacy_phone: pharmacyPhone,
        transfer_type: transferType,
        reason,
      });
      set({ lastDispenseResult: null, rxNumber: null, isProcessing: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Transfer failed";
      set({ isProcessing: false, error: message });
      throw err;
    }
  },

  reset: () => set({ ...initialState, fillDate: today() }),
}));
