/**
 * Streckengeschäft (Drop Shipment) & Dreiecksgeschäft (Triangular Transaction) Types
 * 
 * Rechtliche Grundlagen:
 * - §3 Abs. 6a UStG: Reihengeschäft - nur eine bewegte Lieferung in der Kette
 * - §25b UStG: Innergemeinschaftliches Dreiecksgeschäft - Vereinfachungsregelung
 * - BMF-Schreiben 25.04.2023: Nachweispflichten für Transportverantwortlichkeit
 */

// ============================================================================
// ENUMS
// ============================================================================

/** Klassifikationstyp des Geschäfts */
export type DropShipmentClassificationType = 
  | 'drop_shipment'      // Einfaches Streckengeschäft (2 Parteien + Lieferant)
  | 'triangular'         // Innergemeinschaftliches Dreiecksgeschäft §25b
  | 'chain_transaction'  // Reihengeschäft mit >3 Beteiligten
  | 'domestic'           // Inlandsgeschäft (kein Streckengeschäft)
  | 'unknown';           // Noch nicht klassifiziert

/** Quelle der Klassifikation */
export type ClassificationSource = 
  | 'automatic'    // Automatische OCR/Regel-basierte Erkennung
  | 'manual'       // Manuelle Klassifikation durch Benutzer
  | 'erp_import'   // Import aus ERP-System (SAP, Dynamics, etc.)
  | 'zugferd';     // Aus ZUGFeRD/XRechnung-Metadaten

/** EU-Transaktionstyp */
export type EuTransactionType = 
  | 'intra_community'  // Innergemeinschaftlich
  | 'domestic'         // Inländisch
  | 'export'           // Drittland-Export
  | 'import';          // Drittland-Import

/** Steuerliche Behandlung */
export type TaxTreatment = 
  | 'tax_free_ic'      // Steuerfrei innergemeinschaftlich §4 Nr. 1b
  | 'reverse_charge'   // Steuerschuldnerschaft Empfänger §13b
  | 'standard_vat'     // Normale USt
  | 'triangular_25b';  // Dreiecksgeschäft §25b

/** Rolle einer Partei in der Transaktion */
export type PartyRole = 
  | 'first_supplier'    // Erster Lieferer (Ursprung)
  | 'intermediate'      // Zwischenhändler
  | 'final_recipient';  // Letzter Abnehmer (Endkunde)

/** Belegnachweis-Typ */
export type ProofDocumentType = 
  | 'cmr'                    // CMR-Frachtbrief
  | 'gelangensbestätigung'  // Gelangensbestätigung §17b UStDV
  | 'speditionsauftrag'      // Speditionsauftrag
  | 'spediteursbescheinigung' // Spediteursbescheinigung
  | 'lieferschein'           // Lieferschein
  | 'versandbestätigung';   // Versandbestätigung

/** Validierungsstatus für Belegnachweise */
export type ProofValidationStatus = 
  | 'pending'    // Noch nicht geprüft
  | 'valid'      // Vollständig und gültig
  | 'incomplete' // Unvollständig (fehlende Felder)
  | 'invalid';   // Ungültig (Fehler gefunden)

/** ZUGFeRD VAT Category Codes nach UNTDID 5305 */
export type VatCategoryCode = 
  | 'K'   // Intra-community supply - Innergemeinschaftliche Lieferung
  | 'AE'  // VAT Reverse Charge - Steuerschuldnerschaft Empfänger
  | 'G'   // Free export - Steuerfreier Export
  | 'S'   // Standard rate - Normaler Steuersatz
  | 'Z'   // Zero rated - Nullsatz
  | 'E'   // Exempt - Befreit
  | 'O';  // Outside scope - Nicht im Anwendungsbereich

/** Konfidenz-Level für automatische Erkennung */
export type ConfidenceLevel = 
  | 'definitive'  // 100% - Definitiv-Indikatoren (TAS, §25b Vermerk)
  | 'high'        // 90-99% - Starke Indikatoren
  | 'medium'      // 70-89% - Wahrscheinlich
  | 'low'         // 50-69% - Möglich
  | 'uncertain';  // <50% - Unsicher

// ============================================================================
// CORE INTERFACES
// ============================================================================

/** Hauptklassifikation eines Dokuments */
export interface DropShipmentClassification {
  id: string;
  documentId: string;
  classificationType: DropShipmentClassificationType;
  confidenceScore: number; // 0.0 - 1.0
  confidenceLevel: ConfidenceLevel;
  classificationSource: ClassificationSource;
  
  // Bestätigung
  isConfirmed: boolean;
  confirmedBy?: string;
  confirmedAt?: string;
  
  // EU-spezifisch
  euTransactionType?: EuTransactionType;
  movingDeliveryAssignedTo?: string; // Party responsible for moving delivery
  taxTreatment?: TaxTreatment;
  
