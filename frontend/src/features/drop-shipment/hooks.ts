/**
 * Streckengeschäft React Hooks
 * 
 * TanStack Query hooks for drop shipment / triangular transaction management.
 * Provides data fetching, mutations, and cache management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dropShipmentApi } from './api';
import type {
  DropShipmentListFilter,
  ClassifyDocumentRequest,
  ConfirmClassificationRequest,
  OverrideClassificationRequest,
  LinkProofDocumentRequest,
  DatevExportRequest,
  BulkActionRequest,
} from './types';

// Re-export query keys for external use
export type { DropShipmentListFilter } from './types';

// ============================================================================
// QUERY KEYS
// ============================================================================

export const dropShipmentKeys = {
  all: ['drop-shipments'] as const,
  lists: () => [...dropShipmentKeys.all, 'list'] as const,
  list: (filter?: DropShipmentListFilter) => [...dropShipmentKeys.lists(), filter] as const,
  details: () => [...dropShipmentKeys.all, 'detail'] as const,
  detail: (id: string) => [...dropShipmentKeys.details(), id] as const,
  stats: () => [...dropShipmentKeys.all, 'stats'] as const,
  zmPending: () => [...dropShipmentKeys.all, 'zm-pending'] as const,
  relatedDocs: (id: string) => [...dropShipmentKeys.all, 'related-docs', id] as const,
};

// ============================================================================
// QUERIES
// ============================================================================

/**
 * Hook für Streckengeschäft-Liste mit Filtern
 */
export function useDropShipmentList(filter?: DropShipmentListFilter) {
  return useQuery({
    queryKey: dropShipmentKeys.list(filter),
    queryFn: () => dropShipmentApi.list(filter),
    staleTime: 30_000, // 30 Sekunden
  });
}

/**
 * Hook für einzelne Klassifikation mit allen Details
 */
export function useDropShipmentDetail(id: string | undefined) {
  return useQuery({
    queryKey: dropShipmentKeys.detail(id!),
    queryFn: () => dropShipmentApi.getById(id!),
    enabled: !!id,
    staleTime: 60_000, // 1 Minute
  });
}

/**
 * Hook für Dashboard-Statistiken
 */
export function useDropShipmentStats() {
  return useQuery({
    queryKey: dropShipmentKeys.stats(),
    queryFn: () => dropShipmentApi.getDashboardStats(),
    staleTime: 60_000, // 1 Minute
    refetchInterval: 5 * 60_000, // Alle 5 Minuten aktualisieren
  });
}

/**
 * Hook für ZM-relevante offene Meldungen
 */
export function useZmPending() {
  return useQuery({
    queryKey: dropShipmentKeys.zmPending(),
    queryFn: () => dropShipmentApi.getZmPending(),
    staleTime: 60_000,
  });
}

/**
 * Hook für verknüpfte Dokumente (Dokumentenfluss)
 */
export function useRelatedDocuments(classificationId: string | undefined) {
  return useQuery({
    queryKey: dropShipmentKeys.relatedDocs(classificationId!),
    queryFn: () => dropShipmentApi.getRelatedDocuments(classificationId!),
    enabled: !!classificationId,
  });
}

// ============================================================================
// MUTATIONS
// ============================================================================

/**
 * Hook für automatische Klassifikation eines Dokuments
 */
export function useClassifyDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: ClassifyDocumentRequest) => 
      dropShipmentApi.classifyDocument(request),
    onSuccess: (data) => {
      // Cache mit neuer Klassifikation aktualisieren
      queryClient.setQueryData(
        dropShipmentKeys.detail(data.classification.id),
        data.classification
      );
      // Listen invalidieren
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.stats() });
    },
  });
}

/**
 * Hook für manuelle Bestätigung
 */
export function useConfirmClassification() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: ConfirmClassificationRequest) => 
      dropShipmentApi.confirm(request),
    onSuccess: (data, variables) => {
      // Detail-Cache aktualisieren
      queryClient.setQueryData(
        dropShipmentKeys.detail(variables.classificationId),
        data
      );
      // Listen invalidieren
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.stats() });
    },
  });
}

/**
 * Hook für manuelle Korrektur/Override
 */
export function useOverrideClassification() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: OverrideClassificationRequest) => 
      dropShipmentApi.override(request),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(
        dropShipmentKeys.detail(variables.classificationId),
        data
      );
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.stats() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.zmPending() });
    },
  });
}

/**
 * Hook für Belegnachweis verknüpfen
 */
export function useLinkProofDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: LinkProofDocumentRequest) => 
      dropShipmentApi.linkProofDocument(request),
    onSuccess: (_data, variables) => {
      // Detail neu laden für aktualisierte Belege
      queryClient.invalidateQueries({ 
        queryKey: dropShipmentKeys.detail(variables.classificationId) 
      });
    },
  });
}

/**
 * Hook für Belegnachweis entfernen
 */
export function useUnlinkProofDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ classificationId, proofDocumentId }: { 
      classificationId: string; 
      proofDocumentId: string;
    }) => dropShipmentApi.unlinkProofDocument(classificationId, proofDocumentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: dropShipmentKeys.detail(variables.classificationId) 
      });
    },
  });
}

/**
 * Hook für ZM-Meldung markieren
 */
export function useMarkZmReported() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ classificationId, reportDate }: { 
      classificationId: string; 
      reportDate: string;
    }) => dropShipmentApi.markZmReported(classificationId, reportDate),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ 
        queryKey: dropShipmentKeys.detail(variables.classificationId) 
      });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.zmPending() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.stats() });
    },
  });
}

/**
 * Hook für DATEV-Export
 */
export function useDatevExport() {
  return useMutation({
    mutationFn: (request: DatevExportRequest) => 
      dropShipmentApi.exportDatev(request),
  });
}

/**
 * Hook für Bulk-Aktionen
 */
export function useBulkAction() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: BulkActionRequest) => 
      dropShipmentApi.bulkAction(request),
    onSuccess: () => {
      // Alles invalidieren nach Bulk-Aktion
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.all });
    },
  });
}

/**
 * Hook für Klassifikation löschen
 */
export function useDeleteClassification() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (classificationId: string) => 
      dropShipmentApi.delete(classificationId),
    onSuccess: (_data, classificationId) => {
      queryClient.removeQueries({ 
        queryKey: dropShipmentKeys.detail(classificationId) 
      });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: dropShipmentKeys.stats() });
    },
  });
}

/**
 * Hook für Dokumentenfluss-Validierung
 */
export function useValidateDocumentFlow() {
  return useMutation({
    mutationFn: (classificationId: string) => 
      dropShipmentApi.validateDocumentFlow(classificationId),
  });
}
