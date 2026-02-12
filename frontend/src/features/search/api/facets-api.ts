/**
 * Facets API - Facetten-Daten vom Backend abrufen
 *
 * Endpoint: GET /search/facets
 * Unterstützte Facet-Felder: document_type, status, tags, ocr_backend_used, mime_type, language
 */
import { apiClient } from '@/lib/api/client';
import type { FacetResponse, FacetGroup, FacetBucket } from '../types/facets';

interface FacetParams {
  facetFields?: string;
  documentType?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
}

/** Backend-Antworttypen (snake_case) */
interface FacetValueBackend {
  value: string;
  count: number;
  label?: string | null;
}

interface FacetGroupBackend {
  field: string;
  label: string;
  values: FacetValueBackend[];
  total_distinct: number;
}

interface FacetResponseBackend {
  facets: FacetGroupBackend[];
  total_documents: number;
}

function transformFacetBucket(item: FacetValueBackend): FacetBucket {
  return {
    value: item.value,
    label: item.label || item.value,
    count: item.count,
  };
}

function transformFacetGroup(group: FacetGroupBackend): FacetGroup {
  return {
    field: group.field,
    label: group.label,
    values: group.values.map(transformFacetBucket),
    total_distinct: group.total_distinct,
  };
}

function transformFacetResponse(response: FacetResponseBackend): FacetResponse {
  return {
    facets: response.facets.map(transformFacetGroup),
    total_documents: response.total_documents,
  };
}

export async function getSearchFacets(params: FacetParams = {}): Promise<FacetResponse> {
  const searchParams = new URLSearchParams();

  if (params.facetFields) searchParams.append('facet_fields', params.facetFields);
  if (params.documentType) searchParams.append('document_type', params.documentType);
  if (params.status) searchParams.append('status', params.status);
  if (params.dateFrom) searchParams.append('date_from', params.dateFrom);
  if (params.dateTo) searchParams.append('date_to', params.dateTo);

  const queryString = searchParams.toString();
  const url = `/search/facets${queryString ? `?${queryString}` : ''}`;
  const response = await apiClient.get<FacetResponseBackend>(url);

  return transformFacetResponse(response.data);
}
