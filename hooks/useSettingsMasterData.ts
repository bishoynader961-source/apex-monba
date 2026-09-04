import { useQuery } from '@tanstack/react-query';
import { listSigCodes, listPriceCodes } from '@/lib/api/dictionaries';
import { listPlans } from '@/lib/api/insurance';
import { listPrescribers } from '@/lib/api/prescribers';
import type { SigCodeRead, PriceCodeRead, InsurancePlanRead, PrescriberRead } from '@/types/contracts';

export function useSigCodes() {
  return useQuery<SigCodeRead[], Error>({
    queryKey: ['sigCodes'],
    queryFn: listSigCodes,
    staleTime: 10 * 60 * 1000,
  });
}

export function usePriceCodes() {
  return useQuery<PriceCodeRead[], Error>({
    queryKey: ['priceCodes'],
    queryFn: listPriceCodes,
    staleTime: 10 * 60 * 1000,
  });
}

export function useInsurancePlans() {
  return useQuery<InsurancePlanRead[], Error>({
    queryKey: ['insurancePlans'],
    queryFn: listPlans,
    staleTime: 10 * 60 * 1000,
  });
}

export function usePrescribers() {
  return useQuery<PrescriberRead[], Error>({
    queryKey: ['prescribers'],
    queryFn: () => listPrescribers(),
    staleTime: 10 * 60 * 1000,
  });
}