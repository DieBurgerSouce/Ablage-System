/**
 * Document Chain Types
 *
 * TypeScript Typen für Auftragsketten-Tracking.
 * Workflow: Angebot → Auftrag → Lieferschein → Rechnung
 */

// ==================== Enums ====================

export type ChainRelationshipType =
  | 'quote_to_order'      // Angebot → Auftrag
  | 'order_to_delivery'   // Auftrag → Lieferschein
  | 'delivery_to_invoice' // Lieferschein → Rechnung
  | 'quote_to_invoice';   // Angebot → Rechnung (direkt)

export type DocumentTypeInChain =
  | 'quote'          // Angebot
  | 'order'          // Auftrag
  | 'delivery_note'  // Lieferschein
  | 'invoice';       // Rechnung

export type DiscrepancyType =
  | 'amount'    // Betragsabweichung
  | 'quantity'  // Mengenabweichung
  | 'item'      // Positionsabweichung
  | 'date'      // Datumsabweichung
  | 'other';    // Sonstige Abweichung

export type DiscrepancySeverity = 'info' | 'warning' | 'error';

// ==================== Document in Chain ====================

/**
 * Dokument innerhalb einer Kette
 */
export interface ChainDocument {
  id: string;
  documentType: DocumentTypeInChain;
  filename: string;
  displayName?: string;
  referenceNumber?: string;
  totalAmount?: number;
  documentDate?: string;
  businessEntityId?: string;
  businessEntityName?: string;
  createdAt: string;
}

/**
 * Backend Response
 */
export interface ChainDocumentBackend {
  id: string;
  document_type: DocumentTypeInChain;
  filename: string;
  display_name?: string;
  reference_number?: string;
  total_amount?: number;
  document_date?: string;
  business_entity_id?: string;
  business_entity_name?: string;
  created_at: string;
}

// ==================== Chain Info ====================

/**
 * Vollständige Ketten-Information
 */
export interface DocumentChainInfo {
  chainId: string;
  name?: string;
  documents: ChainDocument[];
  relationships: ChainRelationship[];
  discrepancies: ChainDiscrepancy[];
  totalValue: number;
  status: ChainStatus;
  createdAt: string;
  updatedAt: string;
}

export type ChainStatus =
  | 'in_progress'  // Kette unvollständig
  | 'complete'     // Alle Dokumente vorhanden
  | 'has_issues';  // Abweichungen vorhanden

/**
 * Backend Response
 */
export interface DocumentChainInfoBackend {
  chain_id: string;
  name?: string;
  documents: ChainDocumentBackend[];
  relationships: ChainRelationshipBackend[];
  discrepancies: ChainDiscrepancyBackend[];
  total_value: number;
  status: ChainStatus;
  created_at: string;
  updated_at: string;
}

// ==================== Relationship ====================

/**
 * Beziehung zwischen zwei Dokumenten
 */
export interface ChainRelationship {
  id: string;
  sourceDocumentId: string;
  targetDocumentId: string;
  relationshipType: ChainRelationshipType;
  confidence: number;
  createdAt: string;
}

export interface ChainRelationshipBackend {
  id: string;
  source_document_id: string;
  target_document_id: string;
  relationship_type: ChainRelationshipType;
  confidence: number;
  created_at: string;
}

// ==================== Discrepancy ====================

/**
 * Abweichung in einer Kette
 */
export interface ChainDiscrepancy {
  id: string;
  chainId: string;
  sourceDocumentId: string;
  targetDocumentId: string;
  discrepancyType: DiscrepancyType;
  severity: DiscrepancySeverity;
  description: string;
  sourceValue?: string;
  targetValue?: string;
  differencePercentage?: number;
  isResolved: boolean;
  resolvedAt?: string;
  resolvedByUserId?: string;
  resolutionNotes?: string;
  createdAt: string;
}

export interface ChainDiscrepancyBackend {
  id: string;
  chain_id: string;
  source_document_id: string;
  target_document_id: string;
  discrepancy_type: DiscrepancyType;
  severity: DiscrepancySeverity;
  description: string;
  source_value?: string;
  target_value?: string;
  difference_percentage?: number;
  is_resolved: boolean;
  resolved_at?: string;
  resolved_by_user_id?: string;
  resolution_notes?: string;
  created_at: string;
}

// ==================== Match Result ====================

/**
 * Auto-Match Ergebnis
 */
export interface ChainMatchResult {
  candidateDocumentId: string;
  candidateDocument: ChainDocument;
  confidence: number;
  matchReasons: string[];
  suggestedRelationshipType: ChainRelationshipType;
}

export interface ChainMatchResultBackend {
  candidate_document_id: string;
  candidate_document: ChainDocumentBackend;
  confidence: number;
  match_reasons: string[];
  suggested_relationship_type: ChainRelationshipType;
}

// ==================== Create/Update ====================

