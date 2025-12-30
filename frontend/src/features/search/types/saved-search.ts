/**
 * Saved Search Types - Gespeicherte Suchen
 *
 * Typen und Utilities fuer gespeicherte Suchen.
 * Werden als "Smart Folders" in der Sidebar angezeigt.
 */

import { z } from 'zod';
import { searchParamsSchema, type SearchParams } from './search-params';

// ==================== Types ====================

export const savedSearchSchema = z.object({
  /** Eindeutige ID (UUID) */
  id: z.string().uuid(),

  /** Anzeigename der gespeicherten Suche */
  name: z.string().min(1).max(100),

  /** Optionale Beschreibung */
  description: z.string().max(500).optional(),

  /** Die gespeicherten Suchparameter */
  params: searchParamsSchema,

  /** Erstellungsdatum */
  createdAt: z.string().datetime(),

  /** Letzter Zugriff */
  lastAccessedAt: z.string().datetime().optional(),

  /** Anzahl der Zugriffe */
  accessCount: z.number().int().nonnegative().default(0),

  /** Icon (Lucide Icon Name) */
  icon: z.string().optional(),

  /** Farbe (Tailwind Color) */
  color: z.string().optional(),

  /** Als Favorit markiert */
  pinned: z.boolean().default(false),
});

export type SavedSearch = z.infer<typeof savedSearchSchema>;

// ==================== Creation Helper ====================

export interface CreateSavedSearchInput {
  name: string;
  description?: string;
  params: SearchParams;
  icon?: string;
  color?: string;
}

export function createSavedSearch(input: CreateSavedSearchInput): SavedSearch {
  return {
    id: crypto.randomUUID(),
    name: input.name,
    description: input.description,
    params: input.params,
    icon: input.icon,
    color: input.color,
    createdAt: new Date().toISOString(),
    accessCount: 0,
    pinned: false,
  };
}

// ==================== LocalStorage Schema ====================

export const savedSearchesStorageSchema = z.array(savedSearchSchema);

export type SavedSearchesStorage = z.infer<typeof savedSearchesStorageSchema>;

// ==================== Storage Key ====================

export const SAVED_SEARCHES_STORAGE_KEY = 'ablage-saved-searches';

// ==================== Validation ====================

export function validateSavedSearch(data: unknown): SavedSearch | null {
  const result = savedSearchSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateSavedSearches(data: unknown): SavedSearch[] {
  const result = savedSearchesStorageSchema.safeParse(data);
  return result.success ? result.data : [];
}

// ==================== Search Label Generator ====================

/**
 * Generiert einen automatischen Namen basierend auf den Suchparametern.
 */
export function generateSearchName(params: SearchParams): string {
  const parts: string[] = [];

  // Query
  if (params.q && params.q.trim()) {
    const truncated =
      params.q.length > 20 ? `${params.q.substring(0, 20)}...` : params.q;
    parts.push(`"${truncated}"`);
  }

  // Mode
  if (params.mode && params.mode !== 'hybrid') {
    parts.push(params.mode === 'fulltext' ? 'Volltext' : 'KI');
  }

  // Types
  if (params.type && params.type.length > 0) {
    const typeLabels: Record<string, string> = {
      pdf: 'PDF',
      image: 'Bilder',
      office: 'Office',
    };
    const labels = params.type.map((t) => typeLabels[t] || t);
    parts.push(labels.join(', '));
  }

  // OCR Status
  if (params.ocrStatus && params.ocrStatus.length > 0) {
    const statusLabels: Record<string, string> = {
      completed: 'Verarbeitet',
      pending: 'Wartend',
      failed: 'Fehlerhaft',
    };
    const labels = params.ocrStatus.map((s) => statusLabels[s] || s);
    parts.push(labels.join(', '));
  }

  // Date Range
  if (params.dateRange && params.dateRange !== 'all') {
    const rangeLabels: Record<string, string> = {
      today: 'Heute',
      week: 'Diese Woche',
      month: 'Dieser Monat',
      year: 'Dieses Jahr',
    };
    parts.push(rangeLabels[params.dateRange] || params.dateRange);
  }

  return parts.length > 0 ? parts.join(' - ') : 'Neue Suche';
}
