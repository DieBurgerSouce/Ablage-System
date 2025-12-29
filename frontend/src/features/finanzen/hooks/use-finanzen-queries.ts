import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { FinanceYear, FinanceAggregations } from '../types'
import {
  financeService,
  financeHistoryApi,
  financeVersionApi,
  type FinanceCategoryDocumentList,
  type FinanceCategoryAggregations,
  type FinanceCategoryDocument,
  type FinanceDocumentUploadMetadata,
  type FinanceDocumentUploadResult,
  type FinanceDocumentUpdateData,
  type FinanceDocumentDeleteResult,
  type FinanceDeadlineListResult,
  type FinanceDeadlineOptions,
  type FinanceDocumentHistoryResult,
  type FinanceHistoryItem,
  type FinanceDocumentVersionList,
  type FinanceDocumentVersion,
  type FinanceVersionCompareResult,
  type FinanceVersionRollbackResult,
} from '@/lib/api/services/finance'

// ==================== QUERY KEYS ====================

export const finanzenQueryKeys = {
  all: ['finanzen'] as const,
  years: () => [...finanzenQueryKeys.all, 'years'] as const,
  year: (yearId: string) => [...finanzenQueryKeys.years(), yearId] as const,
  overallAggregations: () => [...finanzenQueryKeys.all, 'overall-aggregations'] as const,
  yearAggregations: (yearId: string) => [...finanzenQueryKeys.all, 'year-aggregations', yearId] as const,
  categoryDocuments: () => [...finanzenQueryKeys.all, 'category-documents'] as const,
  categoryDocumentList: (filter: FinanceCategoryFilter) => [...finanzenQueryKeys.categoryDocuments(), filter] as const,
  categoryAggregations: (yearId: string, category: string) => [...finanzenQueryKeys.all, 'category-aggregations', yearId, category] as const,
  document: (documentId: string) => [...finanzenQueryKeys.all, 'document', documentId] as const,
  deadlines: (options?: FinanceDeadlineOptions) => [...finanzenQueryKeys.all, 'deadlines', options] as const,
  documentHistory: (documentId: string) => [...finanzenQueryKeys.all, 'document-history', documentId] as const,
  documentVersions: (documentId: string) => [...finanzenQueryKeys.all, 'document-versions', documentId] as const,
  documentVersion: (documentId: string, versionNumber: number) => [...finanzenQueryKeys.all, 'document-version', documentId, versionNumber] as const,
  versionCompare: (documentId: string, versionA: number, versionB: number) => [...finanzenQueryKeys.all, 'version-compare', documentId, versionA, versionB] as const,
}

// ==================== INTERFACES ====================

export interface FinanceCategoryFilter {
  yearId: string
  category: string
  search?: string
  dateFrom?: string
  dateTo?: string
  amountMin?: number
  amountMax?: number
  steuerart?: string
  sortBy: string
  sortOrder: 'asc' | 'desc'
  page: number
  pageSize: number
}

// ==================== STALE TIMES ====================

const STALE_TIMES = {
  years: 5 * 60 * 1000,           // 5 Minuten - Jahre aendern sich selten
  aggregations: 60 * 1000,        // 1 Minute
  documents: 30 * 1000,           // 30 Sekunden
}

const GC_TIMES = {
  years: 30 * 60 * 1000,          // 30 Minuten
  aggregations: 10 * 60 * 1000,   // 10 Minuten
  documents: 5 * 60 * 1000,       // 5 Minuten
}

// ==================== RETRY CONFIG ====================

/**
 * Enterprise-grade Retry-Konfiguration mit Exponential Backoff
 */
const RETRY_CONFIG = {
  retry: 3,
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
}

// ==================== QUERIES ====================

/**
 * Hook: Alle Finanz-Jahre abrufen
 */
