/**
 * Strukturiertes Logging-Service für Frontend mit Grafana Loki Integration.
 *
 * Features:
 * - Automatisches Senden an Loki (wenn VITE_LOKI_ENABLED=true)
 * - User-Kontext für bessere Log-Korrelation
 * - Component-spezifische Labels via withLabels()
 * - Production-Safe: debug/info nur in Development
 *
 * Verwendung:
 *   import { logger } from '@/lib/logger';
 *
 *   // Basis-Logging
 *   logger.debug('Debug message', { data: 123 });
 *   logger.info('Info message');
 *   logger.warn('Warning message');
 *   logger.error('Error message', error);
 *
 *   // Mit User-Kontext (nach Login setzen)
 *   // WICHTIG: Keine PII wie E-Mail übergeben!
 *   logger.setUser({ id: 'user123' });
 *
 *   // Mit Component-Labels
 *   const componentLogger = logger.withLabels({ component: 'UploadWizard' });
 *   componentLogger.error('Upload fehlgeschlagen', error);
 */

import { lokiClient, type UserContext, type TenantContext } from './loki-client';

/* eslint-disable no-console */

const isDev = import.meta.env.DEV;

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/**
 * Bounded primitive type for log context values.
 * Only allows primitive types to prevent oversized nested objects in logs.
 */
type LogContextValue = string | number | boolean | null | undefined;

/**
 * Bounded error type for log context.
 * Only allows known error properties to prevent DoS via oversized error objects.
 * P1 Fix (Iteration 12): Previously allowed Record<string, unknown> which could contain 10MB+ objects.
 * P1 Fix (Iteration 13): cause ist jetzt rekursiv BoundedError statt string (max 3 Ebenen).
 */
interface BoundedError {
  message: string;
  name?: string;
  stack?: string;
  code?: string | number;
  cause?: BoundedError;  // P1 Fix: Rekursiv für nested errors, bounded via depth limit
}

/**
 * Log context for structured logging.
 *
 * SECURITY NOTE: This interface uses bounded types to:
 * 1. Prevent prototype pollution via key validation in argsToContext
 * 2. Prevent oversized log payloads via primitive-only values
 * 3. Allow explicit error objects only via the 'error' key with bounded type
 *
 * Known safe keys are explicitly typed. Additional keys must be primitives only.
 */
interface LogContext {
  // Known safe context keys (explicitly typed)
  component?: string;
  action?: string;
  documentId?: string;
  userId?: string;
  error?: BoundedError; // P1 Fix: Now bounded to known error properties
  // Additional metadata - primitives only (no nested objects)
  // This prevents 10MB+ payloads from nested Record<string, unknown>
  [key: string]: LogContextValue | BoundedError;
}

/**
 * Formatiert Error-Objekte für bessere Lesbarkeit.
 * Returns a bounded error object to prevent oversized payloads.
 *
 * P1 Fix (Iteration 13): Rekursive cause-Extraktion mit max 3 Ebenen Tiefe.
 * Verhindert Verlust von nested Error.cause Informationen.
 *
 * @param error - Der zu formatierende Fehler
 * @param depth - Aktuelle Rekursionstiefe (intern, max 3)
 */
function formatError(error: unknown, depth = 0): BoundedError {
  // Depth limit verhindert endlose Rekursion bei zirkulaeren cause-Referenzen
  const MAX_DEPTH = 3;

  if (error instanceof Error) {
    const errorWithCause = error as Error & { cause?: unknown; code?: string | number };
    return {
      name: error.name,
      message: error.message,
      stack: error.stack?.slice(0, 1000),  // Truncate stack to 1KB
      code: errorWithCause.code,
      // P1 Fix: Rekursive cause-Extraktion (max 3 Ebenen)
      cause: (() => {
        const c = errorWithCause.cause;
        if (c instanceof Error && depth < MAX_DEPTH) {
          return formatError(c, depth + 1);  // Rekursiv mit depth+1
        }
        if (typeof c === 'string') {
          return { message: c.slice(0, 500) };  // String cause als BoundedError
        }
        return undefined;
      })(),
    };
  }
  // For non-Error values, stringify but truncate to prevent DoS
  const stringified = typeof error === 'string' ? error : String(error);
  return { message: stringified.slice(0, 1000) }; // Max 1KB for unknown errors
}

/**
 * Formatiert Log-Argumente für Console-Output.
 */