  // ZM (Zusammenfassende Meldung)
  zmRelevant: boolean;
  zmReported: boolean;
  zmReportDate?: string;
  zmDeadline?: string; // 25. des Folgemonats
  
  // DATEV
  suggestedDatevAccount?: string;
  suggestedDatevTaxCode?: string;
  
  // Erkennungsgründe
  detectionReasons: DetectionReason[];
  
  // Verknüpfte Daten
  parties: TransactionParty[];
  lineItems: DropShipmentLineItem[];
  proofDocuments: ProofDocument[];
  
  // Timestamps
  createdAt: string;
  updatedAt: string;
}

/** Erkennungsgrund für die Klassifikation */
export interface DetectionReason {
  indicator: DropShipmentIndicator;
  confidence: number;
  extractedValue?: string;
  fieldLocation?: string; // z.B. "header.shipToAddress"
  description: string;
}

/** Erkennungsindikatoren */
export type DropShipmentIndicator = 
  | 'position_type_tas'           // SAP Positionstyp TAS
  | 'external_procurement'        // ERP: Externes Streckengeschäft
  | 'paragraph_25b_reference'     // §25b UStG Vermerk auf Rechnung
  | 'three_eu_vat_ids'           // 3 verschiedene EU-USt-IdNr.
  | 'empty_warehouse_field'       // Leeres Lagerort-Feld
  | 'address_mismatch'            // Rechnungsadresse ≠ Lieferadresse
  | 'cmr_third_party_recipient'   // CMR mit Drittempfänger
  | 'no_vat_reverse_charge'       // Keine USt + Reverse-Charge-Hinweis
  | 'drop_ship_warehouse'         // Drop-Ship-Lager Referenz
  | 'zugferd_ship_to_differs';    // ZUGFeRD: ShipTo ≠ Buyer


/** Beteiligte Partei in der Transaktion */
export interface TransactionParty {
  id: string;
  classificationId: string;
  partyRole: PartyRole;
  companyName: string;
  vatId?: string;
  vatIdCountry?: string; // ISO 2-letter code
  address?: Address;
  isTransportResponsible: boolean;
  createdAt: string;
}

/** Adresse */
export interface Address {
  id: string;
  street?: string;
  city?: string;
  postalCode?: string;
  country: string; // ISO 2-letter code
  countryName?: string;
}

/** Positionsebene für Mischbelege */
export interface DropShipmentLineItem {
  id: string;
  classificationId: string;
  lineItemNumber: number;
  description?: string;
  quantity?: number;
  unitPrice?: number;
  isDropShipment: boolean;
  warehouseCode?: string; // NULL = Streckenposition
  supplierId?: string;
  shipToAddressId?: string;
  
  // DATEV-Zuordnung pro Position
  datevAccount?: string;
  datevTaxCode?: string;
  
  createdAt: string;
}

/** Belegnachweis-Dokument */
export interface ProofDocument {
  id: string;
  classificationId: string;
  proofType: ProofDocumentType;
  documentId?: string; // Verknüpftes Dokument im DMS
  documentName?: string;
  isComplete: boolean;
  validationStatus: ProofValidationStatus;
  missingFields?: string[];
  validationNotes?: string;
  createdAt: string;
}

// ============================================================================
// DATEV INTEGRATION
// ============================================================================

/** DATEV Kontenzuordnung basierend auf Rolle */
export interface DatevAccountMapping {
  role: 'intermediate_revenue' | 'final_recipient_expense' | 'first_supplier_revenue' | 'ic_acquisition';
  skr03Account: string;
  skr04Account: string;
  taxCode?: string;
  ustvaKennzahl?: string;
  description: string;
}

/** Vordefinierte DATEV-Zuordnungen für Streckengeschäfte */
export const DATEV_DROP_SHIPMENT_ACCOUNTS: DatevAccountMapping[] = [
  {
    role: 'intermediate_revenue',
    skr03Account: '8130',
    skr04Account: '4130',
    taxCode: undefined, // Keine USt
    ustvaKennzahl: '42',
    description: 'Zwischenhändler - Lieferungen §25b Abs. 2 UStG'
  },
  {
    role: 'final_recipient_expense',
    skr03Account: '3553', // oder 5553
    skr04Account: '3553',
    taxCode: '731',
    ustvaKennzahl: '66+69',
    description: 'Letzter Abnehmer - 19% USt + VSt neutralisierend'
  },
  {
    role: 'first_supplier_revenue',
    skr03Account: '8125',
    skr04Account: '4125',
    taxCode: undefined,
    ustvaKennzahl: '41',
    description: 'Erster Lieferer - Steuerfreie innergemeinschaftliche Lieferung'
  },
  {
    role: 'ic_acquisition',
    skr03Account: '3425',
    skr04Account: '5425',
    taxCode: undefined,
    ustvaKennzahl: '89',
    description: 'Innergemeinschaftlicher Erwerb'
  }
];

