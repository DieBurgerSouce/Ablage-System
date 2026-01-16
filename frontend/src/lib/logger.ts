/**
 * Strukturiertes Logging-Service fuer Frontend mit Grafana Loki Integration.
 *
 * Features:
 * - Automatisches Senden an Loki (wenn VITE_LOKI_ENABLED=true)
 * - User-Kontext fuer bessere Log-Korrelation
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
 *   // WICHTIG: Keine PII wie E-Mail uebergeben!
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

interface LogContext {
  [key: string]: unknown;
}

/**
 * Formatiert Error-Objekte fuer bessere Lesbarkeit.
 */
function formatError(error: unknown): Record<string, unknown> {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack,
    };
  }
  return { value: error };
}

/**
 * Formatiert Log-Argumente fuer Console-Output.
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
 * Konvertiert Log-Args zu Context-Objekt fuer Loki.
 */
function argsToContext(...args: unknown[]): Record<string, unknown> | undefined {
  if (args.length === 0) return undefined;

  const context: Record<string, unknown> = {};

  args.forEach((arg, index) => {
    if (arg instanceof Error) {
      context.error = formatError(arg);
    } else if (typeof arg === 'object' && arg !== null) {
      Object.assign(context, arg);
    } else {
      context[`arg${index}`] = arg;
    }
  });

  return Object.keys(context).length > 0 ? context : undefined;
}

/**
 * Logger mit Loki-Integration und Component-Labels.
 */
class LoggerWithLabels {
  constructor(private labels: Record<string, string>) {}

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
 * - User-Kontext: Nach Login setzen fuer bessere Korrelation
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
   * Gruppiertes Logging fuer komplexe Operationen.
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
   * Nuetzlich fuer komplexe Objekte.
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
   * Erstellt einen Logger mit zusaetzlichen Labels.
   * Nuetzlich fuer Component-spezifisches Logging.
   *
   * @example
   * const log = logger.withLabels({ component: 'UploadWizard' });
   * log.error('Upload fehlgeschlagen', error);
   */
  withLabels(labels: Record<string, string>): LoggerWithLabels {
    return new LoggerWithLabels(labels);
  },

  /**
   * Setzt den User-Kontext fuer alle folgenden Logs.
   * Sollte nach erfolgreichem Login aufgerufen werden.
   *
   * WICHTIG: Keine PII wie E-Mail uebergeben!
   *
   * @example
   * logger.setUser({ id: user.id });
   */
  setUser(user: UserContext | null): void {
    lokiClient.setUser(user);
  },

  /**
   * Setzt den Tenant-Kontext fuer Multi-Mandanten-Faehigkeit.
   * Wichtig fuer RLS und Log-Filterung nach Mandant.
   *
   * @example
   * logger.setTenant({ companyId: company.id, companyName: company.name });
   */
  setTenant(tenant: TenantContext | null): void {
    lokiClient.setTenant(tenant);
  },

  /**
   * Sendet alle gepufferten Logs sofort an Loki.
   * Nuetzlich vor Navigation oder Logout.
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

// Default export fuer einfachere Imports
export default logger;
