/**
 * Strukturiertes Logging-Service fuer Frontend.
 *
 * In Production werden nur warn und error ausgegeben.
 * In Development sind alle Log-Level aktiv.
 *
 * Verwendung:
 *   import { logger } from '@/lib/logger';
 *   logger.debug('Debug message', { data: 123 });
 *   logger.info('Info message');
 *   logger.warn('Warning message');
 *   logger.error('Error message', error);
 */

const isDev = import.meta.env.DEV;

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  [key: string]: unknown;
}

/**
 * Formatiert Log-Argumente fuer bessere Lesbarkeit.
 */
function formatLogArgs(
  level: LogLevel,
  message: string,
  ...args: unknown[]
): unknown[] {
  const timestamp = new Date().toISOString();
  const prefix = `[${timestamp}] [${level.toUpperCase()}]`;

  // Filtere Error-Objekte fuer bessere Darstellung
  const formattedArgs = args.map((arg) => {
    if (arg instanceof Error) {
      return {
        name: arg.name,
        message: arg.message,
        stack: arg.stack,
      };
    }
    return arg;
  });

  return [prefix, message, ...formattedArgs];
}

/**
 * Logger mit Production-Safe Logging.
 *
 * - debug/info: Nur in Development
 * - warn/error: Immer (fuer Monitoring und Debugging)
 */
export const logger = {
  /**
   * Debug-Meldungen - nur in Development.
   */
  debug(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.debug(...formatLogArgs('debug', message, ...args));
    }
  },

  /**
   * Info-Meldungen - nur in Development.
   */
  info(message: string, ...args: unknown[]): void {
    if (isDev) {
      console.info(...formatLogArgs('info', message, ...args));
    }
  },

  /**
   * Warnungen - immer ausgeben.
   */
  warn(message: string, ...args: unknown[]): void {
    console.warn(...formatLogArgs('warn', message, ...args));
  },

  /**
   * Fehler - immer ausgeben.
   */
  error(message: string, ...args: unknown[]): void {
    console.error(...formatLogArgs('error', message, ...args));
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
      debug: (message: string, ...args: unknown[]) =>
        logger.debug(message, context, ...args),
      info: (message: string, ...args: unknown[]) =>
        logger.info(message, context, ...args),
      warn: (message: string, ...args: unknown[]) =>
        logger.warn(message, context, ...args),
      error: (message: string, ...args: unknown[]) =>
        logger.error(message, context, ...args),
    };
  },
};

// Default export fuer einfachere Imports
export default logger;
