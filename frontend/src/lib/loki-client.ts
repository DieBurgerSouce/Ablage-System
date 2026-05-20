/**
 * Loki Push Client für Frontend-Logging.
 *
 * Sendet strukturierte Logs an Grafana Loki für zentrales Monitoring.
 * Features:
 * - Batch-Sending (sammelt Logs, sendet alle 5s oder bei 10 Einträgen)
 * - Retry-Logik bei Netzwerkfehlern
 * - User-Kontext für bessere Korrelation
 * - Automatische Label-Generierung
 *
 * Konfiguration via Environment:
 *   VITE_LOKI_ENABLED=true
 *   VITE_LOKI_URL=http://localhost:3100
 */

// Konfiguration
const LOKI_URL = import.meta.env.VITE_LOKI_URL || 'http://localhost:3100';
const LOKI_ENABLED = import.meta.env.VITE_LOKI_ENABLED === 'true';
const BATCH_SIZE = 10;
const BATCH_INTERVAL_MS = 5000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

// Warne wenn keine LOKI_URL konfiguriert ist
if (!import.meta.env.VITE_LOKI_URL && LOKI_ENABLED) {
  console.warn('[Loki] Keine LOKI_URL konfiguriert - verwende Fallback: http://localhost:3100');
}

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
}

interface UserContext {
  id: string;
  // SECURITY: E-Mail NICHT loggen - PII/DSGVO-Verletzung!
  // email ist hier absichtlich nicht enthalten
}

interface TenantContext {
  companyId?: string;
  companyName?: string;
}

interface LokiStream {
  stream: Record<string, string>;
  values: [string, string][];
}

interface LokiPushRequest {
  streams: LokiStream[];
}

/**
 * Loki Push Client Singleton.
 */
class LokiClient {
  private buffer: LogEntry[] = [];
  private user: UserContext | null = null;
  private tenant: TenantContext | null = null;
  private labels: Record<string, string> = {};
  private flushIntervalId: ReturnType<typeof setInterval> | null = null;
  private isEnabled: boolean;
  private isFlushing = false; // Prevent race conditions

