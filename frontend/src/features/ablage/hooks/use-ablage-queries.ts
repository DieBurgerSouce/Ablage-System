/**
 * Zentrale Query Hooks für Ablage Dokumenten-Verwaltung
 * Konsistente Query-Keys und wiederverwendbare Hooks
 *
 * Features:
 * - Differenzierte Stale-Times (documents: 30s, aggregations: 60s, detail: 5min)
 * - Optimistic Updates für bessere UX
 * - Infinite Query für große Listen
 * - Error Retry mit Backoff
 * - Prefetch auf Hover
 */

import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { useCallback } from 'react';
import { ablageService, AblageApiError } from '@/lib/api/services/ablage';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_SEMI_STATIC } from '@/lib/api/query-config';
import type {
  CategoryDocumentFilter,
  CategoryDocumentListResponse,
  CategoryDocumentResponse,
  PaymentStatus,
  DocumentProcessingStatus,
  DocumentSortField,
} from '../types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  documents: QUERY_VOLATILE.staleTime,     // 30s - Dokumente können sich schnell ändern
  aggregations: QUERY_STANDARD.staleTime,  // 60s - Aggregationen ändern sich seltener
  detail: QUERY_SEMI_STATIC.staleTime,     // 5min - Einzelnes Dokument ändert sich selten
} as const;

const GC_TIMES = {
  documents: QUERY_VOLATILE.gcTime,        // 5min - Listen aus Cache entfernen
  aggregations: QUERY_STANDARD.gcTime,     // 10min - Aggregationen länger halten
  detail: QUERY_SEMI_STATIC.gcTime,        // 30min - Details lange halten
} as const;

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    // Keine Retries bei 4xx Fehlern (Client-Fehler)
    if (error instanceof AblageApiError && error.statusCode) {
      if (error.statusCode >= 400 && error.statusCode < 500) {
        return false;
      }
    }
    // Maximal 3 Retries bei Server-Fehlern
    return failureCount < 3;
  },
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
} as const;

// ==================== Query Keys ====================

export const ablageQueryKeys = {
  all: ['ablage'] as const,

  // Kategorie-Dokumente
  categoryDocuments: () => [...ablageQueryKeys.all, 'category-documents'] as const,
  categoryDocumentList: (filter: Partial<CategoryDocumentFilter>) =>
    [...ablageQueryKeys.categoryDocuments(), filter] as const,

  // Aggregationen
  aggregations: () => [...ablageQueryKeys.all, 'aggregations'] as const,
  categoryAggregations: (filter: Pick<CategoryDocumentFilter, 'businessEntityId' | 'folderId' | 'category' | 'entityType'>) =>
    [...ablageQueryKeys.aggregations(), filter] as const,

  // Einzelnes Dokument
  document: (id: string) => [...ablageQueryKeys.all, 'document', id] as const,
};

// ==================== Query Hooks ====================

/**
 * Kategorie-Dokumente mit Filter und Pagination abrufen
 */
export function useCategoryDocuments(
  filter: Partial<CategoryDocumentFilter>,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ablageQueryKeys.categoryDocumentList(filter),
    queryFn: () => ablageService.getCategoryDocuments(filter),
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    enabled: options?.enabled !== false && !!filter.businessEntityId && !!filter.category,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });
}

/**
 * Infinite Query für große Dokumentenlisten (Lazy Loading)
 */
export function useCategoryDocumentsInfinite(
  filter: Omit<Partial<CategoryDocumentFilter>, 'page'>,
  options?: { enabled?: boolean }
) {
  return useInfiniteQuery({
    queryKey: [...ablageQueryKeys.categoryDocuments(), 'infinite', filter] as const,
    // B9: GET /documents/category ist 1-BASIERT (Seiten 1..totalPages)
    queryFn: ({ pageParam = 1 }) =>
      ablageService.getCategoryDocuments({ ...filter, page: pageParam }),
    getNextPageParam: (lastPage) => {
      const nextPage = lastPage.page + 1;
      return nextPage <= lastPage.totalPages ? nextPage : undefined;
    },
    initialPageParam: 1,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    enabled: options?.enabled !== false && !!filter.businessEntityId && !!filter.category,
    ...RETRY_CONFIG,
  });
}

/**
 * Aggregationen für eine Kategorie abrufen
 */
