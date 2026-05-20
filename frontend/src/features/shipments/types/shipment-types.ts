/**
 * Shipment Tracking Types
 *
 * TypeScript Typen für das Sendungsverfolgung-Feature.
 * Konsistent mit Backend-Schema: Shipment Model und API Responses.
 */

// ==================== Enums ====================

export type ShipmentStatus =
  | 'label_created'    // Label erstellt
  | 'picked_up'        // Abgeholt
  | 'in_transit'       // In Transit
  | 'out_for_delivery' // Zustellung
  | 'delivered'        // Zugestellt
  | 'exception'        // Problem
  | 'returned'         // Retourniert
  | 'unknown';         // Unbekannt

export type ShipmentDirection =
  | 'inbound'   // Eingehend (Wareneingang)
  | 'outbound'  // Ausgehend (Versand)
  | 'return';   // Retoure

export type CarrierId =
  | 'dhl'
  | 'dpd'
  | 'hermes'
  | 'ups'
  | 'gls'
  | 'fedex'
  | 'deutsche_post'
  | 'unknown';

// ==================== Carrier Info ====================

export interface CarrierInfo {
  id: CarrierId;
  name: string;
  description: string;
  trackingUrlPattern: string;
}

export const CARRIERS: CarrierInfo[] = [
  {
    id: 'dhl',
    name: 'DHL',
    description: 'DHL Paket Deutschland - Marktführer',
    trackingUrlPattern: 'https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={tracking_number}',
  },
  {
    id: 'dpd',
    name: 'DPD',
    description: 'DPD Deutschland - B2B stark',
    trackingUrlPattern: 'https://tracking.dpd.de/status/de_DE/parcel/{tracking_number}',
  },
  {
    id: 'hermes',
    name: 'Hermes',
    description: 'Hermes Deutschland - B2C stark',
    trackingUrlPattern: 'https://www.myhermes.de/empfangen/sendungsverfolgung/?sendung={tracking_number}',
  },
  {
    id: 'ups',
    name: 'UPS',
    description: 'UPS - International stark',
    trackingUrlPattern: 'https://www.ups.com/track?tracknum={tracking_number}&loc=de_DE',
  },
  {
    id: 'gls',
    name: 'GLS',
    description: 'GLS Germany - B2B stark',
    trackingUrlPattern: 'https://gls-group.com/DE/de/paketverfolgung?match={tracking_number}',
  },
  {
    id: 'fedex',
    name: 'FedEx',
    description: 'FedEx - Express/International',
    trackingUrlPattern: 'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
  },
  {
    id: 'deutsche_post',
    name: 'Deutsche Post',
    description: 'Deutsche Post - Briefe und Einschreiben',
    trackingUrlPattern: 'https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode={tracking_number}',
  },
];

// ==================== API Types ====================

/**
 * Tracking Event Response
 */
export interface ShipmentEventResponse {
  id: string;
  timestamp: string;
  status: ShipmentStatus;
  description: string | null;
  location: string | null;
  postalCode: string | null;
  countryCode: string | null;
}

/**
 * Backend Response (snake_case)
 */
export interface ShipmentEventBackend {
  id: string;
  timestamp: string;
  status: string;
  description: string | null;
  location: string | null;
  postal_code: string | null;
  country_code: string | null;
}

/**
 * Shipment Response (Frontend)
 */
export interface ShipmentResponse {
  id: string;
  trackingNumber: string;
  carrier: CarrierId;
  direction: ShipmentDirection;
  status: ShipmentStatus;
  statusDescription: string | null;
  trackingUrl: string | null;
  estimatedDelivery: string | null;
  actualDelivery: string | null;
  lastTrackingUpdate: string | null;
  origin: string | null;
  destination: string | null;
  weightKg: number | null;
  serviceType: string | null;
  reference: string | null;
  notes: string | null;
  shippingCost: number | null;
  currency: string;
  entityId: string | null;
  documentId: string | null;
  createdAt: string;
  updatedAt: string;
  events: ShipmentEventResponse[];
}

/**
 * Backend Response (snake_case)
 */
