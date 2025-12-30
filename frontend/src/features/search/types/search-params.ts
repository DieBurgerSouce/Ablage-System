/**
 * Search Params Schema - URL-synchronisierte Suchparameter
 *
 * Definiert das Zod-Schema fuer TanStack Router Search Params.
 * Ermoeglicht URL-Sync, Deep-Linking und Validierung.
 *
 * @example
 * // URL: /search?q=rechnung&mode=hybrid&type=pdf&type=image
 * const search = Route.useSearch();
 * // search = { q: 'rechnung', mode: 'hybrid', type: ['pdf', 'image'], ... }
 */

import { z } from 'zod';

// ==================== Enums ====================

export const searchModeSchema = z.enum(['fulltext', 'semantic', 'hybrid']);
export type SearchMode = z.infer<typeof searchModeSchema>;

export const documentTypeSchema = z.enum(['pdf', 'image', 'office']);
export type DocumentType = z.infer<typeof documentTypeSchema>;

export const ocrStatusSchema = z.enum(['completed', 'pending', 'failed']);
export type OcrStatus = z.infer<typeof ocrStatusSchema>;

export const dateRangeSchema = z.enum(['all', 'today', 'week', 'month', 'year']);
export type DateRange = z.infer<typeof dateRangeSchema>;

// ==================== Search Params Schema ====================

/**
 * Hauptschema fuer URL Search Params.
 * Verwendet catch() fuer Fehlertoleranz bei ungueltigten URL-Parametern.
 */
export const searchParamsSchema = z.object({
  /** Suchbegriff */
  q: z.string().optional().catch(''),

  /** Suchmodus */
  mode: searchModeSchema.optional().catch('hybrid'),

  /** Dokumenttypen (Multi-Select) */
  type: z
    .union([z.array(documentTypeSchema), documentTypeSchema])
    .optional()
    .transform((val) => {
      if (!val) return [];
      return Array.isArray(val) ? val : [val];
    })
    .catch([]),

  /** OCR Status (Multi-Select) */
  ocrStatus: z
    .union([z.array(ocrStatusSchema), ocrStatusSchema])
    .optional()
    .transform((val) => {
      if (!val) return [];
      return Array.isArray(val) ? val : [val];
    })
    .catch([]),

  /** Zeitraum (Single-Select) */
  dateRange: dateRangeSchema.optional().catch('all'),

  /** Pagination: Seite */
  page: z.coerce.number().int().positive().optional().catch(1),

  /** Pagination: Limit */
  limit: z.coerce.number().int().min(1).max(100).optional().catch(24),

  /** Sortierung */
  sort: z
    .enum(['date_asc', 'date_desc', 'name_asc', 'name_desc', 'relevance'])
    .optional()
    .catch('relevance'),
});

export type SearchParams = z.infer<typeof searchParamsSchema>;

// ==================== Default Values ====================

export const defaultSearchParams: SearchParams = {
  q: '',
  mode: 'hybrid',
  type: [],
  ocrStatus: [],
  dateRange: 'all',
  page: 1,
  limit: 24,
  sort: 'relevance',
};

// ==================== URL Serialization Helpers ====================

/**
 * Konvertiert SearchParams zu URL-freundlichem Format.
 * Entfernt leere/default Werte um die URL kurz zu halten.
 */
export function serializeSearchParams(
  params: Partial<SearchParams>
): Record<string, string | string[] | undefined> {
  const result: Record<string, string | string[] | undefined> = {};

  if (params.q && params.q.trim()) {
    result.q = params.q.trim();
  }
  if (params.mode && params.mode !== 'hybrid') {
    result.mode = params.mode;
  }
  if (params.type && params.type.length > 0) {
    result.type = params.type;
  }
  if (params.ocrStatus && params.ocrStatus.length > 0) {
    result.ocrStatus = params.ocrStatus;
  }
  if (params.dateRange && params.dateRange !== 'all') {
    result.dateRange = params.dateRange;
  }
  if (params.page && params.page > 1) {
    result.page = String(params.page);
  }
  if (params.limit && params.limit !== 24) {
    result.limit = String(params.limit);
  }
  if (params.sort && params.sort !== 'relevance') {
    result.sort = params.sort;
  }

  return result;
}

/**
 * Prueft ob es aktive Filter gibt (ausser Suchbegriff).
 */
export function hasActiveFilters(params: SearchParams): boolean {
  return (
    params.type.length > 0 ||
    params.ocrStatus.length > 0 ||
    params.dateRange !== 'all' ||
    (params.mode !== undefined && params.mode !== 'hybrid')
  );
}

/**
 * Zaehlt die Anzahl aktiver Filter.
 */
export function countActiveFilters(params: SearchParams): number {
  let count = 0;
  if (params.type.length > 0) count += params.type.length;
  if (params.ocrStatus.length > 0) count += params.ocrStatus.length;
  if (params.dateRange !== 'all') count += 1;
  return count;
}

// ==================== Legacy Compatibility ====================

/**
 * Konvertiert alte SearchFilters in SearchParams.
 * Fuer Rueckwaertskompatibilitaet mit bestehenden Komponenten.
 */
export interface LegacySearchFilters {
  type: string[];
  ocrStatus: string[];
  dateRange: string;
}

export function fromLegacyFilters(
  filters: LegacySearchFilters,
  query: string,
  mode: string
): SearchParams {
  return {
    q: query,
    mode: mode as SearchMode,
    type: filters.type as DocumentType[],
    ocrStatus: filters.ocrStatus as OcrStatus[],
    dateRange: filters.dateRange as DateRange,
    page: 1,
    limit: 24,
    sort: 'relevance',
  };
}

export function toLegacyFilters(params: SearchParams): {
  query: string;
  mode: string;
  filters: LegacySearchFilters;
} {
  return {
    query: params.q ?? '',
    mode: params.mode ?? 'hybrid',
    filters: {
      type: params.type ?? [],
      ocrStatus: params.ocrStatus ?? [],
      dateRange: params.dateRange ?? 'all',
    },
  };
}
