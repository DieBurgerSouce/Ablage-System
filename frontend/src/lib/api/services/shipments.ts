/**
 * Shipment Tracking API Service
 *
 * Zentraler API-Service für Sendungsverfolgung.
 * Delegiert an die Feature-Level API in features/shipments.
 *
 * Endpoints: /api/v1/shipments/*
 */

export {
  shipmentService,
  ShipmentApiError,
  getTrackingUrl,
  getCarrierDisplayName,
} from '@/features/shipments/api/shipment-api';

export type {
  ShipmentResponse,
  ShipmentListResponse,
  ShipmentSummaryResponse,
  CarrierStatisticsResponse,
  CarrierDetectionResponse,
  ShipmentFilter,
  ShipmentCreate,
  ShipmentUpdate,
  ShipmentStatus,
  ShipmentDirection,
  CarrierId,
  CarrierInfo,
  ShipmentEventResponse,
} from '@/features/shipments/types/shipment-types';
