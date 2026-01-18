/**
 * Offline Module Exports
 *
 * Central export point for all offline functionality.
 */

// Sync Service
export { syncService, type SyncProgress, type SyncResult, type SyncEventDetail } from './sync-service';

// Offline API Wrapper
export {
  offlineRequest,
  offlineGet,
  offlinePost,
  offlinePut,
  offlinePatch,
  offlineDelete,
  isOnline,
  getOfflineDocuments,
  getDocument,
  cacheDocumentsForOffline,
  type OfflineApiOptions,
  type OfflineApiResult,
} from './offline-api-wrapper';

// Hooks
export { useOfflineSync } from './use-offline-sync';
export { useOfflineApproval } from './use-offline-approval';

// Components are exported from their own files
