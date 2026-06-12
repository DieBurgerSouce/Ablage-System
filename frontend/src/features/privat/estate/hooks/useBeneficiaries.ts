/**
 * Beneficiaries Hook
 *
 * CRUD-Operationen für Begünstigte/Erben
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import {
  estatePlanningService,
  type Beneficiary,
  type BeneficiaryCreate,
  type BeneficiaryUpdate,
  type TenYearGiftPlan,
} from '@/lib/api/services/estate-planning';
import { estateQueryKeys } from './useEstateOverview';

// ==================== Query Hooks ====================

/**
 * Listet alle Begünstigten eines Space
 */
export function useBeneficiaries(
  spaceId: string,
  options?: Omit<UseQueryOptions<Beneficiary[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.beneficiaries(spaceId),
    queryFn: () => estatePlanningService.listBeneficiaries(spaceId),
    enabled: !!spaceId,
    staleTime: 2 * 60 * 1000, // 2 Minuten
    ...options,
  });
}

/**
 * Holt den 10-Jahres-Schenkungsplan für einen Begünstigten
 */
export function useGiftPlan(
  spaceId: string,
  beneficiaryId: string,
  options?: Omit<UseQueryOptions<TenYearGiftPlan>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.giftPlan(spaceId, beneficiaryId),
    queryFn: () => estatePlanningService.getGiftPlan(spaceId, beneficiaryId),
    enabled: !!spaceId && !!beneficiaryId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Erstellt einen neuen Begünstigten
 */
export function useCreateBeneficiary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: BeneficiaryCreate }) =>
      estatePlanningService.createBeneficiary(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.beneficiaries(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.taxCalculation(spaceId) });
    },
  });
}

/**
 * Aktualisiert einen Begünstigten
 */
export function useUpdateBeneficiary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      beneficiaryId,
      data,
      spaceId: _spaceId,
    }: {
      beneficiaryId: string;
      data: BeneficiaryUpdate;
      spaceId: string;
    }) => estatePlanningService.updateBeneficiary(beneficiaryId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.beneficiaries(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.taxCalculation(spaceId) });
    },
  });
}

/**
 * Löscht einen Begünstigten
 */
export function useDeleteBeneficiary() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ beneficiaryId, spaceId: _spaceId }: { beneficiaryId: string; spaceId: string }) =>
      estatePlanningService.deleteBeneficiary(beneficiaryId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.beneficiaries(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.taxCalculation(spaceId) });
    },
  });
}

/**
 * Simuliert einen Schenkungsplan
 */
export function useSimulateGiftPlan() {
  return useMutation({
    mutationFn: ({
      spaceId,
      beneficiaryId,
      totalIntendedGift,
      existingGifts,
    }: {
      spaceId: string;
      beneficiaryId: string;
      totalIntendedGift: number;
      existingGifts?: Array<{ date: string; amount: number }>;
    }) =>
      estatePlanningService.simulateGiftPlan(spaceId, {
        beneficiaryId,
        totalIntendedGift,
        existingGifts,
      }),
  });
}