  constructor() {
    this.isEnabled = LOKI_ENABLED;

    // Automatischer Flush beim Seitenunload mit sendBeacon
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        this.flushSync();
      });

      // Periodischer Flush starten
      this.startFlushInterval();
    }
  }

  /**
   * Synchroner Flush mit sendBeacon für beforeunload.
   * sendBeacon garantiert Zustellung auch beim Seitenwechsel.
   */
  private flushSync(): void {
    if (!this.isEnabled || this.buffer.length === 0) return;

    const entries = [...this.buffer];
    this.buffer = [];

    const payload = this.buildPayload(entries);

    // sendBeacon ist synchron und garantiert Zustellung
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], {
        type: 'application/json',
      });
      navigator.sendBeacon(`${LOKI_URL}/loki/api/v1/push`, blob);
    }
  }

  /**
   * Aktiviert/Deaktiviert den Client zur Laufzeit.
   */
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
    if (enabled && !this.flushIntervalId) {
      this.startFlushInterval();
    } else if (!enabled && this.flushIntervalId) {
      clearInterval(this.flushIntervalId);
      this.flushIntervalId = null;
    }
  }

  /**
   * Setzt den User-Kontext für alle folgenden Logs.
   * WICHTIG: Keine PII (E-Mail etc.) übergeben!
   */
  setUser(user: UserContext | null): void {
    this.user = user;
  }

  /**
   * Setzt den Tenant-Kontext für Multi-Mandanten-Fähigkeit.
   * Wichtig für RLS und Log-Filterung nach Mandant.
   */
  setTenant(tenant: TenantContext | null): void {
    this.tenant = tenant;
  }

  /**
   * Setzt zusätzliche Labels für alle folgenden Logs.
   */
  setLabels(labels: Record<string, string>): void {
    this.labels = { ...this.labels, ...labels };
  }

  /**
   * Bereinigt den Client (stoppt Timer, flusht Buffer).
   * Wichtig für Hot-Reloading und Tests.
   */
  destroy(): void {
    if (this.flushIntervalId) {
      clearInterval(this.flushIntervalId);
      this.flushIntervalId = null;
    }
    // Sync-Flush für verbleibende Logs
    this.flushSync();
  }

  /**
   * Fuegt einen Log-Eintrag zum Buffer hinzu.
   */
  push(level: LogLevel, message: string, context?: Record<string, unknown>): void {
    if (!this.isEnabled) return;

    const entry: LogEntry = {
      timestamp: Date.now().toString() + '000000', // Nanosekunden-Format für Loki
      level,
      message,
      context: this.enrichContext(context),
    };

    this.buffer.push(entry);

    // Sofort flushen bei Errors oder wenn Buffer voll
    if (level === 'error' || this.buffer.length >= BATCH_SIZE) {
      this.flush();
    }
  }

  /**
   * Sendet alle gepufferten Logs an Loki.
   * Thread-safe durch isFlushing-Flag.
   */
  async flush(): Promise<void> {
    // Prevent race conditions from concurrent flush calls
    if (!this.isEnabled || this.buffer.length === 0 || this.isFlushing) return;

    this.isFlushing = true;
    const entries = [...this.buffer];
    this.buffer = [];

    try {
      await this.sendToLoki(entries);
    } catch {
      // Bei Fehler: Einträge zurück in Buffer (am Anfang)
      // Aber NUR wenn Buffer nicht zwischenzeitlich gefüllt wurde
      this.buffer = [...entries, ...this.buffer];

      // Begrenze Buffer-Größe um Memory Leaks zu vermeiden
      if (this.buffer.length > 100) {
        this.buffer = this.buffer.slice(-100);
      }
    } finally {
      this.isFlushing = false;
    }
  }

  /**
   * Erstellt einen neuen Client mit zusätzlichen Labels.
   * Nützlich für Component-spezifisches Logging.
   */
  withLabels(labels: Record<string, string>): LokiClientWithLabels {
    return new LokiClientWithLabels(this, labels);
  }

  private enrichContext(context?: Record<string, unknown>): Record<string, unknown> {
    const enriched: Record<string, unknown> = {
      ...context,
      url: typeof window !== 'undefined' ? window.location.href : undefined,
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    };

    // User-Kontext (nur ID, keine PII!)
    if (this.user) {
      enriched.userId = this.user.id;
      // SECURITY: E-Mail wird NICHT geloggt (PII/DSGVO)
    }

    // Tenant-Kontext für Multi-Mandanten-RLS
    if (this.tenant) {
      if (this.tenant.companyId) {
        enriched.companyId = this.tenant.companyId;
      }
      if (this.tenant.companyName) {
        enriched.companyName = this.tenant.companyName;
      }
    }

    return enriched;
  }

  private async sendToLoki(entries: LogEntry[], retryCount = 0): Promise<void> {
    const payload = this.buildPayload(entries);

    try {
      const response = await fetch(`${LOKI_URL}/loki/api/v1/push`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        // Keine Credentials - Loki ist intern
        keepalive: true, // Wichtig für beforeunload
      });

      if (!response.ok) {
        throw new Error(`Loki push failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      if (retryCount < MAX_RETRIES) {
        await this.sleep(RETRY_DELAY_MS * (retryCount + 1));
        return this.sendToLoki(entries, retryCount + 1);
      }
      throw error;
    }
  }

  private startFlushInterval(): void {
    if (this.flushIntervalId) return;

    this.flushIntervalId = setInterval(() => {
      this.flush();
    }, BATCH_INTERVAL_MS);
  }

  /**
   * Baut das Loki-Payload für sendBeacon.
   * Wiederverwendbar für sync und async Sends.
   */
  private buildPayload(entries: LogEntry[]): LokiPushRequest {
    const byLevel = new Map<LogLevel, LogEntry[]>();

    for (const entry of entries) {
      const existing = byLevel.get(entry.level) || [];
      existing.push(entry);
      byLevel.set(entry.level, existing);
    }

    const streams: LokiStream[] = [];

    for (const [level, levelEntries] of byLevel) {
      const stream: LokiStream = {
        stream: {
          app: 'ablage-frontend',
          level,
          env: import.meta.env.MODE || 'development',
          ...this.labels,
        },
        values: levelEntries.map((entry) => [
          entry.timestamp,
          JSON.stringify({
            message: entry.message,
            ...entry.context,
          }),
        ]),
      };
      streams.push(stream);
    }

    return { streams };
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/**
 * Helper-Klasse für Component-spezifisches Logging.
 */
class LokiClientWithLabels {
  constructor(
    private client: LokiClient,
    private extraLabels: Record<string, string>
  ) {}

  push(level: LogLevel, message: string, context?: Record<string, unknown>): void {
    this.client.push(level, message, {
      ...context,
      ...this.extraLabels,
    });
  }

  debug(message: string, context?: Record<string, unknown>): void {
    this.push('debug', message, context);
  }

  info(message: string, context?: Record<string, unknown>): void {
    this.push('info', message, context);
  }

  warn(message: string, context?: Record<string, unknown>): void {
    this.push('warn', message, context);
  }

  error(message: string, context?: Record<string, unknown>): void {
    this.push('error', message, context);
  }
}

// Singleton-Export
export const lokiClient = new LokiClient();

// Type-Export für externe Verwendung
export type { LogLevel, LogEntry, UserContext, TenantContext };
