/**
 * Streckengeschäft (Drop Shipment) Feature Module
 * 
 * Automatische Erkennung und Klassifikation von:
 * - Streckengeschäften (Drop Shipments)
 * - Innergemeinschaftlichen Dreiecksgeschäften (§25b UStG)
 * - Reihengeschäften (Chain Transactions)
 * 
 * @module features/drop-shipment
 */

// Types
export * from './types';

// API
export { dropShipmentApi } from './api';

// Hooks
export {
  // Query Keys
  dropShipmentKeys,
  // Queries
  useDropShipmentList,
  useDropShipmentDetail,
  useDropShipmentStats,
  useZmPending,
  useRelatedDocuments,
  // Mutations
  useClassifyDocument,
  useConfirmClassification,
  useOverrideClassification,
  useLinkProofDocument,
  useUnlinkProofDocument,
  useMarkZmReported,
  useDatevExport,
  useBulkAction,
  useDeleteClassification,
  useValidateDocumentFlow,
} from './hooks';
