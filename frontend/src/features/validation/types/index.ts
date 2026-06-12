/**
 * Validation Types Index
 *
 * Re-exports alle Typen für das Validierungs-Feature.
 */

// Legacy Training Types (für Rückwärtskompatibilität)
export * from '../types';

// Neue Queue-basierte Typen
export * from './validation-queue.types';

// Explizit: neue Queue-Typen/-Helper sind kanonisch (Legacy nur Rueckwaertskompatibilitaet)
export type { ValidationQueueItem } from './validation-queue.types';
export { getConfidenceColor, getConfidenceBgColor } from './validation-queue.types';