function formatLogArgs(level: LogLevel, message: string, ...args: unknown[]): unknown[] {
  const timestamp = new Date().toISOString();
  const prefix = `[${timestamp}] [${level.toUpperCase()}]`;

  const formattedArgs = args.map((arg) => {
    if (arg instanceof Error) {
      return formatError(arg);
    }
    return arg;
  });

  return [prefix, message, ...formattedArgs];
}

/**
 * Konvertiert Log-Args zu Context-Objekt für Loki.
 *
 * P1 Fix (Iteration 13): DoS Protection für Object.assign.
 * Verhindert Spreaden von riesigen Objekten wie `window` oder `process`.
 * - Max 10 Keys pro Objekt
 * - Nur primitive Values (string, number, boolean)
 * - Arrays werden als JSON-String begrenzt
 *
 * P1 Fix (Iteration 14): Key-Whitelist + PII-Blocklist.
 * - Nur alphanumerische Keys + underscore erlaubt (max 50 chars)
 * - Blocklist für Prototype pollution + sensitive Keys
 * - Case-insensitive Blocklist-Check für PII-Keys
 */
function argsToContext(...args: unknown[]): Record<string, unknown> | undefined {
  if (args.length === 0) return undefined;

  const context: Record<string, unknown> = {};
  const MAX_KEYS = 10;
  const MAX_STRING_LENGTH = 500;

  // P1 Fix (Iteration 14): Sicherheits-Pattern und Blocklist
  // P1 Fix (Iteration 15): Erweitert um Domain-spezifische PII (CLAUDE.md Regel #8)
  const SAFE_KEY_PATTERN = /^[a-z_][a-z0-9_]{0,49}$/i;  // Alphanumeric + _, max 50 chars
  const BLOCKLIST = new Set([
    // Prototype pollution
    '__proto__', 'constructor', 'prototype', 'hasOwnProperty', 'toString', 'valueOf',
    // Path disclosure
    '__dirname', '__filename',
    // PII/Secrets (case-insensitive check below)
    'secret', 'password', 'token', 'key', 'apikey', 'api_key', 'auth', 'credential',
    'iban', 'ssn', 'creditcard', 'credit_card', 'cardnumber', 'card_number',
    // Domain-specific PII (CLAUDE.md Regel #8: NEVER log customer numbers, IBANs, VAT-IDs)
    'email', 'phone', 'customernumber', 'customer_number',
    'suppliernumber', 'supplier_number', 'vatid', 'vat_id',
    'bic', 'swift', 'accountnumber', 'account_number',
    'taxid', 'tax_id', 'tin',
  ]);

  args.forEach((arg, index) => {
    if (arg instanceof Error) {
      context.error = formatError(arg);
    } else if (Array.isArray(arg)) {
      // Arrays: stringify und truncieren
      const arrStr = JSON.stringify(arg);
      context[`arg${index}`] = arrStr.slice(0, MAX_STRING_LENGTH);
    } else if (typeof arg === 'object' && arg !== null) {
      // P1 Fix: Nur primitive properties, max 10 keys + Key validation
      const safeObj = arg as Record<string, unknown>;
      const safeKeys = Object.keys(safeObj).slice(0, MAX_KEYS);
      for (const key of safeKeys) {
        // P1 Fix (Iteration 14): Key-Whitelist + PII-Blocklist
        const keyLower = key.toLowerCase();
        if (BLOCKLIST.has(keyLower) || !SAFE_KEY_PATTERN.test(key)) {
          continue;
        }
        const val = safeObj[key];
        if (typeof val === 'string') {
          context[key] = val.slice(0, MAX_STRING_LENGTH);
        } else if (typeof val === 'number' || typeof val === 'boolean') {
          context[key] = val;
        }
        // Nested objects/functions werden ignoriert (DoS prevention)
      }
    } else if (arg !== null && arg !== undefined) {
      // Primitives: stringify und truncieren
      context[`arg${index}`] = String(arg).slice(0, MAX_STRING_LENGTH);
    }
  });

  return Object.keys(context).length > 0 ? context : undefined;
}

/**
 * Logger mit Loki-Integration und Component-Labels.
 */
class LoggerWithLabels {
  private labels: Record<string, string>;

  constructor(labels: Record<string, string>) {
    this.labels = labels;
  }

