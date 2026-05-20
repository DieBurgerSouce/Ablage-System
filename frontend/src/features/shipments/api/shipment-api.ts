/**
 * Shipment Tracking API Service
 *
 * Kommuniziert mit den /api/v1/shipments Endpoints
 * für Sendungsverfolgung und Carrier-Integration.
 *
 * Features:
 * - CRUD für Sendungen
 * - Tracking-Abfragen
 * - Carrier-Erkennung
 * - Statistiken
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type {
  ShipmentResponse,
  ShipmentBackend,
  ShipmentEventBackend,
  ShipmentEventResponse,
  ShipmentListResponse,
  ShipmentListBackend,
  ShipmentSummaryResponse,
  ShipmentSummaryBackend,
  CarrierStatisticsResponse,
  CarrierStatisticsBackend,
  CarrierDetectionResponse,
  ShipmentFilter,
  ShipmentCreate,
  ShipmentUpdate,
  CarrierId,
  ShipmentStatus,
  ShipmentDirection,
  CarrierInfo,
} from '../types/shipment-types';

// ==================== Error Classes ====================

export class ShipmentApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'ShipmentApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformEvent(event: ShipmentEventBackend): ShipmentEventResponse {
  return {
    id: event.id,
    timestamp: event.timestamp,
    status: event.status as ShipmentStatus,
    description: event.description,
    location: event.location,
    postalCode: event.postal_code,
    countryCode: event.country_code,
  };
}

function transformShipment(shipment: ShipmentBackend): ShipmentResponse {
  return {
    id: shipment.id,
    trackingNumber: shipment.tracking_number,
    carrier: shipment.carrier as CarrierId,
    direction: shipment.direction as ShipmentDirection,
    status: shipment.status as ShipmentStatus,
    statusDescription: shipment.status_description,
    trackingUrl: shipment.tracking_url,
    estimatedDelivery: shipment.estimated_delivery,
    actualDelivery: shipment.actual_delivery,
    lastTrackingUpdate: shipment.last_tracking_update,
    origin: shipment.origin,
    destination: shipment.destination,
    weightKg: shipment.weight_kg,
    serviceType: shipment.service_type,
    reference: shipment.reference,
    notes: shipment.notes,
    shippingCost: shipment.shipping_cost,
    currency: shipment.currency,
    entityId: shipment.entity_id,
    documentId: shipment.document_id,
    createdAt: shipment.created_at,
    updatedAt: shipment.updated_at,
    events: (shipment.events || []).map(transformEvent),
  };
}

function transformSummary(summary: ShipmentSummaryBackend): ShipmentSummaryResponse {
  return {
    total: summary.total,
    byCarrier: summary.by_carrier,
    byStatus: summary.by_status,
    pendingDelivery: summary.pending_delivery,
    deliveredToday: summary.delivered_today,
    exceptions: summary.exceptions,
  };
}

function transformStatistics(stats: CarrierStatisticsBackend): CarrierStatisticsResponse {
  return {
    carrier: stats.carrier as CarrierId,
    totalShipments: stats.total_shipments,
    delivered: stats.delivered,
    avgDeliveryDays: stats.avg_delivery_days,
    onTimeRate: stats.on_time_rate,
    exceptionRate: stats.exception_rate,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new ShipmentApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 409) {
      throw new ShipmentApiError(`${context}: ${message}`, 409, error);
    }

    if (statusCode === 400) {
      throw new ShipmentApiError(`${context}: ${message}`, 400, error);
    }

    if (statusCode === 503) {
      throw new ShipmentApiError(`${context}: Service nicht verfügbar`, 503, error);
    }

    throw new ShipmentApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new ShipmentApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Shipment Service ====================

export const shipmentService = {
  // ==================== List / Search ====================

  /**
   * Listet Sendungen mit Filter und Pagination
   */
  listShipments: async (
    filter: Partial<ShipmentFilter> = {}
  ): Promise<ShipmentListResponse> => {
    try {
      const params: Record<string, string | number> = {
        page: filter.page ?? 1,
        per_page: filter.perPage ?? 20,
      };

      if (filter.direction) {
        params.direction = filter.direction;
      }
      if (filter.status) {
        params.status = filter.status;
      }
      if (filter.carrier) {
        params.carrier = filter.carrier;
      }
      if (filter.entityId) {
        params.entity_id = filter.entityId;
      }

      const response = await apiClient.get<ShipmentListBackend>(
        '/shipments',
        { params }
      );

      return {
        items: response.data.items.map(transformShipment),
        total: response.data.total,
        page: response.data.page,
        perPage: response.data.per_page,
        pages: response.data.pages,
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { items: [], total: 0, page: 1, perPage: 20, pages: 0 };
      }
      handleApiError(error, 'Sendungen laden');
    }
  },

  // ==================== Summary ====================

  /**
   * Ruft Sendungs-Zusammenfassung ab
   */
  getSummary: async (): Promise<ShipmentSummaryResponse> => {
    try {
      const response = await apiClient.get<ShipmentSummaryBackend>(
        '/shipments/summary'
      );

      return transformSummary(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          total: 0,
          byCarrier: {},
          byStatus: {},
          pendingDelivery: 0,
          deliveredToday: 0,
          exceptions: 0,
        };
      }
      handleApiError(error, 'Zusammenfassung laden');
    }
  },

  // ==================== Statistics ====================

  /**
   * Ruft Carrier-Statistiken ab
   */
  getStatistics: async (days: number = 90): Promise<CarrierStatisticsResponse[]> => {
    try {
      const response = await apiClient.get<CarrierStatisticsBackend[]>(
        '/shipments/statistics',
        { params: { days } }
      );

      return response.data.map(transformStatistics);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Statistiken laden');
    }
  },

  // ==================== Get Single ====================

  /**
   * Ruft eine einzelne Sendung ab
   */
  getShipment: async (shipmentId: string): Promise<ShipmentResponse> => {
    try {
      const response = await apiClient.get<ShipmentBackend>(
        `/shipments/${shipmentId}`
      );

      return transformShipment(response.data);
    } catch (error) {
      handleApiError(error, 'Sendung laden');
    }
  },

  // ==================== Create ====================

  /**
   * Erstellt eine neue Sendung
   */
  createShipment: async (
    data: ShipmentCreate
  ): Promise<ShipmentResponse> => {
    try {
      const response = await apiClient.post<ShipmentBackend>(
        '/shipments',
        {
          tracking_number: data.trackingNumber,
          direction: data.direction ?? 'inbound',
          carrier: data.carrier,
          entity_id: data.entityId,
          document_id: data.documentId,
          reference: data.reference,
          notes: data.notes,
          shipping_cost: data.shippingCost,
        }
      );

      return transformShipment(response.data);
    } catch (error) {
      handleApiError(error, 'Sendung erstellen');
    }
  },

  // ==================== Update ====================

  /**
   * Aktualisiert eine Sendung
   */
  updateShipment: async (
    shipmentId: string,
    data: ShipmentUpdate
  ): Promise<ShipmentResponse> => {
    try {
      const payload: Record<string, unknown> = {};

      if (data.reference !== undefined) payload.reference = data.reference;
      if (data.notes !== undefined) payload.notes = data.notes;
      if (data.shippingCost !== undefined) payload.shipping_cost = data.shippingCost;
      if (data.entityId !== undefined) payload.entity_id = data.entityId;
      if (data.documentId !== undefined) payload.document_id = data.documentId;

      const response = await apiClient.patch<ShipmentBackend>(
        `/shipments/${shipmentId}`,
        payload
      );

      return transformShipment(response.data);
    } catch (error) {
      handleApiError(error, 'Sendung aktualisieren');
    }
  },

  // ==================== Delete ====================

  /**
   * Löscht eine Sendung (Soft-Delete)
   */
  deleteShipment: async (shipmentId: string): Promise<void> => {
    try {
      await apiClient.delete(`/shipments/${shipmentId}`);
    } catch (error) {
      handleApiError(error, 'Sendung löschen');
    }
  },

  // ==================== Refresh Tracking ====================

  /**
   * Aktualisiert Tracking-Daten einer Sendung
   */
  refreshTracking: async (shipmentId: string): Promise<ShipmentResponse> => {
    try {
      const response = await apiClient.post<ShipmentBackend>(
        `/shipments/${shipmentId}/refresh`
      );

      return transformShipment(response.data);
    } catch (error) {
      handleApiError(error, 'Tracking aktualisieren');
    }
  },

  /**
   * Aktualisiert alle aktiven Sendungen
   */
  refreshAllActive: async (): Promise<{ updated: number; failed: number }> => {
    try {
      const response = await apiClient.post<{ updated: number; failed: number }>(
        '/shipments/refresh-all'
      );

      return response.data;
    } catch (error) {
      handleApiError(error, 'Alle Sendungen aktualisieren');
    }
  },

  // ==================== Carrier Detection ====================

  /**
   * Erkennt Carrier anhand Tracking-Nummer
   */
  detectCarrier: async (trackingNumber: string): Promise<CarrierDetectionResponse> => {
    try {
      const response = await apiClient.get<{
        tracking_number: string;
        detected_carrier: string;
        tracking_url: string | null;
        confidence: 'high' | 'medium' | 'low';
      }>('/shipments/detect-carrier', {
        params: { tracking_number: trackingNumber },
      });

      return {
        trackingNumber: response.data.tracking_number,
        detectedCarrier: response.data.detected_carrier as CarrierId,
        trackingUrl: response.data.tracking_url,
        confidence: response.data.confidence,
      };
    } catch (error) {
      handleApiError(error, 'Carrier erkennen');
    }
  },

  // ==================== List Carriers ====================

  /**
   * Listet alle unterstützten Carrier auf
   */
  listCarriers: async (): Promise<CarrierInfo[]> => {
    try {
      const response = await apiClient.get<Array<{
        id: string;
        name: string;
        description: string;
        tracking_url_pattern: string;
      }>>('/shipments/carriers/list');

      return response.data.map((c) => ({
        id: c.id as CarrierId,
        name: c.name,
        description: c.description,
        trackingUrlPattern: c.tracking_url_pattern,
      }));
    } catch (error) {
      handleApiError(error, 'Carrier laden');
    }
  },
};