/**
 * Payload zum Erstellen einer neuen Kette
 */
export interface ChainCreate {
  name?: string;
  documentIds: string[];
}

/**
 * Payload zum Verknüpfen von Dokumenten
 */
export interface LinkDocumentsRequest {
  sourceDocumentId: string;
  targetDocumentId: string;
  relationshipType: ChainRelationshipType;
  chainId?: string; // Optional, erstellt neue Kette wenn nicht angegeben
}

/**
 * Payload zum Auflösen einer Abweichung
 */
export interface ResolveDiscrepancyRequest {
  resolutionNotes: string;
}

// ==================== Filter ====================

export interface ChainFilter {
  page: number;
  perPage: number;
  status?: ChainStatus;
  businessEntityId?: string;
  hasDiscrepancies?: boolean;
}

// ==================== UI Labels ====================

export const CHAIN_UI_LABELS = {
  // Page
  pageTitle: 'Auftragsketten',
  pageDescription: 'Verknüpfung von Angeboten, Aufträgen, Lieferscheinen und Rechnungen',

  // Document Types
  typeQuote: 'Angebot',
  typeOrder: 'Auftrag',
  typeDeliveryNote: 'Lieferschein',
  typeInvoice: 'Rechnung',

  // Status
  statusInProgress: 'In Bearbeitung',
  statusComplete: 'Vollständig',
  statusHasIssues: 'Mit Abweichungen',

  // Relationship Types
  relQuoteToOrder: 'Angebot → Auftrag',
  relOrderToDelivery: 'Auftrag → Lieferschein',
  relDeliveryToInvoice: 'Lieferschein → Rechnung',
  relQuoteToInvoice: 'Angebot → Rechnung',

  // Discrepancy
  discrepancyAmount: 'Betragsabweichung',
  discrepancyQuantity: 'Mengenabweichung',
  discrepancyItem: 'Positionsabweichung',
  discrepancyDate: 'Datumsabweichung',
  discrepancyOther: 'Sonstige Abweichung',

  // Severity
  severityInfo: 'Information',
  severityWarning: 'Warnung',
  severityError: 'Fehler',

  // Actions
  actionCreateChain: 'Kette erstellen',
  actionLinkDocuments: 'Dokumente verknüpfen',
  actionAutoMatch: 'Automatisch verknüpfen',
  actionViewChain: 'Kette anzeigen',
  actionResolveDiscrepancy: 'Abweichung auflösen',
  actionRemoveLink: 'Verknüpfung entfernen',

  // Toasts
  successCreateChain: 'Auftragskette erstellt',
  successLinkDocuments: 'Dokumente verknüpft',
  successResolveDiscrepancy: 'Abweichung aufgelöst',
  errorCreateChain: 'Fehler beim Erstellen der Kette',
  errorLinkDocuments: 'Fehler beim Verknüpfen',
  errorAutoMatch: 'Fehler beim automatischen Matching',
  errorResolveDiscrepancy: 'Fehler beim Auflösen der Abweichung',

  // Empty States
  emptyNoChains: 'Noch keine Auftragsketten',
  emptyNoMatches: 'Keine passenden Dokumente gefunden',
  emptyNoDiscrepancies: 'Keine Abweichungen',
} as const;

// ==================== Style Constants ====================

export const DOCUMENT_TYPE_STYLES: Record<DocumentTypeInChain, {
  label: string;
  icon: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
}> = {
  quote: {
    label: CHAIN_UI_LABELS.typeQuote,
    icon: 'FileText',
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
  },
  order: {
    label: CHAIN_UI_LABELS.typeOrder,
    icon: 'ClipboardList',
    bgColor: 'bg-purple-50',
    textColor: 'text-purple-700',
    borderColor: 'border-purple-200',
  },
  delivery_note: {
    label: CHAIN_UI_LABELS.typeDeliveryNote,
    icon: 'Truck',
    bgColor: 'bg-orange-50',
    textColor: 'text-orange-700',
    borderColor: 'border-orange-200',
  },
  invoice: {
    label: CHAIN_UI_LABELS.typeInvoice,
    icon: 'Receipt',
    bgColor: 'bg-green-50',
    textColor: 'text-green-700',
    borderColor: 'border-green-200',
  },
};

export const DISCREPANCY_SEVERITY_STYLES: Record<DiscrepancySeverity, {
  label: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
}> = {
  info: {
    label: CHAIN_UI_LABELS.severityInfo,
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
  },
  warning: {
    label: CHAIN_UI_LABELS.severityWarning,
    bgColor: 'bg-yellow-50',
    textColor: 'text-yellow-700',
    borderColor: 'border-yellow-200',
  },
  error: {
    label: CHAIN_UI_LABELS.severityError,
    bgColor: 'bg-red-50',
    textColor: 'text-red-700',
    borderColor: 'border-red-200',
  },
};
