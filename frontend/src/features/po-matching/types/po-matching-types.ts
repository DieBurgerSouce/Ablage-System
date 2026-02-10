/**
 * PO-Matching TypeScript Types
 *
 * Typdefinitionen fuer das 3-Way Purchase Order Matching:
 * Bestellung <-> Lieferschein <-> Rechnung
 *
 * Alle Typen korrespondieren mit den Backend-Pydantic-Schemas
 * aus app/api/v1/po_matching.py
 */

// ==================== Enums / Unions ====================

export type MatchStatus =
  | 'pending'
  | 'partial'
  | 'full'
  | 'discrepancy'
  | 'rejected'
  | 'approved';

export type DiscrepancyCategory =
  | 'amount'
  | 'quantity'
  | 'item'
  | 'date'
  | 'price';

export type DiscrepancySeverity =
  | 'info'
  | 'warning'
  | 'error'
  | 'critical';

// ==================== Response Types ====================

export interface MatchResponse {
  id: string;
  company_id: string;
  purchase_order_id: string | null;
  delivery_note_id: string | null;
  invoice_id: string | null;
  document_chain_id: string | null;
  vendor_entity_id: string | null;
  vendor_name: string | null;
  order_number: string | null;
  order_date: string | null;
  po_amount: number | null;
  dn_amount: number | null;
  invoice_amount: number | null;
  match_status: MatchStatus;
  match_score: number;
  auto_matched: boolean;
  amount_tolerance_percent: number;
  quantity_tolerance_percent: number;
  approved_by_id: string | null;
  approved_at: string | null;
  approval_notes: string | null;
  document_count: number;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
  matched_at: string | null;
}

export interface DiscrepancyResponse {
  id: string;
  match_id: string;
  category: DiscrepancyCategory;
  description: string;
  field_name: string;
  expected_value: string | null;
  actual_value: string | null;
  expected_amount: number | null;
  actual_amount: number | null;
  deviation_percent: number | null;
  severity: DiscrepancySeverity;
  resolved: boolean;
  resolved_at: string | null;
  resolution_notes: string | null;
  created_at: string;
}

export interface MatchDetailResponse extends MatchResponse {
  discrepancies: DiscrepancyResponse[];
}

export interface MatchListResponse {
  items: MatchResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface MatchStatisticsResponse {
  total_matches: number;
  pending_matches: number;
  partial_matches: number;
  full_matches: number;
  discrepancy_matches: number;
  approved_matches: number;
  rejected_matches: number;
  auto_matched_count: number;
  avg_match_score: number;
  total_discrepancies: number;
  unresolved_discrepancies: number;
  avg_amount_deviation_percent: number;
  period_start: string;
  period_end: string;
}

export interface UnmatchedDocumentResponse {
  id: string;
  filename: string | null;
  document_type: string | null;
  chain_id: string | null;
  created_at: string;
}

export interface AutoMatchResponse {
  matches_updated: number;
  matches: MatchResponse[];
}

// ==================== Request / Filter Types ====================

export interface POMatchFilter {
  status?: MatchStatus;
  vendor_entity_id?: string;
  date_from?: string;
  date_to?: string;
  order_number?: string;
  page?: number;
  page_size?: number;
}

export interface POMatchCreateRequest {
  purchase_order_id?: string;
  delivery_note_id?: string;
  invoice_id?: string;
  document_chain_id?: string;
  vendor_entity_id?: string;
  vendor_name?: string;
  order_number?: string;
  order_date?: string;
  po_amount?: number;
  dn_amount?: number;
  invoice_amount?: number;
  amount_tolerance_percent?: number;
  quantity_tolerance_percent?: number;
}

export interface ApproveMatchRequest {
  notes?: string;
}