/** DATEV Export-Daten für ein Streckengeschäft */
export interface DatevDropShipmentExport {
  classificationId: string;
  invoiceNumber: string;
  invoiceDate: string;
  amount: number;
  account: string;
  taxCode?: string;
  vatId?: string; // Feld AN (Spalte 40) - Format LLXXXXXXXXXXX
  zmRelevant: boolean;
  triangularMarker?: '1'; // Kennzeichen für Dreiecksgeschäft in ZM
}

// ============================================================================
// ZUGFeRD / XRECHNUNG
// ============================================================================

/** ZUGFeRD-relevante Felder für Streckengeschäfte */
export interface ZugferdDropShipmentData {
  // Parteien
  buyerTradeParty: ZugferdParty;      // Rechnungsempfänger
  shipToTradeParty?: ZugferdParty;    // Warenempfänger (bei Strecke anders)
  ultimateShipToTradeParty?: ZugferdParty; // Endkunde bei Dreiecksgeschäft
  
  // Steuer
  vatCategoryCode: VatCategoryCode;
  exemptionReason?: string;
  vatexCode?: string; // z.B. 'VATEX-EU-IC'
  
  // Lieferland
  deliverToCountryCode?: string; // BT-80 - Pflicht bei VAT Category K
  
  // Validierung
  validationErrors: ZugferdValidationError[];
}

/** ZUGFeRD Partei */
export interface ZugferdParty {
  name: string;
  vatId?: string;
  address?: {
    line1?: string;
    city?: string;
    postalCode?: string;
    countryCode: string;
  };
}

/** ZUGFeRD Validierungsfehler */
export interface ZugferdValidationError {
  rule: string; // z.B. 'BR-IC-12'
  severity: 'error' | 'warning';
  message: string;
  field?: string;
}

// ============================================================================
// API REQUEST/RESPONSE TYPES
// ============================================================================

/** Filter für Streckengeschäft-Liste */
export interface DropShipmentListFilter {
  classificationType?: DropShipmentClassificationType[];
  confidenceMin?: number;
  isConfirmed?: boolean;
  zmRelevant?: boolean;
  zmReported?: boolean;
  euTransactionType?: EuTransactionType[];
  dateFrom?: string;
  dateTo?: string;
  searchQuery?: string;
  page?: number;
  pageSize?: number;
  sortBy?: 'createdAt' | 'confidenceScore' | 'zmDeadline';
  sortOrder?: 'asc' | 'desc';
}

/** Paginierte Liste */
export interface DropShipmentListResponse {
  items: DropShipmentClassification[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/** Klassifikations-Request */
export interface ClassifyDocumentRequest {
  documentId: string;
  forceReclassify?: boolean;
}

/** Klassifikations-Response */
export interface ClassifyDocumentResponse {
  classification: DropShipmentClassification;
  isNew: boolean;
  processingTimeMs: number;
}

/** Bestätigungs-Request */
export interface ConfirmClassificationRequest {
  classificationId: string;
  confirmedType?: DropShipmentClassificationType;
  notes?: string;
}

/** Override-Request für manuelle Korrektur */
export interface OverrideClassificationRequest {
  classificationId: string;
  newClassificationType: DropShipmentClassificationType;
  euTransactionType?: EuTransactionType;
  taxTreatment?: TaxTreatment;
  movingDeliveryAssignedTo?: string;
  datevAccount?: string;
  datevTaxCode?: string;
  reason: string;
}

/** Belegnachweis verknüpfen */
export interface LinkProofDocumentRequest {
  classificationId: string;
  proofType: ProofDocumentType;
  documentId: string;
}

/** ZM-relevante offene Meldungen */
export interface ZmPendingResponse {
  items: DropShipmentClassification[];
  currentPeriod: string; // z.B. "2025-01"
  deadline: string; // 25. des Folgemonats
  daysRemaining: number;
}

/** DATEV Export Request */
export interface DatevExportRequest {
  classificationIds: string[];
  exportFormat: 'extf' | 'csv';
  kontenrahmen: '03' | '04';
  includeZmData: boolean;
}

/** DATEV Export Response */
export interface DatevExportResponse {
  exportId: string;
  fileName: string;
  downloadUrl: string;
  recordCount: number;
  warnings?: string[];
}

// ============================================================================
// UI STATE TYPES
// ============================================================================

/** Dashboard-Statistiken */
export interface DropShipmentDashboardStats {
  total: number;
  byType: Record<DropShipmentClassificationType, number>;
  pendingConfirmation: number;
  zmPending: number;
  proofIncomplete: number;
  avgConfidence: number;
  thisMonth: number;
  lastMonth: number;
}

/** Bulk-Aktion */
export interface BulkActionRequest {
  action: 'confirm' | 'export_datev' | 'mark_zm_reported';
  classificationIds: string[];
}

/** Bulk-Aktion Response */
export interface BulkActionResponse {
  successful: string[];
  failed: Array<{ id: string; error: string }>;
}
