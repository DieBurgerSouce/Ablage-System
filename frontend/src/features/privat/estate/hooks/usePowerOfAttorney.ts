/**
 * Power of Attorney Hook
 *
 * CRUD-Operationen fuer Vollmachten (Vorsorge-, General-, Bankvollmacht, etc.)
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import {
  estatePlanningService,
  type PowerOfAttorney,
  type PowerOfAttorneyCreate,
  type PowerOfAttorneyUpdate,
  type PowerOfAttorneyType,
  type HeirDocumentAccess,
  type HeirDocumentAccessCreate,
} from '@/lib/api/services/estate-planning';
import { estateQueryKeys } from './useEstateOverview';

// ==================== Constants ====================

/**
 * Vollmacht-Typen mit deutschen Labels
 */
export const POA_TYPE_LABELS: Record<PowerOfAttorneyType, string> = {
  vorsorgevollmacht: 'Vorsorgevollmacht',
  generalvollmacht: 'Generalvollmacht',
  bankvollmacht: 'Bankvollmacht',
  patientenverfuegung: 'Patientenverfuegung',
  betreuungsverfuegung: 'Betreuungsverfuegung',
  sorgerechtsverfuegung: 'Sorgerechtsverfuegung',
};

/**
 * Beschreibungen der Vollmacht-Typen
 */
export const POA_TYPE_DESCRIPTIONS: Record<PowerOfAttorneyType, string> = {
  vorsorgevollmacht:
    'Ermaechtigt eine Vertrauensperson, bei Geschaeftsunfaehigkeit alle oder bestimmte Angelegenheiten zu regeln.',
  generalvollmacht:
    'Umfassende Vertretungsbefugnis fuer alle Rechtsgeschaefte. Gilt auch bei Geschaeftsunfaehigkeit, wenn ausdruecklich geregelt.',
  bankvollmacht:
    'Ermaechtigt zur Fuehrung von Bankkonten und Durchfuehrung von Bankgeschaeften.',
  patientenverfuegung:
    'Legt fest, welche medizinischen Massnahmen gewuenscht oder abgelehnt werden.',
  betreuungsverfuegung:
    'Legt fest, wer als Betreuer eingesetzt werden soll, falls eine Betreuung notwendig wird.',
  sorgerechtsverfuegung:
    'Bestimmt, wer sich um minderjaehrige Kinder kuemmern soll.',
};

/**
 * Empfohlene Vollmachten
 */
export const ESSENTIAL_POAS: PowerOfAttorneyType[] = [
  'vorsorgevollmacht',
  'patientenverfuegung',
  'bankvollmacht',
];

// ==================== Query Hooks ====================

/**
 * Listet alle Vollmachten eines Space
 */
export function usePowersOfAttorney(
  spaceId: string,
  options?: Omit<UseQueryOptions<PowerOfAttorney[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.powersOfAttorney(spaceId),
    queryFn: () => estatePlanningService.listPowersOfAttorney(spaceId),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}

/**
 * Listet alle zeitgesteuerten Erben-Zugriffe
 */
export function useHeirDocumentAccess(
  spaceId: string,
  options?: Omit<UseQueryOptions<HeirDocumentAccess[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: estateQueryKeys.heirAccess(spaceId),
    queryFn: () => estatePlanningService.listHeirDocumentAccess(spaceId),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Erstellt eine neue Vollmacht
 */
export function useCreatePowerOfAttorney() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PowerOfAttorneyCreate }) =>
      estatePlanningService.createPowerOfAttorney(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.powersOfAttorney(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

/**
 * Aktualisiert eine Vollmacht
 */
export function useUpdatePowerOfAttorney() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      poaId,
      data,
      spaceId,
    }: {
      poaId: string;
      data: PowerOfAttorneyUpdate;
      spaceId: string;
    }) => estatePlanningService.updatePowerOfAttorney(poaId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.powersOfAttorney(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

/**
 * Loescht eine Vollmacht
 */
export function useDeletePowerOfAttorney() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ poaId, spaceId }: { poaId: string; spaceId: string }) =>
      estatePlanningService.deletePowerOfAttorney(poaId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.powersOfAttorney(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

/**
 * Erstellt einen zeitgesteuerten Erben-Zugriff
 */
export function useCreateHeirDocumentAccess() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: HeirDocumentAccessCreate }) =>
      estatePlanningService.createHeirDocumentAccess(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.heirAccess(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

/**
 * Loescht einen zeitgesteuerten Erben-Zugriff
 */
export function useDeleteHeirDocumentAccess() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ accessId, spaceId }: { accessId: string; spaceId: string }) =>
      estatePlanningService.deleteHeirDocumentAccess(accessId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.heirAccess(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

// ==================== Utility Functions ====================

/**
 * Prueft, welche wichtigen Vollmachten fehlen
 */
export function getMissingEssentialPoas(existingPoas: PowerOfAttorney[]): PowerOfAttorneyType[] {
  const activeTypes = new Set(
    existingPoas.filter((p) => p.isActive).map((p) => p.poaType)
  );

  return ESSENTIAL_POAS.filter((type) => !activeTypes.has(type));
}

/**
 * Formatiert das Vollmacht-Datum
 */
export function formatPoaDate(dateString?: string): string {
  if (!dateString) return 'Nicht angegeben';
  return new Date(dateString).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}
