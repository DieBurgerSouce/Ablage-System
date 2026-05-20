/**
 * Shipment Tracking Feature Module
 *
 * Sendungsverfolgung für 7 Paketdienste:
 * DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post
 */

// Types
export * from './types/shipment-types';

// API
export { shipmentService, ShipmentApiError, getTrackingUrl, getCarrierDisplayName } from './api/shipment-api';

// Hooks
export {
  shipmentQueryKeys,
  useShipments,
  useShipmentSummary,
  useCarrierStatistics,
  useShipment,
  useCarriers,
  useCreateShipment,
  useUpdateShipment,
  useDeleteShipment,
  useRefreshTracking,
  useRefreshAllShipments,
  useDetectCarrier,
  useShipmentPage,
  useShipmentMutations,
  usePrefetchShipments,
  usePrefetchShipment,
  useInvalidateShipmentQueries,
} from './hooks/use-shipment-queries';

// Components
export { CarrierIcon, CarrierBadge, getCarrierOptions } from './components/CarrierIcon';
export { ShipmentTrackingCard, ShipmentSummaryCard } from './components/ShipmentTrackingCard';
export { ShipmentList } from './components/ShipmentList';
export { ShipmentDetail } from './components/ShipmentDetail';
