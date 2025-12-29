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
  | 'archiv';

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

// Kunden-Kategorien Definition
export const CUSTOMER_CATEGORIES: DocumentCategoryInfo[] = [
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
};