export interface ShipmentBackend {
  id: string;
  tracking_number: string;
  carrier: string;
  direction: string;
  status: string;
  status_description: string | null;
  tracking_url: string | null;
  estimated_delivery: string | null;
  actual_delivery: string | null;
  last_tracking_update: string | null;
  origin: string | null;
  destination: string | null;
  weight_kg: number | null;
  service_type: string | null;
  reference: string | null;
  notes: string | null;
  shipping_cost: number | null;
  currency: string;
  entity_id: string | null;
  document_id: string | null;
  created_at: string;
  updated_at: string;
  events: ShipmentEventBackend[];
}

/**
 * Paginated List Response
 */
export interface ShipmentListResponse {
  items: ShipmentResponse[];
  total: number;
  page: number;
  perPage: number;
  pages: number;
}

/**
 * Backend List Response
 */
export interface ShipmentListBackend {
  items: ShipmentBackend[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

/**
 * Carrier Detection Response
 */
export interface CarrierDetectionResponse {
  trackingNumber: string;
  detectedCarrier: CarrierId;
  trackingUrl: string | null;
  confidence: 'high' | 'medium' | 'low';
}

/**
 * Shipment Summary
 */
export interface ShipmentSummaryResponse {
  total: number;
  byCarrier: Record<string, number>;
  byStatus: Record<string, number>;
  pendingDelivery: number;
  deliveredToday: number;
  exceptions: number;
}

/**
 * Backend Summary
 */
export interface ShipmentSummaryBackend {
  total: number;
  by_carrier: Record<string, number>;
  by_status: Record<string, number>;
  pending_delivery: number;
  delivered_today: number;
  exceptions: number;
}

/**
 * Carrier Statistics
 */
export interface CarrierStatisticsResponse {
  carrier: CarrierId;
  totalShipments: number;
  delivered: number;
  avgDeliveryDays: number;
  onTimeRate: number;
  exceptionRate: number;
}

/**
 * Backend Statistics
 */
export interface CarrierStatisticsBackend {
  carrier: string;
  total_shipments: number;
  delivered: number;
  avg_delivery_days: number;
  on_time_rate: number;
  exception_rate: number;
}

// ==================== Filter Types ====================

export interface ShipmentFilter {
  page: number;
  perPage: number;
  direction?: ShipmentDirection;
  status?: ShipmentStatus;
  carrier?: CarrierId;
  entityId?: string;
}

// ==================== Create/Update Types ====================

export interface ShipmentCreate {
  trackingNumber: string;
  direction?: ShipmentDirection;
  carrier?: CarrierId;
  entityId?: string;
  documentId?: string;
  reference?: string;
  notes?: string;
  shippingCost?: number;
}

export interface ShipmentUpdate {
  reference?: string;
  notes?: string;
  shippingCost?: number;
  entityId?: string;
  documentId?: string;
}

// ==================== UI Labels (Deutsch) ====================

export const UI_LABELS = {
  // Page
  pageTitle: 'Sendungsverfolgung',
  pageSubtitle: 'Alle Sendungen verfolgen und verwalten',

  // Tab/Sections
  tabOverview: 'Übersicht',
  tabAllShipments: 'Alle Sendungen',
  tabStatistics: 'Statistiken',

  // Status Labels
  statusLabelCreated: 'Label erstellt',
  statusPickedUp: 'Abgeholt',
  statusInTransit: 'Unterwegs',
  statusOutForDelivery: 'Zustellung',
  statusDelivered: 'Zugestellt',
  statusException: 'Problem',
  statusReturned: 'Retourniert',
  statusUnknown: 'Unbekannt',

  // Direction Labels
  directionInbound: 'Eingehend',
  directionOutbound: 'Ausgehend',
  directionReturn: 'Retoure',

  // Summary Cards
  summaryTotal: 'Gesamt',
  summaryPending: 'Ausstehend',
  summaryDeliveredToday: 'Heute zugestellt',
  summaryExceptions: 'Probleme',

  // Table Headers
  tableTrackingNumber: 'Sendungsnummer',
  tableCarrier: 'Versanddienstleister',
  tableStatus: 'Status',
  tableDirection: 'Richtung',
  tableDestination: 'Zielort',
  tableEstimatedDelivery: 'Vorr. Zustellung',
  tableCreatedAt: 'Erstellt',
  tableActions: 'Aktionen',

  // Actions
  actionTrack: 'Verfolgen',
  actionRefresh: 'Aktualisieren',
  actionDetails: 'Details',
  actionDelete: 'Löschen',
  actionCreate: 'Sendung hinzufügen',
  actionExternalTracking: 'Externe Verfolgung',

  // Filter Labels
  filterStatus: 'Status',
  filterCarrier: 'Versanddienstleister',
  filterDirection: 'Richtung',
  filterAll: 'Alle',
  filterReset: 'Filter zurücksetzen',

  // Detail View
  detailTitle: 'Sendungsdetails',
  detailTrackingNumber: 'Sendungsnummer',
  detailCarrier: 'Versanddienstleister',
  detailStatus: 'Status',
  detailOrigin: 'Absender',
  detailDestination: 'Empfänger',
  detailWeight: 'Gewicht',
  detailServiceType: 'Serviceart',
  detailReference: 'Referenz',
  detailNotes: 'Notizen',
  detailShippingCost: 'Versandkosten',
  detailCreatedAt: 'Erstellt am',
  detailUpdatedAt: 'Aktualisiert am',
  detailEstimatedDelivery: 'Vorr. Zustellung',
  detailActualDelivery: 'Zugestellt am',

  // Timeline
  timelineTitle: 'Sendungsverlauf',
  timelineEmpty: 'Keine Events vorhanden',

  // Form
  formTrackingNumber: 'Sendungsnummer',
  formTrackingNumberPlaceholder: 'z.B. 00340434173456789012',
  formCarrier: 'Versanddienstleister',
  formCarrierAuto: 'Automatisch erkennen',
  formDirection: 'Richtung',
  formReference: 'Referenz (optional)',
  formNotes: 'Notizen (optional)',
  formShippingCost: 'Versandkosten (optional)',
  formSubmit: 'Sendung erstellen',
  formCancel: 'Abbrechen',

  // Toasts
  successCreate: 'Sendung erfolgreich erstellt',
  successUpdate: 'Sendung aktualisiert',
  successDelete: 'Sendung gelöscht',
  successRefresh: 'Tracking-Daten aktualisiert',
  errorLoad: 'Fehler beim Laden der Sendungen',
  errorCreate: 'Fehler beim Erstellen der Sendung',
  errorUpdate: 'Fehler beim Aktualisieren',
  errorDelete: 'Fehler beim Löschen',
  errorRefresh: 'Fehler beim Aktualisieren der Tracking-Daten',

  // Empty States
  emptyTitle: 'Keine Sendungen',
  emptyDescription: 'Es wurden noch keine Sendungen erfasst.',
  emptyAction: 'Erste Sendung erstellen',

  // Statistics
  statsAvgDeliveryDays: 'Ø Lieferzeit (Tage)',
  statsOnTimeRate: 'Pünktlichkeitsrate',
  statsExceptionRate: 'Problemrate',
  statsDelivered: 'Zugestellt',
} as const;

// ==================== Status Styles ====================

export const STATUS_STYLES: Record<ShipmentStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: string }> = {
  label_created: { label: UI_LABELS.statusLabelCreated, variant: 'outline', icon: 'tag' },
  picked_up: { label: UI_LABELS.statusPickedUp, variant: 'secondary', icon: 'package' },
  in_transit: { label: UI_LABELS.statusInTransit, variant: 'secondary', icon: 'truck' },
  out_for_delivery: { label: UI_LABELS.statusOutForDelivery, variant: 'default', icon: 'map-pin' },
  delivered: { label: UI_LABELS.statusDelivered, variant: 'default', icon: 'check-circle' },
  exception: { label: UI_LABELS.statusException, variant: 'destructive', icon: 'alert-triangle' },
  returned: { label: UI_LABELS.statusReturned, variant: 'outline', icon: 'rotate-ccw' },
  unknown: { label: UI_LABELS.statusUnknown, variant: 'outline', icon: 'help-circle' },
};

export const DIRECTION_STYLES: Record<ShipmentDirection, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  inbound: { label: UI_LABELS.directionInbound, variant: 'secondary' },
  outbound: { label: UI_LABELS.directionOutbound, variant: 'default' },
  return: { label: UI_LABELS.directionReturn, variant: 'outline' },
};
