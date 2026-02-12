/**
 * WebSocket Configuration
 *
 * Zentrale Konfiguration für WebSocket-Verbindungen.
 * Unterstützt Environment-Variablen für flexible Deployment-Szenarien.
 */

import { logger } from '@/lib/logger';

/**
 * Backend API Port Konfiguration
 *
 * In Development: Verwendet VITE_API_PORT oder Fallback auf '8000'
 * In Production: Verwendet den aktuellen window.location.port
 */
export const API_PORT = import.meta.env.DEV
  ? (import.meta.env.VITE_API_PORT as string) || '8000'
  : window.location.port;

/**
 * WebSocket Protocol basierend auf aktuellem HTTP-Protocol
 */
export const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

/**
 * Hostname für WebSocket-Verbindungen
 */
export const WS_HOST = window.location.hostname;

/**
 * Erstellt die vollständige WebSocket-URL für einen Pfad
 *
 * @param path - Der WebSocket-Pfad (z.B. '/api/v1/admin/jobs/ws')
 * @returns Vollständige WebSocket-URL
 */
export function buildWebSocketUrl(path: string): string {
  return `${WS_PROTOCOL}//${WS_HOST}:${API_PORT}${path}`;
}

/**
 * Logging-Konfiguration für WebSocket-Debugging
 *
 * Im Development-Modus werden Debug-Meldungen ausgegeben,
 * in Production werden sie unterdrückt.
 */
export const WS_DEBUG_ENABLED = import.meta.env.DEV;

/**
 * Logger-Funktionen für WebSocket-Debugging
 * Nur aktiv wenn WS_DEBUG_ENABLED true ist
 */
export const wsLogger = {
  debug: (...args: unknown[]) => {
    if (WS_DEBUG_ENABLED) {
      logger.debug('[JobWebSocket]', ...args);
    }
  },
  info: (...args: unknown[]) => {
    if (WS_DEBUG_ENABLED) {
      logger.info('[JobWebSocket]', ...args);
    }
  },
  warn: (...args: unknown[]) => {
    // Warnings sind immer aktiv
    logger.warn('[JobWebSocket]', ...args);
  },
  error: (...args: unknown[]) => {
    // Errors sind immer aktiv
    logger.error('[JobWebSocket]', ...args);
  },
};