// ==================== Utility Functions ====================

/**
 * Generiert Tracking-URL für eine Sendung
 */
export function getTrackingUrl(trackingNumber: string, carrier: CarrierId): string | null {
  const patterns: Record<CarrierId, string | null> = {
    dhl: `https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode=${trackingNumber}`,
    dpd: `https://tracking.dpd.de/status/de_DE/parcel/${trackingNumber}`,
    hermes: `https://www.myhermes.de/empfangen/sendungsverfolgung/?sendung=${trackingNumber}`,
    ups: `https://www.ups.com/track?tracknum=${trackingNumber}&loc=de_DE`,
    gls: `https://gls-group.com/DE/de/paketverfolgung?match=${trackingNumber}`,
    fedex: `https://www.fedex.com/fedextrack/?trknbr=${trackingNumber}`,
    deutsche_post: `https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode=${trackingNumber}`,
    unknown: null,
  };

  return patterns[carrier] || null;
}

/**
 * Formatiert Carrier-Namen
 */
export function getCarrierDisplayName(carrier: CarrierId): string {
  const names: Record<CarrierId, string> = {
    dhl: 'DHL',
    dpd: 'DPD',
    hermes: 'Hermes',
    ups: 'UPS',
    gls: 'GLS',
    fedex: 'FedEx',
    deutsche_post: 'Deutsche Post',
    unknown: 'Unbekannt',
  };

  return names[carrier] || 'Unbekannt';
}
