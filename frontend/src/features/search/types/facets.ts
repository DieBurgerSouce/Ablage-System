/**
 * Facet Types - Typen fuer die Facetten-Suche
 *
 * Abgestimmt auf das Backend-Schema:
 * - FacetValue (value, count, label?)
 * - FacetGroup (field, label, values, total_distinct)
 * - SearchFacetsResponse (facets: FacetGroup[], total_documents)
 */

export interface FacetBucket {
  value: string;
  label: string;
  count: number;
}

export interface FacetGroup {
  field: string;
  label: string;
  values: FacetBucket[];
  total_distinct: number;
}

export interface FacetResponse {
  facets: FacetGroup[];
  total_documents: number;
}
