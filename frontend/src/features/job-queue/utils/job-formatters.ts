/**
 * Job Formatters
 *
 * Utility-Funktionen für die Formatierung von Job-Daten.
 * Zentralisiert für Wiederverwendbarkeit in allen Job-Queue Komponenten.
 */

// ==================== Time Formatting ====================

/**
 * Formatiert ein Datum als relative Zeit (z.B. "vor 5 Minuten")
 */
export function formatRelativeTime(dateInput: string | Date | undefined | null): string {
  if (!dateInput) return 'Nie';

  const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 0) {
    // Zukunft
    const futureSecs = Math.abs(diffSecs);
    const futureMins = Math.floor(futureSecs / 60);
    const futureHours = Math.floor(futureMins / 60);

    if (futureSecs < 60) return `in ${futureSecs}s`;
    if (futureMins < 60) return `in ${futureMins}min`;
    if (futureHours < 24) return `in ${futureHours}h`;
    return formatDateTime(date);
  }

  if (diffSecs < 60) return `vor ${diffSecs}s`;
  if (diffMins < 60) return `vor ${diffMins}min`;
  if (diffHours < 24) return `vor ${diffHours}h`;
  if (diffDays < 7) return `vor ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`;

  return formatDate(date);
}

/**
 * Formatiert ein Datum im deutschen Format (TT.MM.JJJJ)
 */
export function formatDate(dateInput: string | Date | undefined | null): string {
  if (!dateInput) return '-';

  const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/**
 * Formatiert Datum und Uhrzeit im deutschen Format
 */
export function formatDateTime(dateInput: string | Date | undefined | null): string {
  if (!dateInput) return '-';

  const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Formatiert nur die Uhrzeit im deutschen Format
 */
export function formatTime(dateInput: string | Date | undefined | null): string {
  if (!dateInput) return '-';

  const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  return date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// ==================== Duration Formatting ====================

/**
 * Formatiert eine Dauer in Millisekunden als lesbare Zeit
 */
export function formatDuration(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return '-';
  if (ms < 0) return '-';

  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}min`;
  if (ms < 86400000) return `${(ms / 3600000).toFixed(1)}h`;

  const days = Math.floor(ms / 86400000);
  const hours = Math.floor((ms % 86400000) / 3600000);
  return `${days}d ${hours}h`;
}

/**
 * Formatiert eine Dauer als detaillierte Zeit
 */
export function formatDurationDetailed(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return '-';
  if (ms < 0) return '-';

  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) {
    return `${days} Tag${days > 1 ? 'e' : ''}, ${hours % 24} Std, ${minutes % 60} Min`;
  }
  if (hours > 0) {
    return `${hours} Std, ${minutes % 60} Min, ${seconds % 60} Sek`;
  }
  if (minutes > 0) {
    return `${minutes} Min, ${seconds % 60} Sek`;
  }
  return `${seconds} Sek`;
}

/**
 * Berechnet die verbleibende Zeit basierend auf Fortschritt und Startzeit
 */
export function estimateRemainingTime(
  progress: number,
  startTime: string | Date | undefined | null
): string {
  if (!startTime || progress <= 0 || progress >= 100) return '-';

  const start = typeof startTime === 'string' ? new Date(startTime) : startTime;
  const elapsed = Date.now() - start.getTime();
  const totalEstimated = (elapsed / progress) * 100;
  const remaining = totalEstimated - elapsed;

  return formatDuration(remaining);
}

// ==================== Size Formatting ====================

/**
 * Formatiert Bytes als lesbare Größe
 */
export function formatBytes(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null) return '-';
  if (bytes < 0) return '-';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

// ==================== String Formatting ====================

/**
 * Kürzt einen Dateinamen auf eine maximale Länge
 */
export function truncateFilename(
  filename: string | undefined | null,
  maxLength: number = 30
): string {
  if (!filename) return '-';
  if (filename.length <= maxLength) return filename;

  const extension = filename.includes('.') ? filename.split('.').pop() || '' : '';
  const baseName = extension ? filename.slice(0, -(extension.length + 1)) : filename;

  const availableLength = maxLength - extension.length - 4; // "..." + "."

  if (availableLength <= 0) {
    return filename.slice(0, maxLength - 3) + '...';
  }

  return `${baseName.slice(0, availableLength)}...${extension ? `.${extension}` : ''}`;
}

/**
 * Kürzt einen Text mit Ellipse
 */
export function truncateText(
  text: string | undefined | null,
  maxLength: number = 50
): string {
  if (!text) return '-';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Formatiert eine Zahl als Prozent
 */
export function formatPercent(
  value: number | undefined | null,
  decimals: number = 1
): string {
  if (value === undefined || value === null) return '-';
  return `${value.toFixed(decimals)}%`;
}

/**
 * Formatiert eine große Zahl mit Tausender-Trennung
 */
export function formatNumber(value: number | undefined | null): string {
  if (value === undefined || value === null) return '-';
  return value.toLocaleString('de-DE');
}

/**
 * Formatiert eine Zahl kompakt (z.B. 1.5K, 2.3M)
 */
export function formatCompactNumber(value: number | undefined | null): string {
  if (value === undefined || value === null) return '-';

  if (value < 1000) return String(value);
  if (value < 1000000) return `${(value / 1000).toFixed(1)}K`;
  if (value < 1000000000) return `${(value / 1000000).toFixed(1)}M`;
  return `${(value / 1000000000).toFixed(1)}B`;
}

// ==================== ID Formatting ====================

/**
 * Kürzt eine UUID für die Anzeige
 */
export function formatJobId(id: string | undefined | null): string {
  if (!id) return '-';
  if (id.length <= 8) return id;
  return `${id.slice(0, 4)}...${id.slice(-4)}`;
}

/**
 * Formatiert eine Celery Task ID
 */
export function formatTaskId(taskId: string | undefined | null): string {
  if (!taskId) return '-';
  // Celery Task IDs sind oft sehr lang
  if (taskId.length <= 12) return taskId;
  return `${taskId.slice(0, 6)}...${taskId.slice(-6)}`;
}