export function useCategoryAggregations(
  filter: Pick<CategoryDocumentFilter, 'businessEntityId' | 'folderId' | 'category' | 'entityType'>,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ablageQueryKeys.categoryAggregations(filter),
    queryFn: () => ablageService.getCategoryAggregations(filter),
    staleTime: STALE_TIMES.aggregations,
    gcTime: GC_TIMES.aggregations,
    enabled: options?.enabled !== false && !!filter.businessEntityId && !!filter.category,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelnes Dokument abrufen
 */
export function useDocument(documentId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ablageQueryKeys.document(documentId),
    queryFn: () => ablageService.getDocument(documentId),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!documentId,
    ...RETRY_CONFIG,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Mehrere Dokumente als ZIP herunterladen
 */
export function useBulkDownloadZip() {
  return useMutation({
    mutationFn: async ({
      documentIds,
      filename,
    }: {
      documentIds: string[];
      filename?: string;
    }) => {
      const blob = await ablageService.bulkDownloadZip(documentIds, { filename });
      const downloadFilename = filename || `dokumente_${new Date().toISOString().split('T')[0]}.zip`;
      ablageService.downloadBlob(blob, downloadFilename);
      return { success: true, count: documentIds.length };
    },
  });
}

/**
 * Dokument-Metadaten als CSV exportieren
 */
export function useBulkExportCsv() {
  return useMutation({
    mutationFn: async ({
      documentIds,
      columns,
      includeAmounts = true,
      includeDates = true,
    }: {
      documentIds: string[];
      columns?: string[];
      includeAmounts?: boolean;
      includeDates?: boolean;
    }) => {
      const blob = await ablageService.bulkExportCsv(documentIds, {
        columns,
        includeAmounts,
        includeDates,
      });
      const filename = `export_${new Date().toISOString().split('T')[0]}.csv`;
      ablageService.downloadBlob(blob, filename);
      return { success: true, count: documentIds.length };
    },
  });
}

/**
 * Mehrere Dokumente löschen (Soft-Delete)
 */
export function useBulkDelete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentIds,
      reason,
    }: {
      documentIds: string[];
      reason?: string;
    }) => {
      return ablageService.bulkDelete(documentIds, { reason });
    },
    onSuccess: () => {
      // Alle Kategorie-Dokumente und Aggregationen invalidieren
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.aggregations() });
    },
  });
}

/**
 * Dokumente in andere Kategorie verschieben
 */
export function useBulkMoveCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentIds,
      targetCategory,
    }: {
      documentIds: string[];
      targetCategory: string;
    }) => {
      return ablageService.bulkMoveCategory(documentIds, targetCategory);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.aggregations() });
    },
  });
}

/**
 * Tags für mehrere Dokumente setzen
 */
export function useBulkSetTags() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentIds,
      tags,
      mode = 'add',
    }: {
      documentIds: string[];
      tags: string[];
      mode?: 'add' | 'remove' | 'set';
    }) => {
      return ablageService.bulkSetTags(documentIds, tags, mode);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
    },
  });
}

/**
 * Zahlungsstatus eines Dokuments aktualisieren
 */
export function useUpdatePaymentStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentId,
      status,
      paidAmount,
    }: {
      documentId: string;
      status: 'offen' | 'bezahlt' | 'überfällig' | 'teilbezahlt';
      paidAmount?: number;
    }) => {
      return ablageService.updatePaymentStatus(documentId, status, paidAmount);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.document(variables.documentId) });
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.aggregations() });
    },
  });
}

/**
 * Mehrere Dokumente als bezahlt markieren
 */
export function useBulkMarkAsPaid() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentIds,
      paymentDate,
    }: {
      documentIds: string[];
      paymentDate?: string;
    }) => {
      return ablageService.bulkMarkAsPaid(documentIds, paymentDate);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
      queryClient.invalidateQueries({ queryKey: ablageQueryKeys.aggregations() });
    },
  });
}

// ==================== Optimistic Updates Helpers ====================

/**
 * Hilfsfunktion um optimistische Updates für Dokumente durchzuführen
 */
export function useOptimisticDocumentUpdate() {
  const queryClient = useQueryClient();

  const updateDocument = useCallback(
    (documentId: string, updater: (old: CategoryDocumentResponse) => CategoryDocumentResponse) => {
      // Update im Dokument-Cache
      queryClient.setQueryData<CategoryDocumentResponse>(
        ablageQueryKeys.document(documentId),
        (old) => (old ? updater(old) : old)
      );

      // Update in allen Dokumentlisten
      queryClient.setQueriesData<CategoryDocumentListResponse>(
        { queryKey: ablageQueryKeys.categoryDocuments() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              item.id === documentId ? updater(item) : item
            ),
          };
        }
      );
    },
    [queryClient]
  );

  const removeDocuments = useCallback(
    (documentIds: string[]) => {
      const idSet = new Set(documentIds);
      queryClient.setQueriesData<CategoryDocumentListResponse>(
        { queryKey: ablageQueryKeys.categoryDocuments() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.filter((item) => !idSet.has(item.id)),
            total: old.total - documentIds.length,
          };
        }
      );
    },
    [queryClient]
  );

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ablageQueryKeys.all });
  }, [queryClient]);

  const invalidateDocuments = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ablageQueryKeys.categoryDocuments() });
    queryClient.invalidateQueries({ queryKey: ablageQueryKeys.aggregations() });
  }, [queryClient]);

  return { updateDocument, removeDocuments, invalidateAll, invalidateDocuments };
}

// ==================== Combined Hooks ====================

/**
 * Filter-Parameter für Kategorie-Seite
 */
