/**
 * Power of Attorney Hook
 *
 * CRUD-Operationen für Vollmachten (Vorsorge-, General-, Bankvollmacht, etc.)
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
  patientenverfuegung: 'Patientenverfügung',
  betreuungsverfuegung: 'Betreuungsverfügung',
  sorgerechtsverfuegung: 'Sorgerechtsverfügung',
};

/**
 * Beschreibungen der Vollmacht-Typen
 */
export const POA_TYPE_DESCRIPTIONS: Record<PowerOfAttorneyType, string> = {
  vorsorgevollmacht:
    'Ermächtigt eine Vertrauensperson, bei Geschäftsunfähigkeit alle oder bestimmte Angelegenheiten zu regeln.',
  generalvollmacht:
    'Umfassende Vertretungsbefugnis für alle Rechtsgeschäfte. Gilt auch bei Geschäftsunfähigkeit, wenn ausdrücklich geregelt.',
  bankvollmacht:
    'Ermächtigt zur Führung von Bankkonten und Durchführung von Bankgeschäften.',
  patientenverfuegung:
    'Legt fest, welche medizinischen Maßnahmen gewünscht oder abgelehnt werden.',
  betreuungsverfuegung:
    'Legt fest, wer als Betreuer eingesetzt werden soll, falls eine Betreuung notwendig wird.',
  sorgerechtsverfuegung:
    'Bestimmt, wer sich um minderjährige Kinder kümmern soll.',
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
      spaceId: _spaceId,
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
 * Löscht eine Vollmacht
 */
export function useDeletePowerOfAttorney() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ poaId, spaceId: _spaceId }: { poaId: string; spaceId: string }) =>
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
 * Löscht einen zeitgesteuerten Erben-Zugriff
 */
export function useDeleteHeirDocumentAccess() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ accessId, spaceId: _spaceId }: { accessId: string; spaceId: string }) =>
      estatePlanningService.deleteHeirDocumentAccess(accessId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.heirAccess(spaceId) });
      queryClient.invalidateQueries({ queryKey: estateQueryKeys.overview(spaceId) });
    },
  });
}

// ==================== Utility Functions ====================

/**
 * Prüft, welche wichtigen Vollmachten fehlen
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
