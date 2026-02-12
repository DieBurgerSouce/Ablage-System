/**
 * Streckengeschäft Detection - TypeScript Types
 * 
 * Type definitions for Drop Shipment / Triangular Transaction Detection
 * Used across frontend components and API integration
 */

// =============================================================================
// ENUMS
// =============================================================================

/** Transaction type classification */
export type TransactionType =
  | 'standard'           // Normal warehouse transaction
  | 'drop_shipment'      // Streckengeschäft (2 parties)
  | 'triangular_eu'      // EU Dreiecksgeschäft §25b UStG (3 EU parties)
  | 'chain_transaction'  // Reihengeschäft (3+ parties, complex)
  | 'unknown';           // Needs manual classification

/** Role of German company in transaction */
export type CompanyRole =
  | 'first_supplier'     // Erster Lieferer
  | 'intermediate'       // Zwischenhändler (mittlerer Abnehmer)
  | 'final_buyer'        // Letzter Abnehmer
  | 'not_applicable';    // Standard transaction

/** Moving delivery assignment per §3 Abs. 6a UStG */
export type MovingDelivery =
  | 'to_intermediate'    // Lieferung AN den Zwischenhändler ist bewegte Lieferung
  | 'from_intermediate'  // Lieferung VOM Zwischenhändler ist bewegte Lieferung
  | 'undetermined';      // Noch nicht bestimmt

/** Classification confidence level */
export type ConfidenceLevel =
  | 'definitive'         // 100% - ERP marker, legal reference
  | 'high'               // 90-99% - Strong indicators
  | 'medium'             // 70-89% - Multiple weak indicators
  | 'low'                // 50-69% - Single weak indicator
  | 'manual_required';   // <50% - Conflicting signals

/** VAT treatment category */
export type VatCategory =
  | 'standard_de'        // Normal German VAT (19% or 7%)
  | 'intra_community'    // Innergemeinschaftliche Lieferung (steuerfrei)
  | 'reverse_charge'     // Steuerschuldnerschaft beim Empfänger
  | 'export'             // Ausfuhr Drittland (steuerfrei)
  | 'triangular_middle'  // §25b Zwischenhändler (keine USt, ZM Kz.1)
  | 'triangular_final';  // §25b Endabnehmer (Reverse Charge + VSt)

/** Proof document type */
export type ProofType =
  | 'invoice'
  | 'delivery_note'
  | 'cmr'
  | 'gelangensbestätigung'
  | 'speditionsauftrag'
  | 'vat_id_proof';

/** Party role in transaction chain */
export type PartyRole =
  | 'seller'
  | 'buyer'
  | 'ship_to'
  | 'bill_to'
  | 'carrier';

// =============================================================================
// CORE INTERFACES
// =============================================================================

/** Classification indicator that triggered detection */
export interface ClassificationIndicator {
  code: string;
  name: string;
  weight: number;
  isDefinitive: boolean;
  matchedValue?: string;
  sourceField?: string;
}

/** Main classification result for a document */
export interface DropShipmentClassification {
  id: string;
  documentId: string;
  
  // Classification results
  transactionType: TransactionType;
  companyRole: CompanyRole;
  movingDelivery: MovingDelivery;
  vatCategory: VatCategory;
  
  // Confidence
  confidenceLevel: ConfidenceLevel;
  confidenceScore: number; // 0-100
  
  // Validation
  isValidated: boolean;
  validatedBy?: string;
  validatedAt?: string;
  
  // Detection details
  indicators: ClassificationIndicator[];
  conflicts?: ConflictInfo[];
  
  // EU transaction details
  partyCount: number;
  euCountriesInvolved?: string[]; // ISO country codes
  
  // DATEV integration
  datevAccountDebit?: string;
  datevAccountCredit?: string;
  datevTaxCode?: string;
  zmRelevant: boolean;
  zmMarker?: '1' | null; // '1' for triangular transactions
  
  // Timestamps
  createdAt: string;
  updatedAt: string;
}

/** Position-level classification for mixed invoices */
export interface DropShipmentPosition {
  id: string;
  classificationId: string;
  documentId: string;
  
  // Position identification
  positionNumber: number;
  articleNumber?: string;
  articleDescription?: string;
  quantity?: number;
  unitPrice?: number;
  lineTotal?: number;
  
  // Classification
  isDropShipment: boolean;
  warehouseCode?: string;
  erpPositionType?: string; // TAS, TAN, etc.
  
  // VAT treatment
  vatCategory?: VatCategory;
  vatRate?: number;
  
