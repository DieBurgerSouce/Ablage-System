// Dokumentkategorien für die Ablage-Struktur
export type CustomerDocumentCategory =
  | 'anfragen'
  | 'angebote'
  | 'auftragsbestätigung'
  | 'lieferscheine'
  | 'rechnungen'
  | 'storno'
  | 'mahnungen'
  | 'offene_rechnungen'
  | 'offene_angebote'
  | 'offene_anfragen'
  | 'reklamation'
  | 'kommunikation'
  | 'archiv'
  | 'druckdaten';  // NUR für Spargelmesser-Kunden!

// Lieferanten haben zusaetzlich "Bestellungen"
export type SupplierDocumentCategory =
  | CustomerDocumentCategory
  | 'bestellungen';

// Kategorie-Metadaten
export interface DocumentCategoryInfo {
  id: string;
  label: string;
  shortCode?: string;  // z.B. "AG", "AB", "LS", "RG", "ST", "B"
  icon: string;        // Lucide Icon Name
  color?: string;      // Badge Farbe
  isOpenStatus?: boolean;  // Für "Offene X" Kategorien
}

// Basis Kunden-Kategorien (für Folie - ohne Druckdaten)
export const CUSTOMER_CATEGORIES_BASE: DocumentCategoryInfo[] = [
  { id: 'anfragen', label: 'Anfragen', icon: 'HelpCircle' },
  { id: 'angebote', label: 'Angebote', shortCode: 'AG', icon: 'FileText' },
  { id: 'auftragsbestätigung', label: 'Auftragsbestätigung', shortCode: 'AB', icon: 'FileCheck' },
  { id: 'lieferscheine', label: 'Lieferscheine', shortCode: 'LS', icon: 'Truck' },
  { id: 'rechnungen', label: 'Rechnungen', shortCode: 'RG', icon: 'Receipt' },
  { id: 'storno', label: 'Storno', shortCode: 'ST', icon: 'XCircle', color: 'destructive' },
  { id: 'mahnungen', label: 'Mahnungen', icon: 'AlertTriangle', color: 'warning' },
  { id: 'offene_rechnungen', label: 'Offene Rechnungen', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_angebote', label: 'Offene Angebote', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_anfragen', label: 'Offene Anfragen', icon: 'Clock', isOpenStatus: true },
  { id: 'reklamation', label: 'Reklamation', icon: 'MessageSquareWarning', color: 'destructive' },
  { id: 'kommunikation', label: 'Kommunikation', icon: 'Mail' },
  { id: 'archiv', label: 'Archiv', icon: 'Archive' },
];

// Spargelmesser-spezifische Kategorien (mit Druckdaten am Ende, nach Archiv)
export const CUSTOMER_CATEGORIES_MESSER: DocumentCategoryInfo[] = [
  ...CUSTOMER_CATEGORIES_BASE,  // Alle Basis-Kategorien inkl. Archiv
  { id: 'druckdaten', label: 'Druckdaten', shortCode: 'DD', icon: 'Printer' },  // NUR für Messer (nach Archiv)
];

// Alias für Abwärtskompatibilität (= Folie-Kategorien)
export const CUSTOMER_CATEGORIES: DocumentCategoryInfo[] = CUSTOMER_CATEGORIES_BASE;

/**
 * Gibt die passenden Kategorien für einen Kunden-Ordner zurück.
 * @param folderId - "messer" oder "folie"
 * @returns Kategorie-Liste (Messer hat zusätzlich "Druckdaten")
 */
export function getCustomerCategoriesForFolder(folderId: string): DocumentCategoryInfo[] {
  return folderId === 'messer' ? CUSTOMER_CATEGORIES_MESSER : CUSTOMER_CATEGORIES_BASE;
}

