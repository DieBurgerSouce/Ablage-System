/**
 * Document Graph & Timeline Types
 *
 * TypeScript-Typen fuer Dokumenten-Graph-Visualisierung
 * und chronologischen Zeitstrahl.
 */

// ==================== Chain Types ====================

export interface ChainDocument {
  id: string;
  documentType: string;
  chainPosition: number;
  filename: string;
  documentDate: string | null;
  amount: number | null;
  referenceNumbers: Record<string, string> | null;
  createdAt: string;
}

export interface DocumentChain {
  chainId: string;
  documentCount: number;
  chainStartedAt: string;
  chainUpdatedAt: string;
  hasQuote: boolean;
  hasOrder: boolean;
  hasDeliveryNote: boolean;
  hasInvoice: boolean;
  hasCreditNote: boolean;
  openDiscrepancies: number;
  isComplete: boolean;
  documents: ChainDocument[];
}

export interface ChainByDocumentResponse {
  documentId: string;
  chainId: string | null;
  documentCount?: number;
  isComplete?: boolean;
  openDiscrepancies?: number;
  message?: string;
}

export interface EntityChainsResponse {
  chains: DocumentChain[];
  total: number;
}

// ==================== Graph View Types ====================

export type ViewMode = 'graph' | 'timeline';

export type DocumentTypeIcon =
  | 'quote'
  | 'order'
  | 'delivery_note'
  | 'invoice'
  | 'credit_note'
  | 'reminder'
  | 'dunning'
  | 'receipt'
  | 'contract'
  | 'unknown';

export type EdgeRelationType =
  | 'chain_link'
  | 'lineage_parent'
  | 'reference';

export interface GraphNodeData {
  label: string;
  documentType: string;
  date: string | null;
  amount: number | null;
  status: string;
  chainId: string;
  chainPosition: number;
}

export interface GraphEdgeData {
  relationType: EdgeRelationType;
  label: string;
}

// ==================== Timeline Types ====================

export type TimelineEventCategory =
  | 'erstellt'
  | 'bearbeitet'
  | 'ocr'
  | 'verknuepft'
  | 'bezahlt'
  | 'gemahnt'
  | 'exportiert'
  | 'archiviert'
  | 'geloescht';

export interface TimelineItem {
  id: string;
  timestamp: string;
  eventType: string;
  category: TimelineEventCategory;
  title: string;
  description: string;
  documentId: string | null;
  documentTitle: string | null;
  metadata: Record<string, unknown>;
}

// ==================== Filter Types ====================

export interface GraphFilterState {
  entityId: string | null;
  entityType: 'customer' | 'supplier' | 'all';
  timeRange: '7d' | '30d' | '90d' | '365d' | 'all';
  documentTypes: string[];
  viewMode: ViewMode;
}

// ==================== Backend Transform Types ====================

export interface ChainDocumentBackend {
  id: string;
  document_type: string;
  chain_position: number;
  filename: string;
  document_date: string | null;
  amount: number | null;
  reference_numbers: Record<string, string> | null;
  created_at: string;
}

export interface DocumentChainBackend {
  chain_id: string;
  document_count: number;
  chain_started_at: string;
  chain_updated_at: string;
  has_quote: boolean;
  has_order: boolean;
  has_delivery_note: boolean;
  has_invoice: boolean;
  has_credit_note: boolean;
  open_discrepancies: number;
  is_complete: boolean;
  documents: ChainDocumentBackend[];
}