export interface CategoryPageFilter {
  businessEntityId: string;
  folderId: string;
  category: string;
  entityType: 'customer' | 'supplier';
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  processingStatus?: DocumentProcessingStatus[];
  paymentStatus?: PaymentStatus[];
  tags?: string[];
  sortBy?: DocumentSortField;
  sortOrder?: 'asc' | 'desc';
  page?: number;
  pageSize?: number;
}

/**
 * Kombinierter Hook für Kategorie-Seite
 * Lädt sowohl Dokumente als auch Aggregationen
 */
export function useCategoryPage(
  filter: CategoryPageFilter,
  options?: { enabled?: boolean }
) {
  const isEnabled = options?.enabled !== false &&
    !!filter.businessEntityId &&
    !!filter.category;

  const documentsQuery = useCategoryDocuments(filter, { enabled: isEnabled });
  const aggregationsQuery = useCategoryAggregations(
    {
      businessEntityId: filter.businessEntityId,
      folderId: filter.folderId,
      category: filter.category,
      entityType: filter.entityType,
    },
    { enabled: isEnabled }
  );

  return {
    // Daten
    documents: documentsQuery.data,
    aggregations: aggregationsQuery.data,

    // Ladezustand
    isLoading: documentsQuery.isLoading || aggregationsQuery.isLoading,
    isLoadingDocuments: documentsQuery.isLoading,
    isLoadingAggregations: aggregationsQuery.isLoading,
    isFetching: documentsQuery.isFetching || aggregationsQuery.isFetching,

    // Fehlerzustand
    isError: documentsQuery.isError || aggregationsQuery.isError,
    error: documentsQuery.error || aggregationsQuery.error,
    documentsError: documentsQuery.error,
    aggregationsError: aggregationsQuery.error,

    // Aktionen
    refetch: () => {
      documentsQuery.refetch();
      aggregationsQuery.refetch();
    },
    refetchDocuments: documentsQuery.refetch,
    refetchAggregations: aggregationsQuery.refetch,
  };
}

// ==================== Combined Mutation Hook ====================

/**
 * Kombinierter Hook für alle Dokument-Mutationen
 * Praktisch für Komponenten die mehrere Bulk-Aktionen brauchen
 */
export function useDocumentMutations() {
  const bulkDelete = useBulkDelete();
  const bulkMoveCategory = useBulkMoveCategory();
  const bulkSetTags = useBulkSetTags();
  const bulkMarkAsPaid = useBulkMarkAsPaid();
  const bulkDownloadZip = useBulkDownloadZip();
  const bulkExportCsv = useBulkExportCsv();
  const updatePaymentStatus = useUpdatePaymentStatus();
  const optimistic = useOptimisticDocumentUpdate();

  const isAnyMutating =
    bulkDelete.isPending ||
    bulkMoveCategory.isPending ||
    bulkSetTags.isPending ||
    bulkMarkAsPaid.isPending ||
    bulkDownloadZip.isPending ||
    bulkExportCsv.isPending ||
    updatePaymentStatus.isPending;

  return {
    // Mutations
    bulkDelete,
    bulkMoveCategory,
    bulkSetTags,
    bulkMarkAsPaid,
    bulkDownloadZip,
    bulkExportCsv,
    updatePaymentStatus,

    // Optimistic Updates
    ...optimistic,

    // Status
    isAnyMutating,
  };
}

// ==================== Prefetch Helpers ====================

/**
 * Prefetch für Kategorie-Dokumente (z.B. beim Hover über Kategorie-Link)
 */
export function usePrefetchCategoryDocuments() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (filter: Partial<CategoryDocumentFilter>) => {
      queryClient.prefetchQuery({
        queryKey: ablageQueryKeys.categoryDocumentList(filter),
        queryFn: () => ablageService.getCategoryDocuments(filter),
        staleTime: STALE_TIMES.documents,
      });
    },
    [queryClient]
  );

  return prefetch;
}

/**
 * Prefetch für Kategorie-Seite (Dokumente + Aggregationen)
 */
export function usePrefetchCategoryPage() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (filter: Pick<CategoryDocumentFilter, 'businessEntityId' | 'folderId' | 'category' | 'entityType'>) => {
      // Prefetch Dokumente (erste Seite; B9: 1-basiert)
      queryClient.prefetchQuery({
        queryKey: ablageQueryKeys.categoryDocumentList({ ...filter, page: 1, pageSize: 25 }),
        queryFn: () => ablageService.getCategoryDocuments({ ...filter, page: 1, pageSize: 25 }),
        staleTime: STALE_TIMES.documents,
      });

      // Prefetch Aggregationen
      queryClient.prefetchQuery({
        queryKey: ablageQueryKeys.categoryAggregations(filter),
        queryFn: () => ablageService.getCategoryAggregations(filter),
        staleTime: STALE_TIMES.aggregations,
      });
    },
    [queryClient]
  );

  return prefetch;
}

// ==================== Utility Helpers ====================

/**
 * Invalidiert alle Ablage-relevanten Queries
 * Nützlich nach großen Änderungen
 */
export function useInvalidateAblageQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ablageQueryKeys.all });
  }, [queryClient]);
}
