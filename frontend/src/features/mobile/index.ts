/**
 * Mobile Feature - Exports
 *
 * PWA-optimierte Features für mobile Geräte:
 * - Kamera-Scan für Dokumentenerfassung
 * - OCR-Ergebnis und Zuordnung nach Scan
 * - Offline-Unterstützung
 * - Touch-optimierte Gesten
 *
 * Phase 3.1 + 3.2 der Feature-Roadmap (Januar-Februar 2026)
 */

// Components
export { CameraScan, default as CameraScanComponent } from './components/CameraScan';
export { ScanResultPanel } from './components/ScanResultPanel';
export { QuickAssignSheet } from './components/QuickAssignSheet';

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

export {
  useScanFlow,
  type ScanFlowPhase,
  type ScanFlowState,
  type OCRResultSummary,
  type EntitySuggestion,
} from './hooks/use-scan-flow';