export function useFinanceYears() {
  return useQuery({
    queryKey: finanzenQueryKeys.years(),
    queryFn: async (): Promise<FinanceYear[]> => {
      return financeService.getYears()
    },
    staleTime: STALE_TIMES.years,
    gcTime: GC_TIMES.years,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Einzelnes Finanz-Jahr abrufen
 */
export function useFinanceYear(yearId: string | undefined) {
  return useQuery({
    queryKey: finanzenQueryKeys.year(yearId || ''),
    queryFn: async (): Promise<FinanceYear | null> => {
      if (!yearId) return null
      return financeService.getYear(yearId)
    },
    enabled: !!yearId,
    staleTime: STALE_TIMES.years,
    gcTime: GC_TIMES.years,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Gesamt-Aggregationen abrufen
 */
export function useFinanceOverallAggregations() {
  return useQuery({
    queryKey: finanzenQueryKeys.overallAggregations(),
    queryFn: async (): Promise<FinanceAggregations> => {
      return financeService.getOverallAggregations()
    },
    staleTime: STALE_TIMES.aggregations,
    gcTime: GC_TIMES.aggregations,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Jahr-Aggregationen abrufen
 */
export function useFinanceYearAggregations(yearId: string | undefined) {
  return useQuery({
    queryKey: finanzenQueryKeys.yearAggregations(yearId || ''),
    queryFn: async (): Promise<FinanceAggregations | null> => {
      if (!yearId) return null
      return financeService.getYearAggregations(yearId)
    },
    enabled: !!yearId,
    staleTime: STALE_TIMES.aggregations,
    gcTime: GC_TIMES.aggregations,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Kategorie-Dokumente abrufen
 */
export function useFinanceCategoryDocuments(filter: FinanceCategoryFilter) {
  return useQuery({
    queryKey: finanzenQueryKeys.categoryDocumentList(filter),
    queryFn: async (): Promise<FinanceCategoryDocumentList> => {
      return financeService.getCategoryDocuments(
        filter.yearId,
        filter.category,
        {
          search: filter.search,
          dateFrom: filter.dateFrom,
          dateTo: filter.dateTo,
          amountMin: filter.amountMin,
          amountMax: filter.amountMax,
          steuerart: filter.steuerart,
          page: filter.page,
          pageSize: filter.pageSize,
          sortBy: filter.sortBy,
          sortOrder: filter.sortOrder,
        }
      )
    },
    enabled: !!filter.yearId && !!filter.category,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Kategorie-Aggregationen abrufen
 */
export function useFinanceCategoryAggregations(yearId: string | undefined, category: string | undefined) {
  return useQuery({
    queryKey: finanzenQueryKeys.categoryAggregations(yearId || '', category || ''),
    queryFn: async (): Promise<FinanceCategoryAggregations | null> => {
      if (!yearId || !category) return null
      return financeService.getCategoryAggregations(yearId, category)
    },
    enabled: !!yearId && !!category,
    staleTime: STALE_TIMES.aggregations,
    gcTime: GC_TIMES.aggregations,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Finanzen-Dashboard-Daten kombiniert
 */
export function useFinanceDashboard() {
  const yearsQuery = useFinanceYears()
  const aggregationsQuery = useFinanceOverallAggregations()

  return {
    years: yearsQuery.data || [],
    aggregations: aggregationsQuery.data || null,
    isLoading: yearsQuery.isLoading || aggregationsQuery.isLoading,
    isError: yearsQuery.isError || aggregationsQuery.isError,
    error: yearsQuery.error || aggregationsQuery.error,
    refetch: () => {
      yearsQuery.refetch()
      aggregationsQuery.refetch()
    },
  }
}

/**
 * Hook: Jahr-Seite-Daten kombiniert
 */
export function useFinanceYearPage(yearId: string | undefined) {
  const yearQuery = useFinanceYear(yearId)
  const aggregationsQuery = useFinanceYearAggregations(yearId)

  return {
    year: yearQuery.data || null,
    aggregations: aggregationsQuery.data || null,
    isLoading: yearQuery.isLoading || aggregationsQuery.isLoading,
    isError: yearQuery.isError || aggregationsQuery.isError,
    error: yearQuery.error || aggregationsQuery.error,
    refetch: () => {
      yearQuery.refetch()
      aggregationsQuery.refetch()
    },
  }
}

/**
 * Hook: Kategorie-Seite-Daten kombiniert
 */
export function useFinanceCategoryPage(yearId: string | undefined, category: string | undefined, filter: Omit<FinanceCategoryFilter, 'yearId' | 'category'>) {
  const fullFilter: FinanceCategoryFilter = {
    yearId: yearId || '',
    category: category || '',
    ...filter,
  }

  const documentsQuery = useFinanceCategoryDocuments(fullFilter)
  const aggregationsQuery = useFinanceCategoryAggregations(yearId, category)

  return {
    documents: documentsQuery.data || { items: [], total: 0, page: 0, pageSize: 25, totalPages: 0 },
    aggregations: aggregationsQuery.data || null,
    isLoading: documentsQuery.isLoading || aggregationsQuery.isLoading,
    isError: documentsQuery.isError || aggregationsQuery.isError,
    error: documentsQuery.error || aggregationsQuery.error,
    refetch: () => {
      documentsQuery.refetch()
      aggregationsQuery.refetch()
    },
  }
}

// ==================== MUTATIONS ====================

/**
 * Hook: Cache invalidieren nach Aenderungen
 */
export function useInvalidateFinanceQueries() {
  const queryClient = useQueryClient()

  return {
    invalidateAll: () => {
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.all })
    },
    invalidateYears: () => {
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.years() })
    },
    invalidateYear: (yearId: string) => {
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.year(yearId) })
    },
    invalidateAggregations: () => {
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.overallAggregations() })
    },
    invalidateCategoryDocuments: (yearId: string, category: string) => {
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.categoryAggregations(yearId, category)
      })
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.categoryDocuments()
      })
    },
  }
}

// ==================== DEADLINE QUERY ====================

/**
 * Hook: Finanz-Fristen abrufen
 */
export function useFinanceDeadlines(options?: FinanceDeadlineOptions) {
  return useQuery({
    queryKey: finanzenQueryKeys.deadlines(options),
    queryFn: async (): Promise<FinanceDeadlineListResult> => {
      return financeService.getDeadlines(options)
    },
    staleTime: STALE_TIMES.documents, // 30 Sekunden
    gcTime: GC_TIMES.documents, // 5 Minuten
    ...RETRY_CONFIG,
  })
}

// ==================== SINGLE DOCUMENT QUERY ====================

/**
 * Hook: Einzelnes Finanz-Dokument abrufen
 */
export function useFinanceDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: finanzenQueryKeys.document(documentId || ''),
    queryFn: async (): Promise<FinanceCategoryDocument | null> => {
      if (!documentId) return null
      return financeService.getDocument(documentId)
    },
    enabled: !!documentId,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

// ==================== HISTORY QUERY ====================

/**
 * Hook: Dokument-History (Audit Trail) abrufen
 *
 * Zeigt alle Aenderungen an einem Finanz-Dokument:
 * - Erstellung, Bearbeitung, Loeschung
 * - Kategorie- und Jahr-Aenderungen
 * - OCR-Verarbeitung
 * - Frist-Aenderungen
 */
export function useFinanceDocumentHistory(documentId: string | undefined, limit?: number) {
  return useQuery({
    queryKey: finanzenQueryKeys.documentHistory(documentId || ''),
    queryFn: async (): Promise<FinanceDocumentHistoryResult | null> => {
      if (!documentId) return null
      return financeHistoryApi.getDocumentHistory(documentId, limit)
    },
    enabled: !!documentId,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

// ==================== VERSION QUERY HOOKS ====================

/**
 * Hook: Dokument-Versionen (OCR-Versionen) abrufen
 *
 * Zeigt alle OCR-Versionen eines Dokuments:
 * - Versionsnummern und -details
 * - Backend-Information (DeepSeek, GOT-OCR, Surya)
 * - Konfidenz-Scores und Wortanzahl
 * - Rollback-Status
 */
export function useFinanceDocumentVersions(documentId: string | undefined) {
  return useQuery({
    queryKey: finanzenQueryKeys.documentVersions(documentId || ''),
    queryFn: async (): Promise<FinanceDocumentVersionList | null> => {
      if (!documentId) return null
      return financeVersionApi.getVersions(documentId)
    },
    enabled: !!documentId,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Einzelne Version abrufen
 */
export function useFinanceDocumentVersion(
  documentId: string | undefined,
  versionNumber: number | undefined
) {
  return useQuery({
    queryKey: finanzenQueryKeys.documentVersion(documentId || '', versionNumber || 0),
    queryFn: async (): Promise<FinanceDocumentVersion | null> => {
      if (!documentId || !versionNumber) return null
      return financeVersionApi.getVersion(documentId, versionNumber)
    },
    enabled: !!documentId && !!versionNumber,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

/**
 * Hook: Versionen vergleichen
 */
export function useFinanceVersionCompare(
  documentId: string | undefined,
  versionA: number | undefined,
  versionB: number | undefined
) {
  return useQuery({
    queryKey: finanzenQueryKeys.versionCompare(documentId || '', versionA || 0, versionB || 0),
    queryFn: async (): Promise<FinanceVersionCompareResult | null> => {
      if (!documentId || !versionA || !versionB) return null
      return financeVersionApi.compareVersions(documentId, versionA, versionB)
    },
    enabled: !!documentId && !!versionA && !!versionB && versionA !== versionB,
    staleTime: STALE_TIMES.documents,
    gcTime: GC_TIMES.documents,
    ...RETRY_CONFIG,
  })
}

// ==================== VERSION MUTATION HOOKS ====================

export interface RollbackVersionParams {
  documentId: string
  targetVersion: number
  rollbackNote?: string
}

/**
 * Hook: Rollback zu einer frueheren Version
 */
export function useRollbackToVersion() {
  const queryClient = useQueryClient()

  return useMutation<FinanceVersionRollbackResult, Error, RollbackVersionParams>({
    mutationFn: async ({ documentId, targetVersion, rollbackNote }) => {
      return financeVersionApi.rollbackToVersion(documentId, targetVersion, rollbackNote)
    },
    onSuccess: (_data, variables) => {
      // Invalidate version queries
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.documentVersions(variables.documentId)
      })
      // Invalidate document queries (OCR text might change)
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.document(variables.documentId)
      })
      // Invalidate history (rollback is logged)
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.documentHistory(variables.documentId)
      })
    },
  })
}

// ==================== MUTATION HOOKS ====================

export interface UploadDocumentParams {
  year: string
  category: string
  file: File
  metadata?: FinanceDocumentUploadMetadata
}

export interface UpdateDocumentParams {
  documentId: string
  updateData: FinanceDocumentUpdateData
}

/**
 * Hook: Finanz-Dokument hochladen
 */
export function useUploadFinanceDocument() {
  const queryClient = useQueryClient()

  return useMutation<FinanceDocumentUploadResult, Error, UploadDocumentParams>({
    mutationFn: async ({ year, category, file, metadata }) => {
      return financeService.uploadDocument(year, category, file, metadata)
    },
    onSuccess: (_data, variables) => {
      // Invalidate relevant queries after successful upload
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.categoryDocuments() })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.year(variables.year) })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.years() })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.overallAggregations() })
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.yearAggregations(variables.year)
      })
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.categoryAggregations(variables.year, variables.category)
      })
    },
  })
}