  debug(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.debug(...formatLogArgs('debug', message, ...args));
    }
    // Debug nur in Development an Loki senden (optional)
    if (isDev) {
      lokiClient.push('debug', message, { ...argsToContext(...args), ...this.labels });
    }
  }

  info(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.info(...formatLogArgs('info', message, ...args));
    }
    // Info in Production an Loki senden
    lokiClient.push('info', message, { ...argsToContext(...args), ...this.labels });
  }

  warn(message: string, ...args: unknown[]): void {
    console.warn(...formatLogArgs('warn', message, ...args));
    lokiClient.push('warn', message, { ...argsToContext(...args), ...this.labels });
  }

  error(message: string, ...args: unknown[]): void {
    console.error(...formatLogArgs('error', message, ...args));
    lokiClient.push('error', message, { ...argsToContext(...args), ...this.labels });
  }
}

/**
 * Haupt-Logger mit Production-Safe Logging und Loki-Integration.
 *
 * - debug/info: Nur in Development auf Console
 * - warn/error: Immer auf Console + Loki
 * - User-Kontext: Nach Login setzen für bessere Korrelation
 */
export const logger = {
  /**
   * Debug-Meldungen - nur in Development auf Console.
   * In Development auch an Loki gesendet.
   */
  debug(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.debug(...formatLogArgs('debug', message, ...args));
      lokiClient.push('debug', message, argsToContext(...args));
    }
  },

  /**
   * Info-Meldungen - nur in Development auf Console.
   * Immer an Loki gesendet.
   */
  info(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.info(...formatLogArgs('info', message, ...args));
    }
    lokiClient.push('info', message, argsToContext(...args));
  },

  /**
   * Warnungen - immer auf Console und Loki.
   */
  warn(message: string, ...args: unknown[]): void {
    console.warn(...formatLogArgs('warn', message, ...args));
    lokiClient.push('warn', message, argsToContext(...args));
  },

  /**
   * Fehler - immer auf Console und Loki.
   */
  error(message: string, ...args: unknown[]): void {
    console.error(...formatLogArgs('error', message, ...args));
    lokiClient.push('error', message, argsToContext(...args));
  },

  /**
   * Gruppiertes Logging für komplexe Operationen.
   * Nur in Development aktiv.
   */
  group(label: string, fn: () => void): void {
    if (isDev) {
      console.group(label);
      try {
        fn();
      } finally {
        console.groupEnd();
      }
    }
  },

  /**
   * Performance-Messung.
   * Nur in Development aktiv.
   */
  time(label: string): void {
    if (isDev) {
      console.time(label);
    }
  },

  timeEnd(label: string): void {
    if (isDev) {
      console.timeEnd(label);
    }
  },

  /**
   * Strukturiertes Logging mit Context.
   * Nützlich für komplexe Objekte.
   */
  withContext(context: LogContext) {
    return {
      debug: (message: string, ...args: unknown[]) => logger.debug(message, context, ...args),
      info: (message: string, ...args: unknown[]) => logger.info(message, context, ...args),
      warn: (message: string, ...args: unknown[]) => logger.warn(message, context, ...args),
      error: (message: string, ...args: unknown[]) => logger.error(message, context, ...args),
    };
  },

  /**
   * Erstellt einen Logger mit zusätzlichen Labels.
   * Nützlich für Component-spezifisches Logging.
   *
   * @example
   * const log = logger.withLabels({ component: 'UploadWizard' });
   * log.error('Upload fehlgeschlagen', error);
   */
  withLabels(labels: Record<string, string>): LoggerWithLabels {
    return new LoggerWithLabels(labels);
  },

  /**
   * Setzt den User-Kontext für alle folgenden Logs.
   * Sollte nach erfolgreichem Login aufgerufen werden.
   *
   * WICHTIG: Keine PII wie E-Mail übergeben!
   *
   * @example
   * logger.setUser({ id: user.id });
   */
  setUser(user: UserContext | null): void {
    lokiClient.setUser(user);
  },

  /**
   * Setzt den Tenant-Kontext für Multi-Mandanten-Fähigkeit.
   * Wichtig für RLS und Log-Filterung nach Mandant.
   *
   * @example
   * logger.setTenant({ companyId: company.id, companyName: company.name });
   */
  setTenant(tenant: TenantContext | null): void {
    lokiClient.setTenant(tenant);
  },

  /**
   * Sendet alle gepufferten Logs sofort an Loki.
   * Nützlich vor Navigation oder Logout.
   */
  flush(): Promise<void> {
    return lokiClient.flush();
  },

  /**
   * Aktiviert/Deaktiviert Loki-Integration zur Laufzeit.
   */
  setLokiEnabled(enabled: boolean): void {
    lokiClient.setEnabled(enabled);
  },
};

// Default export für einfachere Imports
export default logger;
