/**
 * Validation API Exports
 */

// Legacy Training API (für Rückwärtskompatibilität)
export * from './validation-api';
export { default as validationApi } from './validation-api';

// Neue Queue-basierte API
export * from './validation-queue-api';
export { default as validationQueueApi } from './validation-queue-api';
