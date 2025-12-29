/**
 * Streckengeschäft Components Index
 * 
 * Central export for all drop shipment classification components.
 */

// Main Dashboard
export { StreckengeschaeftDashboard } from './StreckengeschaeftDashboard';
export { default as StreckengeschaeftDashboardDefault } from './StreckengeschaeftDashboard';

// Detail View
export { ClassificationDetail } from './ClassificationDetail';
export { default as ClassificationDetailDefault } from './ClassificationDetail';

// Dialogs
export { ValidationDialog } from './ValidationDialog';
export { default as ValidationDialogDefault } from './ValidationDialog';

// ZM Summary
export { ZmSummaryCard } from './ZmSummaryCard';
export { default as ZmSummaryCardDefault } from './ZmSummaryCard';

// Re-export types for convenience
export type {
  DropShipmentClassification,
  DropShipmentPosition,
  TransactionParty,
  ProofDocument,
  VatIdRecord,
  ClassificationIndicator,
  ConflictInfo,
  ClassificationStatistics,
  ZmSummary,
  TransactionType,
  CompanyRole,
  MovingDelivery,
  ConfidenceLevel,
  VatCategory,
  ProofType,
  PartyRole,
} from '@/types/streckengeschaeft';
