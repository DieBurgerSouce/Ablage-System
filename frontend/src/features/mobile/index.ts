/**
 * Mobile Feature - Exports
 *
 * PWA-optimierte Features fuer mobile Geraete:
 * - Kamera-Scan fuer Dokumentenerfassung
 * - Offline-Unterstuetzung
 * - Touch-optimierte Gesten
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

// Components
export { CameraScan, default as CameraScanComponent } from './components/CameraScan';

// Hooks
export {
  useCameraScan,
  type CapturedDocument,
} from './hooks/use-camera-scan';

export {
  useOfflineStatus,
  type ConnectionType,
  type NetworkInfo,
  type StorageInfo,
  type ServiceWorkerInfo,
} from './hooks/use-offline-status';
