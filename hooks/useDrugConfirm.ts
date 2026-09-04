import { useQuery, useMutation } from '@tanstack/react-query';
import { confirmDrug } from '@/lib/api/drugConfirm';
import type { DrugConfirmResult } from '@/types/contracts';

export function useDrugConfirm(ndc: string) {
  return useQuery<DrugConfirmResult, Error>({
    queryKey: ['drugConfirm', ndc],
    queryFn: () => confirmDrug(ndc),
    enabled: ndc.length >= 11,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

export function useConfirmDrug() {
  return useMutation({
    mutationFn: confirmDrug,
  });
}