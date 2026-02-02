/**
 * Estate Overview Hook
 *
 * Laedt die Nachlassuebersicht mit Summary, Steuerberechnung und Schenkungsplaenen
 */

import { useQuery, type UseQueryOptions } from '@tanstack/react-query';
import {
  estatePlanningService,
  type EstateOverview,
  type EstateSummary,
} from '@/lib/api/services/estate-planning';

// ==================== Query Keys ====================

export const estateQueryKeys = {
  all: ['estate-planning'] as const,
  overview: (spaceId: string) => [...estateQueryKeys.all, 'overview', spaceId] as const,
  summary: (spaceId: string) => [...estateQueryKeys.all, 'summary', spaceId] as const,
  beneficiaries: (spaceId: string) => [...estateQueryKeys.all, 'beneficiaries', spaceId] as const,
  powersOfAttorney: (spaceId: string) => [...estateQueryKeys.all, 'poa', spaceId] as const,
  heirAccess: (spaceId: string) => [...estateQueryKeys.all, 'heir-access', spaceId] as const,
  taxCalculation: (spaceId: string) => [...estateQueryKeys.all, 'tax', spaceId] as const,
  giftPlan: (spaceId: string, beneficiaryId: string) =>
    [...estateQueryKeys.all, 'gift-plan', spaceId, beneficiaryId] as const,
};

// ==================== Overview Hook ====================

/**
 * Holt die komplette Nachlassuebersicht
 */
export function useEstateOverview(
  spaceId: string,
  options?: Omit<UseQueryOptions<EstateOverview>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.overview(spaceId),
    queryFn: () => estatePlanningService.getEstateOverview(spaceId),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}

/**
 * Holt nur die Nachlass-Zusammenfassung
 */
export function useEstateSummary(
  spaceId: string,
  options?: Omit<UseQueryOptions<EstateSummary>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.summary(spaceId),
    queryFn: () => estatePlanningService.getEstateSummary(spaceId),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}