  // DATEV accounts
  datevRevenueAccount?: string;
  datevExpenseAccount?: string;
  
  createdAt: string;
}

/** Party information from transaction */
export interface TransactionParty {
  id: string;
  classificationId: string;
  
  partyRole: PartyRole;
  sequenceNumber: number; // 1=first, 2=middle, 3=last
  
  // Identification
  companyName?: string;
  vatId?: string;
  countryCode?: string;
  
  // Address
  street?: string;
  city?: string;
  postalCode?: string;
  country?: string;
  
  sourceField?: string;
  createdAt: string;
}

/** VAT ID with validation status */
export interface VatIdRecord {
  id: string;
  vatId: string;
  countryCode: string;
  companyName?: string;
  
  isValid?: boolean;
  lastValidated?: string;
  validationResponse?: ViesValidationResponse;
  
  customerId?: string;
  supplierId?: string;
  
  createdAt: string;
  updatedAt: string;
}

/** VIES validation response structure */
export interface ViesValidationResponse {
  valid: boolean;
  name?: string;
  address?: string;
  requestDate: string;
  requestIdentifier?: string;
}

/** Proof document in evidence chain */
export interface ProofDocument {
  id: string;
  classificationId: string;
  documentId?: string;
  
  proofType: ProofType;
  isPresent: boolean;
  isComplete: boolean;
  missingFields?: string[];
  
  // CMR specific
  cmrField24Signed?: boolean;
  cmrField24Date?: string;
  
  notes?: string;
  createdAt: string;
}

/** Conflict information when indicators disagree */
export interface ConflictInfo {
  indicator1: string;
  indicator2: string;
  description: string;
  resolution?: string;
}

// =============================================================================
// AUDIT & HISTORY
// =============================================================================

/** Audit log entry */
export interface ClassificationAuditEntry {
  id: string;
  classificationId: string;
  
  action: ClassificationAction;
  previousValue?: Partial<DropShipmentClassification>;
  newValue?: Partial<DropShipmentClassification>;
  reason?: string;
  
  performedBy?: string;
  performedAt: string;
  
  ipAddress?: string;
  userAgent?: string;
}

export type ClassificationAction =
  | 'created'
  | 'auto_classified'
  | 'manually_validated'
  | 'overridden'
  | 'exported_datev'
  | 'zm_reported';

// =============================================================================
// CONFIGURATION
// =============================================================================

/** DATEV account mapping configuration */
export interface DatevAccountMapping {
  id: string;
  kontenrahmen: 'SKR03' | 'SKR04';
  companyRole: CompanyRole;
  transactionType: TransactionType;
  
  revenueAccount?: string;
  expenseAccount?: string;
  taxCode?: string;
  
  ustvaKennzahl?: string;
  zmKennzeichen?: '1' | null;
  
  descriptionDe?: string;
  isActive: boolean;
}

/** Classification indicator configuration */
export interface IndicatorConfig {
  id: string;
  indicatorCode: string;
  indicatorNameDe: string;
  indicatorNameEn?: string;
  
  weight: number; // 0-100
  isDefinitive: boolean;
  appliesToIncoming: boolean;
  appliesToOutgoing: boolean;
  
  detectionPattern?: string; // Regex
  detectionField?: string;
  
  isActive: boolean;
}

// =============================================================================
// API REQUEST/RESPONSE TYPES
// =============================================================================

/** Request to classify a document */
export interface ClassifyDocumentRequest {
  documentId: string;
  forceReclassify?: boolean;
  skipValidation?: boolean;
}

/** Classification result with full details */
export interface ClassificationResult {
  classification: DropShipmentClassification;
  positions: DropShipmentPosition[];
  parties: TransactionParty[];
  proofDocuments: ProofDocument[];
  suggestedActions: SuggestedAction[];
}

/** Suggested action based on classification */
export interface SuggestedAction {
  actionType: 'create_task' | 'warning' | 'info' | 'datev_export' | 'zm_check';
  priority: 'high' | 'medium' | 'low';
  titleDe: string;
  descriptionDe: string;
  actionData?: Record<string, unknown>;
}

/** Manual validation request */
export interface ValidateClassificationRequest {
  classificationId: string;
  validatedTransactionType: TransactionType;
  validatedCompanyRole: CompanyRole;
  validatedVatCategory: VatCategory;
  reason?: string;
}

/** Bulk classification request */
export interface BulkClassifyRequest {
  documentIds: string[];
  options?: {
    forceReclassify?: boolean;
    skipLowConfidence?: boolean;
  };
}