// Lieferanten-Kategorien (mit Bestellungen)
export const SUPPLIER_CATEGORIES: DocumentCategoryInfo[] = [
  { id: 'anfragen', label: 'Anfragen', icon: 'HelpCircle' },
  { id: 'angebote', label: 'Angebote', shortCode: 'AG', icon: 'FileText' },
  { id: 'auftragsbestätigung', label: 'Auftragsbestätigung', shortCode: 'AB', icon: 'FileCheck' },
  { id: 'lieferscheine', label: 'Lieferscheine', shortCode: 'LS', icon: 'Truck' },
  { id: 'rechnungen', label: 'Rechnungen', shortCode: 'RG', icon: 'Receipt' },
  { id: 'bestellungen', label: 'Bestellungen', shortCode: 'B', icon: 'ShoppingCart' },  // NUR Lieferanten!
  { id: 'storno', label: 'Storno', shortCode: 'ST', icon: 'XCircle', color: 'destructive' },
  { id: 'mahnungen', label: 'Mahnungen', icon: 'AlertTriangle', color: 'warning' },
  { id: 'offene_rechnungen', label: 'Offene Rechnungen', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_angebote', label: 'Offene Angebote', icon: 'Clock', isOpenStatus: true },
  { id: 'offene_anfragen', label: 'Offene Anfragen', icon: 'Clock', isOpenStatus: true },
  { id: 'reklamation', label: 'Reklamation', icon: 'MessageSquareWarning', color: 'destructive' },
  { id: 'kommunikation', label: 'Kommunikation', icon: 'Mail' },
  { id: 'archiv', label: 'Archiv', icon: 'Archive' },
];

// Dokumentenzaehlung pro Kategorie
export type DocumentCounts = Record<string, number>;

// Entity mit Dokumentenzaehlung pro Kategorie
export interface EntityWithDocumentCounts {
  id: string;
  name: string;
  displayName?: string;
  entityType: 'customer' | 'supplier';
  documentCounts: DocumentCounts;
  totalDocuments: number;
  lastDocumentDate?: string;
  isActive: boolean;
}

// ==================== FILTER & API TYPES ====================

/**
 * Verarbeitungsstatus eines Dokuments (OCR)
 */
export type DocumentProcessingStatus =
  | 'pending'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

/**
 * Zahlungsstatus für Rechnungen
 */
export type PaymentStatus = 'offen' | 'bezahlt' | 'überfällig' | 'teilbezahlt';

/**
 * Sortier-Optionen für Dokumente
 */
export type DocumentSortField =
  | 'document_date'
  | 'created_at'
  | 'filename'
  | 'total_amount'
  | 'due_date'
  | 'payment_status';

export type SortOrder = 'asc' | 'desc';

/**
 * Filter für Kategorie-Dokumente
 * Wird von der API als Query-Parameter verwendet
 */
export interface CategoryDocumentFilter {
  // Basis-Parameter (aus Route)
  businessEntityId: string;
  folderId: string;
  category: string;
  entityType: 'customer' | 'supplier';

  // Text-Filter
  search?: string;

  // Datums-Filter (ISO-Strings)
  dateFrom?: string;
  dateTo?: string;

  // Betrags-Filter
  amountMin?: number;
  amountMax?: number;

  // Status-Filter
  processingStatus?: DocumentProcessingStatus[];
  paymentStatus?: PaymentStatus[];

  // Weitere Filter
  tags?: string[];

  // Sortierung
  sortBy: DocumentSortField;
  sortOrder: SortOrder;

  // Pagination
  page: number;
  pageSize: number;
}

/**
 * Einzelnes Dokument in der Kategorie-Liste
 */
export interface CategoryDocumentResponse {
  id: string;
  filename: string;
  originalFilename: string;
  documentType: string;
  processingStatus: DocumentProcessingStatus;
  fileSize: number;
  pageCount: number;
  mimeType: string | null;
  createdAt: string;
  updatedAt: string;
  documentDate: string | null;
  ocrConfidence: number | null;
  documentNumber: string | null;
  totalAmount: number | null;
  currency: string;
  dueDate: string | null;
  paymentStatus: PaymentStatus;
  paidAmount: number | null;
  partnerName: string | null;
  tags: string[];
  thumbnailUrl: string | null;
  previewUrl: string | null;
  // Skonto-Daten (aus OCR-Extraktion)
  skontoPercent: number | null;
  skontoDays: number | null;
  skontoDeadline: string | null;
  skontoAmount: number | null;
}

/**
 * Aggregationen für die Dokumenten-Liste
 */
export interface CategoryDocumentAggregations {
  totalDocuments: number;
  documentsByStatus: Record<string, number>;
  documentsByPaymentStatus: Record<string, number>;
  totalAmount: number;
  totalPaid: number;
  totalOpen: number;
  totalOverdue: number;
  currency: string;
  earliestDate: string | null;
  latestDate: string | null;
  overdueCount: number;
}

/**
 * API Response für Kategorie-Dokumente
 */
export interface CategoryDocumentListResponse {
  items: CategoryDocumentResponse[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/**
 * Ergebnis einer Bulk-Aktion
 */
export interface BulkActionResult {
  successCount: number;
  failedCount: number;
  errors: Array<{ documentId: string; error: string }>;
}

/**
 * Default-Filter-Werte
 */
export const DEFAULT_CATEGORY_FILTER: Omit<CategoryDocumentFilter, 'businessEntityId' | 'folderId' | 'category' | 'entityType'> = {
  sortBy: 'document_date',
  sortOrder: 'desc',
  page: 0,
  pageSize: 25,
};

/**
 * Status-Konfiguration für Badges
 */
export const PROCESSING_STATUS_CONFIG: Record<DocumentProcessingStatus, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pending: { label: 'Ausstehend', variant: 'secondary' },
  queued: { label: 'In Warteschlange', variant: 'secondary' },
  processing: { label: 'Verarbeitung', variant: 'default' },
  completed: { label: 'Verarbeitet', variant: 'outline' },
  failed: { label: 'Fehlgeschlagen', variant: 'destructive' },
  cancelled: { label: 'Abgebrochen', variant: 'secondary' },
};

export const PAYMENT_STATUS_CONFIG: Record<PaymentStatus, { label: string; className: string }> = {
  offen: { label: 'Offen', className: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  bezahlt: { label: 'Bezahlt', className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  überfällig: { label: 'Überfällig', className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  teilbezahlt: { label: 'Teilbezahlt', className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
};

/**
 * Kategorien die Zahlungsstatus haben (Rechnungen-bezogen)
 */
export const CATEGORIES_WITH_PAYMENT_STATUS = ['rechnungen', 'offene_rechnungen', 'mahnungen'];

/**
 * Mapping von Kategorie zu Backend document_type
 */
export const CATEGORY_TO_DOCUMENT_TYPE: Record<string, string> = {
  anfragen: 'inquiry',
  angebote: 'offer',
  auftragsbestätigung: 'order_confirmation',
  lieferscheine: 'delivery_note',
  rechnungen: 'invoice',
  bestellungen: 'order',
  storno: 'cancellation',
  mahnungen: 'reminder',
  offene_rechnungen: 'invoice',
  offene_angebote: 'offer',
  offene_anfragen: 'inquiry',
  reklamation: 'complaint',
  kommunikation: 'communication',
  archiv: 'archive',
  druckdaten: 'print_data',  // NUR für Spargelmesser-Kunden!
};

// ==================== VORGANGS-TYPEN ====================

/**
 * Status eines Vorgangs
 */
export type TransactionStatus =
  | 'draft'       // Entwurf
  | 'pending'     // In Bearbeitung
  | 'completed'   // Abgeschlossen (alle Schritte erledigt)
  | 'cancelled';  // Abgebrochen

/**
 * Status eines einzelnen Schritts im Vorgang
 */
export type TransactionStepStatus =
  | 'pending'     // Noch nicht begonnen
  | 'active'      // Aktuell in Bearbeitung
  | 'completed'   // Abgeschlossen
  | 'skipped';    // Übersprungen

/**
 * Typ eines Vorgang-Schritts (entspricht Dokumentkategorien)
 */
export type TransactionStepType =
  | 'anfrage'
  | 'angebot'
  | 'auftrag'
  | 'lieferschein'
  | 'rechnung'
  | 'zahlung';

/**
 * Konfiguration für Vorgang-Schritte
 */
export interface TransactionStepConfig {
  type: TransactionStepType;
  label: string;
  shortCode: string;
  icon: string;
  categoryId: string;  // Mapping zu Dokumentkategorie
}

/**
 * Standard-Vorgang-Schritte (Angebot → Auftrag → Lieferschein → Rechnung → Zahlung)
 */
export const TRANSACTION_STEPS: TransactionStepConfig[] = [
  { type: 'anfrage', label: 'Anfrage', shortCode: 'AF', icon: 'HelpCircle', categoryId: 'anfragen' },
  { type: 'angebot', label: 'Angebot', shortCode: 'AG', icon: 'FileText', categoryId: 'angebote' },
  { type: 'auftrag', label: 'Auftrag', shortCode: 'AB', icon: 'FileCheck', categoryId: 'auftragsbestätigung' },
  { type: 'lieferschein', label: 'Lieferschein', shortCode: 'LS', icon: 'Truck', categoryId: 'lieferscheine' },
  { type: 'rechnung', label: 'Rechnung', shortCode: 'RG', icon: 'Receipt', categoryId: 'rechnungen' },
  { type: 'zahlung', label: 'Zahlung', shortCode: 'ZA', icon: 'Banknote', categoryId: '' },  // Kein Dokument, nur Status
];

/**
 * Einzelner Schritt in einem Vorgang
 */
export interface TransactionStep {
  id: string;
  type: TransactionStepType;
  status: TransactionStepStatus;
  documentId: string | null;
  documentNumber: string | null;
  completedAt: string | null;
  amount: number | null;
  currency: string;
}

/**
 * Ein Vorgang (z.B. eine Bestellung von Anfrage bis Zahlung)
 */
export interface Transaction {
  id: string;
  transactionNumber: string;  // z.B. "VG-2024-001"
  name: string;               // Beschreibung, z.B. "Bestellung Druckplatten"
  status: TransactionStatus;
  entityId: string;
  entityName: string;
  folderId: string;
  steps: TransactionStep[];
  totalAmount: number | null;
  currency: string;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  lastActivityAt: string;
}

/**
 * API Response für Vorgänge-Liste
 */
export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/**
 * Filter für Vorgänge-Liste
 */
export interface TransactionFilter {
  entityId?: string;
  folderId?: string;
  status?: TransactionStatus[];
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  page: number;
  pageSize: number;
}

/**
 * Default-Filter für Vorgänge
 */
export const DEFAULT_TRANSACTION_FILTER: Omit<TransactionFilter, 'entityId' | 'folderId'> = {
  page: 0,
  pageSize: 20,
};

// ==================== OCR REVIEW WORKFLOW TYPES ====================

/**
 * Invoice Direction (Eingang vs Ausgang)
 */
export type InvoiceDirection = 'incoming' | 'outgoing' | null;

/**
 * Quick Classification Ergebnis vom Backend
 * Wird von /ocr/process nach OCR automatisch ausgeführt
 */
export interface QuickClassificationResult {
  direction: InvoiceDirection;
  confidence: number;
  matchedEntityId: string | null;
  matchedEntityName: string | null;
  matchedEntityType: 'customer' | 'supplier' | null;
  matchedEntityConfidence: number;
  suggestedDocumentType: string;
  suggestedTags: string[];
  extractedData: {
    documentNumber: string | null;
    documentDate: string | null;
    totalAmount: number | null;
    currency: string;
    dueDate: string | null;
    ibanFound: string | null;
    vatIdFound: string | null;
  };
}

/**
 * Rename-Vorschlag vom Backend
 * Format: {SupplierName}_{InvoiceNumber}.pdf
 */
export interface RenameSuggestion {
  suggestedFilename: string;
  confidence: number;
  parts: {
    entityName: string | null;
    documentNumber: string | null;
  };
}

/**
 * Erweitertes OCR-Ergebnis von /ocr/process
 * Enthält OCR-Text + Quick Classification + Rename-Vorschlag
 */
export interface OCRProcessResult {
  success: boolean;
  text: string;
  confidence: number;
  pageCount: number;
  processingTimeMs: number;
  backend: string;

  // Neu: Quick Classification
  quickClassification: QuickClassificationResult | null;

  // Neu: Rename-Vorschlag
  renameSuggestion: RenameSuggestion | null;

  // Neu: Temp-File-ID für späteres Speichern
  tempFileId: string;
}

/**
 * Request zum finalen Speichern nach OCR-Review
 * Wird an POST /api/v1/documents/upload-complete gesendet
 */
export interface UploadCompleteRequest {
  tempFileId: string;
  finalFilename: string;
  documentType: string;

  // Metadaten (aus Quick Classification oder manuell)
  documentNumber?: string;
  documentDate?: string;  // ISO Date String
  totalAmount?: number;
  currency?: string;
  dueDate?: string;

  // NEU: Rechnungsrichtung und Auto-erkannte Felder
  direction?: InvoiceDirection;
  ibanFound?: string | null;
  vatIdFound?: string | null;

  // Entity-Linking
  businessEntityId?: string;
  folderId: string;
  category: string;
  entityType: 'customer' | 'supplier';

  // Tags
  tags?: string[];

  // OCR-Daten (optional, zur Speicherung)
  ocrText?: string;
  ocrConfidence?: number;
}

/**
 * Response von /api/v1/documents/upload-complete
 */
export interface UploadCompleteResponse {
  success: boolean;
  documentId: string;
  filename: string;
  storagePath: string;
  fileSize: number;
  entityLinked: boolean;
  entityName?: string;
  message: string;
}

/**
 * Status des Upload-Workflows
 */
export type UploadWorkflowStatus =
  | 'idle'           // Kein Upload aktiv
  | 'uploading'      // Datei wird hochgeladen
  | 'processing'     // OCR läuft
  | 'classifying'    // Quick Classification läuft
  | 'review'         // Warten auf User-Review
  | 'saving'         // Wird gespeichert
  | 'completed'      // Erfolgreich abgeschlossen
  | 'error';         // Fehler aufgetreten

/**
 * State für den Upload-Workflow Hook
 */
export interface UploadWorkflowState {
  status: UploadWorkflowStatus;
  progress: number;
  file: File | null;
  fileUrl: string | null;
  tempFileId: string | null;
  ocrResult: {
    text: string;
    confidence: number;
  } | null;
  quickClassification: QuickClassificationResult | null;
  renameSuggestion: RenameSuggestion | null;
  error: string | null;
}

/**
 * Optionen für den Upload-Workflow Hook
 */
export interface UseDocumentUploadOptions {
  entityId: string;
  entityType: 'customer' | 'supplier';
  folderId: string;
  category: string;
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}

/**
 * Entity-Match Badge Konfiguration
 */
export const ENTITY_MATCH_CONFIDENCE_LEVELS = {
  high: { threshold: 0.9, label: 'Sehr sicher', color: 'bg-green-100 text-green-800' },
  medium: { threshold: 0.75, label: 'Wahrscheinlich', color: 'bg-yellow-100 text-yellow-800' },
  low: { threshold: 0.5, label: 'Möglich', color: 'bg-orange-100 text-orange-800' },
  none: { threshold: 0, label: 'Nicht erkannt', color: 'bg-gray-100 text-gray-800' },
} as const;

/**
 * Ermittelt das Confidence-Level für ein Entity-Match
 */
export function getEntityMatchLevel(confidence: number): keyof typeof ENTITY_MATCH_CONFIDENCE_LEVELS {
  if (confidence >= ENTITY_MATCH_CONFIDENCE_LEVELS.high.threshold) return 'high';
  if (confidence >= ENTITY_MATCH_CONFIDENCE_LEVELS.medium.threshold) return 'medium';
  if (confidence >= ENTITY_MATCH_CONFIDENCE_LEVELS.low.threshold) return 'low';
  return 'none';
}

// ==================== DOCUMENT TYPE OPTIONS ====================

/**
 * Dokumenttyp-Option fuer Select-Dropdown
 */
export interface DocumentTypeOption {
  value: string;
  label: string;
}

/**
 * Dokumenttypen fuer Kunden (Ausgangsbelege)
 */
export const CUSTOMER_DOCUMENT_TYPES: DocumentTypeOption[] = [
  { value: 'offer', label: 'Angebot' },
  { value: 'order_confirmation', label: 'Auftragsbestätigung' },
  { value: 'delivery_note', label: 'Lieferschein' },
  { value: 'invoice', label: 'Rechnung' },
  { value: 'credit_note', label: 'Gutschrift' },
  { value: 'reminder', label: 'Mahnung' },
  { value: 'complaint', label: 'Reklamation' },
  { value: 'correspondence', label: 'Korrespondenz' },
  { value: 'contract', label: 'Vertrag' },
  { value: 'document', label: 'Sonstiges Dokument' },
];

/**
 * Dokumenttypen fuer Lieferanten (Eingangsbelege)
 */
export const SUPPLIER_DOCUMENT_TYPES: DocumentTypeOption[] = [
  { value: 'inquiry', label: 'Anfrage' },
  { value: 'order', label: 'Bestellung' },
  { value: 'order_confirmation', label: 'Auftragsbestätigung' },
  { value: 'delivery_note', label: 'Lieferschein' },
  { value: 'invoice', label: 'Eingangsrechnung' },
  { value: 'credit_note', label: 'Gutschrift' },
  { value: 'complaint', label: 'Reklamation' },
  { value: 'correspondence', label: 'Korrespondenz' },
  { value: 'contract', label: 'Vertrag' },
  { value: 'certificate', label: 'Zertifikat/Zeugnis' },
  { value: 'document', label: 'Sonstiges Dokument' },
];

// ==================== RE-EXPORTS FROM ABLAGE-TYPES ====================
// Upload-bezogene Types und Utilities fuer DocumentUploadDialog

export {
  type UploadFile,
  type UploadStatus,
  type UploadRequest,
  type UploadResponse,
  type OCRBackend,
  OCR_BACKENDS,
  formatFileSize,
  getStatusColor,
  getStatusLabel,
} from './types/ablage-types';

// ==================== MULTI-FILE UPLOAD TYPES ====================

/**
 * Status einer einzelnen Datei im Multi-Upload Workflow
 */
export type AblageUploadFileStatus =
  | 'pending'      // Wartet auf Upload
  | 'uploading'    // Wird hochgeladen
  | 'processing'   // OCR laeuft
  | 'review'       // Bereit zur Pruefung (Quick Classification fertig)
  | 'completed'    // Gespeichert
  | 'error';       // Fehler

/**
 * Einzelne Datei im Multi-Upload Workflow
 * Basiert auf dem Upload Wizard Pattern
 */
export interface AblageUploadingFile {
  // Identifikation
  id: string;
  file: File | null;                  // Kann null sein nach Page-Reload
  originalFilename: string;           // Fuer Persistenz

  // Status
  status: AblageUploadFileStatus;
  progress: number;                   // Upload-Progress (0-100)
  ocrProgress?: number;               // OCR-Progress (0-100)
  error?: string;

  // IDs nach Upload
  documentId?: string;                // Backend Document ID
  tempFileId?: string;                // Temp Storage ID
  taskId?: string;                    // Celery Task ID

  // Preview URL (Blob URL fuer lokale Vorschau)
  fileUrl?: string;

  // Quick Classification Ergebnis
  quickClassification?: QuickClassificationResult;

  // Rename-Vorschlag
  renameSuggestion?: RenameSuggestion;

  // User-Bestaetigung
  confirmedDirection?: InvoiceDirection;
  renameConfirmed?: boolean;
  renamedFilename?: string;

  // OCR-Ergebnis
  ocrResult?: {
    text: string;
    confidence: number;
    pageCount: number;
  };
}

/**
 * State fuer den Multi-File Upload Hook
 */
export interface AblageMultiUploadState {
  files: AblageUploadingFile[];
  isUploading: boolean;
  hasErrors: boolean;
  pendingReviewCount: number;
  completedCount: number;
}

/**
 * Optionen fuer den Multi-File Upload Hook
 */
export interface UseAblageMultiUploadOptions {
  entityId: string;
  entityName: string;
  entityType: 'customer' | 'supplier';
  folderId: string;
  folderName: string;
  category: string;
  categoryName?: string;
  ocrBackend?: string;
  onAllComplete?: () => void;
  onFileComplete?: (fileId: string, documentId: string) => void;
  onFileError?: (fileId: string, error: Error) => void;
}