/**
 * Hook: Finanz-Dokument aktualisieren
 */
export function useUpdateFinanceDocument() {
  const queryClient = useQueryClient()

  return useMutation<FinanceCategoryDocument, Error, UpdateDocumentParams>({
    mutationFn: async ({ documentId, updateData }) => {
      return financeService.updateDocument(documentId, updateData)
    },
    onSuccess: (_data, variables) => {
      // Invalidate single document cache
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.document(variables.documentId)
      })
      // Invalidate document lists and aggregations (category might have changed)
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.categoryDocuments() })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.all })
    },
  })
}

export interface DeleteDocumentParams {
  documentId: string
  yearId: string
  category: string
}

/**
 * Hook: Finanz-Dokument loeschen
 */
export function useDeleteFinanceDocument() {
  const queryClient = useQueryClient()

  return useMutation<FinanceDocumentDeleteResult, Error, DeleteDocumentParams>({
    mutationFn: async ({ documentId }) => {
      return financeService.deleteDocument(documentId)
    },
    onSuccess: (_data, variables) => {
      // Remove document from cache
      queryClient.removeQueries({
        queryKey: finanzenQueryKeys.document(variables.documentId)
      })
      // Invalidate all related queries
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.categoryDocuments() })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.year(variables.yearId) })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.years() })
      queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.overallAggregations() })
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.yearAggregations(variables.yearId)
      })
      queryClient.invalidateQueries({
        queryKey: finanzenQueryKeys.categoryAggregations(variables.yearId, variables.category)
      })
    },
  })
}

/**
 * Default-Filter-Werte fuer Kategorie-Dokumente
 */
export const DEFAULT_FINANCE_CATEGORY_FILTER: Omit<FinanceCategoryFilter, 'yearId' | 'category'> = {
  sortBy: 'document_date',
  sortOrder: 'desc',
  page: 0,
  pageSize: 25,
}

// Re-export types from finance service
export type {
  FinanceCategoryDocumentList,
  FinanceCategoryAggregations,
  FinanceDocumentHistoryResult,
  FinanceHistoryItem,
  FinanceDocumentVersionList,
  FinanceDocumentVersion,
  FinanceVersionCompareResult,
  FinanceVersionRollbackResult,
}
