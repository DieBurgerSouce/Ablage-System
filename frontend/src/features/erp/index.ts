/**
 * ERP Feature Module Export
 *
 * Exportiert alle ERP-Integration Komponenten, Hooks und Typen.
 */

// Components
export {
  ERPConnectionsPage,
  ERPConnectionDialog,
  ERPStatsCards,
  SyncDashboard,
  ConflictResolver,
} from './components';

// Hooks
export {
  useERPConnections,
  useERPConnection,
  useCreateConnection,
  useUpdateConnection,
  useDeleteConnection,
  useTestConnection,
  useTriggerSync,
  useSyncHistory,
  useERPConflicts,
  useResolveConflict,
  useERPStats,
} from './hooks/useERP';

// API
export {
  listConnections,
  getConnection,
  createConnection,
  updateConnection,
  deleteConnection,
  testConnection,
  triggerSync,
  getSyncHistory,
  listConflicts,
  resolveConflict,
  getERPStats,
  erpKeys,
} from './api';

// Types
export type {
  ERPType,
  ERPSyncDirection,
  ERPConnectionStatus,
  ERPSyncStatus,
  ERPConflictStatus,
  ERPEntityType,
  ERPConnection,
  ERPConnectionCreate,
  ERPConnectionUpdate,
  ERPConnectionTestResult,
  ERPSyncHistory,
  ERPConflict,
  ERPConflictResolve,
  ERPStats,
  SyncTriggerResponse,
} from './types';
