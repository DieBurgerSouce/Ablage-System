// Dokumentkategorien fuer die Ablage-Struktur
export type CustomerDocumentCategory =
  | 'anfragen'
  | 'angebote'
  | 'auftragsbestaetigung'
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
  isOpenStatus?: boolean;  // Fuer "Offene X" Kategorien
}

// Kunden-Kategorien Definition
export const CUSTOMER_CATEGORIES: DocumentCategoryInfo[] = [
  { id: 'anfragen', label: 'Anfragen', icon: 'HelpCircle' },
  { id: 'angebote', label: 'Angebote', shortCode: 'AG', icon: 'FileText' },
  { id: 'auftragsbestaetigung', label: 'Auftragsbestaetigung', shortCode: 'AB', icon: 'FileCheck' },
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
  { id: 'auftragsbestaetigung', label: 'Auftragsbestaetigung', shortCode: 'AB', icon: 'FileCheck' },
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