/** Bulk classification response */
export interface BulkClassifyResponse {
  successful: ClassificationResult[];
  failed: Array<{
    documentId: string;
    error: string;
  }>;
  summary: {
    total: number;
    classified: number;
    failed: number;
    manualRequired: number;
  };
}

/** DATEV export request */
export interface DatevExportRequest {
  classificationIds: string[];
  kontenrahmen: 'SKR03' | 'SKR04';
  includeZmData: boolean;
  exportFormat: 'csv' | 'extf';
}

/** DATEV export response */
export interface DatevExportResponse {
  exportId: string;
  filename: string;
  downloadUrl: string;
  recordCount: number;
  zmRecordCount: number;
  warnings: string[];
}

// =============================================================================
// FILTER & PAGINATION
// =============================================================================

/** Filter options for classification list */
export interface ClassificationFilter {
  transactionTypes?: TransactionType[];
  confidenceLevels?: ConfidenceLevel[];
  isValidated?: boolean;
  zmRelevant?: boolean;
  dateFrom?: string;
  dateTo?: string;
  documentIds?: string[];
  customerIds?: string[];
  supplierIds?: string[];
}

/** Paginated classification list response */
export interface ClassificationListResponse {
  items: DropShipmentClassification[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

// =============================================================================
// DASHBOARD & STATISTICS
// =============================================================================

/** Statistics for dashboard */
export interface ClassificationStatistics {
  totalDocuments: number;
  byTransactionType: Record<TransactionType, number>;
  byConfidenceLevel: Record<ConfidenceLevel, number>;
  pendingValidation: number;
  zmRelevantCount: number;
  
  // Time-based metrics
  classifiedToday: number;
  classifiedThisWeek: number;
  classifiedThisMonth: number;
  
  // Accuracy metrics (if manual validation exists)
  accuracyRate?: number;
  overrideRate?: number;
}

/** ZM (Zusammenfassende Meldung) summary */
export interface ZmSummary {
  period: string; // YYYY-MM format
  totalAmount: number;
  triangularAmount: number;
  recordCount: number;
  triangularRecordCount: number;
  byCountry: Array<{
    countryCode: string;
    amount: number;
    recordCount: number;
  }>;
  deadline: string; // 25th of following month
  isSubmitted: boolean;
  submittedAt?: string;
}

/** ZM Record - einzelner Eintrag für ZM Meldung */
export interface ZmRecord {
  id: string;
  vatId: string;
  countryCode: string;
  amount: number;
  isTriangular: boolean;
  triangularMarker?: '1' | null;  // Kz.1 für Dreiecksgeschaeft
  classificationId: string;
}

// =============================================================================
// UI HELPER TYPES
// =============================================================================

/** Badge variant based on confidence */
export const getConfidenceBadgeVariant = (
  level: ConfidenceLevel
): 'default' | 'secondary' | 'destructive' | 'outline' => {
  switch (level) {
    case 'definitive':
    case 'high':
      return 'default';
    case 'medium':
      return 'secondary';
    case 'low':
      return 'outline';
    case 'manual_required':
      return 'destructive';
  }
};

/** German labels for transaction types */
export const transactionTypeLabels: Record<TransactionType, string> = {
  standard: 'Standard (Lager)',
  drop_shipment: 'Streckengeschäft',
  triangular_eu: 'EU-Dreiecksgeschäft',
  chain_transaction: 'Reihengeschäft',
  unknown: 'Unbekannt',
};

/** German labels for company roles */
export const companyRoleLabels: Record<CompanyRole, string> = {
  first_supplier: 'Erster Lieferer',
  intermediate: 'Zwischenhändler',
  final_buyer: 'Letzter Abnehmer',
  not_applicable: 'Nicht zutreffend',
};

/** German labels for VAT categories */
export const vatCategoryLabels: Record<VatCategory, string> = {
  standard_de: 'Standard DE (19%/7%)',
  intra_community: 'Innergemeinschaftlich steuerfrei',
  reverse_charge: 'Reverse Charge §13b',
  export: 'Ausfuhr Drittland steuerfrei',
  triangular_middle: '§25b Zwischenhändler',
  triangular_final: '§25b Endabnehmer',
};

/** German labels for confidence levels */
export const confidenceLevelLabels: Record<ConfidenceLevel, string> = {
  definitive: 'Definitiv (100%)',
  high: 'Hoch (90-99%)',
  medium: 'Mittel (70-89%)',
  low: 'Niedrig (50-69%)',
  manual_required: 'Manuelle Prüfung erforderlich',
};
