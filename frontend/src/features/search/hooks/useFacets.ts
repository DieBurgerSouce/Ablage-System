/**
 * useFacets Hook - TanStack Query Hook fuer Facetten-Daten
 *
 * Ruft Facetten vom Backend ab und cached sie fuer 30 Sekunden.
 * Unterstuetzt Filter-Parameter fuer kontextabhaengige Facetten.
 */
import { useQuery } from '@tanstack/react-query';
import { getSearchFacets } from '../api/facets-api';
import type { FacetResponse } from '../types/facets';

interface UseFacetsOptions {
  documentType?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  enabled?: boolean;
}

export const facetKeys = {
  all: ['search-facets'] as const,
  withFilters: (filters: Omit<UseFacetsOptions, 'enabled'>) =>
    [...facetKeys.all, filters] as const,
};

export function useFacets(options: UseFacetsOptions = {}) {
  const { enabled = true, ...filters } = options;

  return useQuery<FacetResponse, Error>({
    queryKey: facetKeys.withFilters(filters),
    queryFn: () => getSearchFacets({
      facetFields: 'document_type,status,tags,ocr_backend_used',
      documentType: filters.documentType,
      status: filters.status,
      dateFrom: filters.dateFrom,
      dateTo: filters.dateTo,
    }),
    enabled,
    staleTime: 30 * 1000, // 30 Sekunden
    retry: 1,
  });
}
