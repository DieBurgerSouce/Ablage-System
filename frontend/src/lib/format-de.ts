/**
 * Deutsche Formatierungsbibliothek - Erweiterte Utilities
 *
 * Ergaenzt format.ts um:
 * - Datumsformatierung (kurz, lang, relativ)
 * - Zeitformatierung (12h/24h)
 * - Dateigroessen
 * - Prozentangaben
 * - Aufbewahrungsfristen
 * - Steuerzeitraeume
 *
 * WICHTIG: Diese Datei ergaenzt format.ts, dupliziert es nicht.
 * Funktionen aus format.ts werden wiederverwendet wo moeglich.
 */

// Re-export existing functions from format.ts
export {
  formatCurrencyDE,
  formatCurrencyCompactDE,
  formatDateDE as formatDateDEShort, // Alias to avoid confusion
  formatDateTimeDE as formatDateTimeDEBasic,
  formatRelativeDateDE as formatRelativeDEBasic,
  formatNumberDE,
  formatPercentDE as formatPercentDEBasic,
  formatFileSizeDE as formatFileSizeDEBasic,
  formatIBANDE,
  formatVATID,
  truncateText,
  formatUserName,
} from './format';

// ==================== EXTENDED DATE FORMATTING ====================

/**
 * Formatiert ein Datum im deutschen Format mit erweiterten Optionen
 *
 * @example
 * formatDateDE(new Date(), 'short') // "07.02.2026"
 * formatDateDE(new Date(), 'long') // "7. Februar 2026"
 * formatDateDE(new Date(), 'relative') // "gerade eben"
 */
export function formatDateDE(
  date: Date | string | null | undefined,
  style: 'short' | 'long' | 'relative' = 'short'
): string {
  if (!date) {
    return '-';
  }

  const dateObj = typeof date === 'string' ? new Date(date) : date;

  if (isNaN(dateObj.getTime())) {
    return '-';
  }

  if (style === 'relative') {
    return formatRelativeDE(dateObj);
  }

  const options: Intl.DateTimeFormatOptions =
    style === 'short'
      ? { day: '2-digit', month: '2-digit', year: 'numeric' }
      : { day: 'numeric', month: 'long', year: 'numeric' };

  return new Intl.DateTimeFormat('de-DE', options).format(dateObj);
}

/**
 * Formatiert Datum und Uhrzeit im deutschen Format
 *
 * @example
 * formatDateTimeDE(new Date()) // "07.02.2026, 14:30 Uhr"
 * formatDateTimeDE(new Date(), true) // "07.02.2026, 14:30:45 Uhr"
 */
export function formatDateTimeDE(
  date: Date | string | null | undefined,
  showSeconds: boolean = false
): string {
  if (!date) {
    return '-';
  }

  const dateObj = typeof date === 'string' ? new Date(date) : date;

  if (isNaN(dateObj.getTime())) {
    return '-';
  }

  const dateStr = formatDateDE(dateObj, 'short');
  const timeStr = formatTimeDE(dateObj, showSeconds);

  return `${dateStr}, ${timeStr}`;
}

/**
 * Formatiert nur die Uhrzeit im deutschen Format
 *
 * @example
 * formatTimeDE(new Date()) // "14:30 Uhr"
 * formatTimeDE(new Date(), true) // "14:30:45 Uhr"
 */
export function formatTimeDE(
  date: Date | string | null | undefined,
  showSeconds: boolean = false
): string {
  if (!date) {
    return '-';
  }

  const dateObj = typeof date === 'string' ? new Date(date) : date;

  if (isNaN(dateObj.getTime())) {
    return '-';
  }

  const options: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    ...(showSeconds ? { second: '2-digit' } : {}),
  };

  const timeStr = new Intl.DateTimeFormat('de-DE', options).format(dateObj);
  return `${timeStr} Uhr`;
}

/**
 * Formatiert ein Datum relativ zum aktuellen Zeitpunkt (erweitert)
 *
 * @example
 * formatRelativeDE(new Date()) // "gerade eben"
 * formatRelativeDE(new Date(Date.now() - 60000)) // "vor 1 Minute"
 * formatRelativeDE(new Date(Date.now() - 300000)) // "vor 5 Minuten"
 * formatRelativeDE(new Date(Date.now() - 3600000)) // "vor 1 Stunde"
 * formatRelativeDE(new Date(Date.now() - 7200000)) // "vor 2 Stunden"
 * formatRelativeDE(new Date(Date.now() - 86400000)) // "gestern"
 * formatRelativeDE(new Date(Date.now() - 172800000)) // "vor 2 Tagen"
 * formatRelativeDE(new Date(Date.now() - 259200000)) // "vor 3 Tagen"
 */
export function formatRelativeDE(date: Date | string | null | undefined): string {
  if (!date) {
    return '-';
  }

  const dateObj = typeof date === 'string' ? new Date(date) : date;

  if (isNaN(dateObj.getTime())) {
    return '-';
  }

  const now = new Date();
  const diffMs = now.getTime() - dateObj.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  // Future dates
  if (diffMs < 0) {
    const absDiffSec = Math.abs(diffSec);
    const absDiffMin = Math.abs(diffMin);
    const absDiffHours = Math.abs(diffHours);
    const absDiffDays = Math.abs(diffDays);

    if (absDiffSec < 60) {
      return 'in wenigen Sekunden';
    }
    if (absDiffMin < 60) {
      return absDiffMin === 1 ? 'in 1 Minute' : `in ${absDiffMin} Minuten`;
    }
    if (absDiffHours < 24) {
      return absDiffHours === 1 ? 'in 1 Stunde' : `in ${absDiffHours} Stunden`;
    }
    if (absDiffDays === 1) {
      return 'morgen';
    }
    return `in ${absDiffDays} Tagen`;
  }

  // Past dates
  if (diffSec < 10) {
    return 'gerade eben';
  }
  if (diffSec < 60) {
    return `vor ${diffSec} Sekunden`;
  }
  if (diffMin < 60) {
    return diffMin === 1 ? 'vor 1 Minute' : `vor ${diffMin} Minuten`;
  }
  if (diffHours < 24) {
    return diffHours === 1 ? 'vor 1 Stunde' : `vor ${diffHours} Stunden`;
  }
  if (diffDays === 1) {
    return 'gestern';
  }
  if (diffDays < 7) {
    return `vor ${diffDays} Tagen`;
  }
  if (diffWeeks < 4) {
    return diffWeeks === 1 ? 'vor 1 Woche' : `vor ${diffWeeks} Wochen`;
  }
  if (diffMonths < 12) {
    return diffMonths === 1 ? 'vor 1 Monat' : `vor ${diffMonths} Monaten`;
  }
  if (diffYears === 1) {
    return 'vor 1 Jahr';
  }
  return `vor ${diffYears} Jahren`;
}

// ==================== FILE SIZE FORMATTING ====================

/**
 * Formatiert eine Dateigroesse (erweiterte Version mit mehr Einheiten)
 *
 * @example
 * formatFileSizeDE(500) // "500 Bytes"
 * formatFileSizeDE(1536) // "1,5 KB"
 * formatFileSizeDE(1572864) // "1,5 MB"
 * formatFileSizeDE(2147483648) // "2,0 GB"
 */
export function formatFileSizeDE(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) {
    return '-';
  }

  if (isNaN(bytes) || bytes < 0) {
    return '-';
  }

  if (bytes === 0) {
    return '0 Bytes';
  }

  const units = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  const decimals = unitIndex === 0 ? 0 : 1;
  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(size);

  return `${formatted} ${units[unitIndex]}`;
}

// ==================== PERCENTAGE FORMATTING ====================

/**
 * Formatiert einen Prozentwert (erweiterte Version)
 *
 * @example
 * formatPercentDE(0.8555) // "85,5 %"
 * formatPercentDE(0.8555, 1) // "85,6 %"
 * formatPercentDE(85.5, 1, false) // "85,5 %" (bereits als Prozent)
 */
export function formatPercentDE(
  value: number | null | undefined,
  decimals: number = 1,
  isDecimal: boolean = true
): string {
  if (value === null || value === undefined) {
    return '-';
  }

  if (isNaN(value)) {
    return '-';
  }

  const percentValue = isDecimal ? value * 100 : value;

  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(percentValue);

  return `${formatted} %`;
}

// ==================== RETENTION PERIOD FORMATTING ====================

/**
 * Formatiert eine Aufbewahrungsfrist nach deutschem Recht
 *
 * @example
 * formatRetentionPeriodDE(10) // "10 Jahre (§147 AO)"
 * formatRetentionPeriodDE(6) // "6 Jahre (§257 HGB)"
 * formatRetentionPeriodDE(3) // "3 Jahre"
 */
export function formatRetentionPeriodDE(years: number | null | undefined): string {
  if (years === null || years === undefined) {
    return '-';
  }

  if (isNaN(years) || years < 0) {
    return '-';
  }

  const yearText = years === 1 ? 'Jahr' : 'Jahre';

  // German legal retention periods
  if (years === 10) {
    return `${years} ${yearText} (§147 AO)`;
  }
  if (years === 6) {
    return `${years} ${yearText} (§257 HGB)`;
  }

  return `${years} ${yearText}`;
}

// ==================== TAX PERIOD FORMATTING ====================

/**
 * Formatiert einen Steuerzeitraum
 *
 * @example
 * formatTaxPeriodDE(2026) // "Steuerjahr 2026"
 * formatTaxPeriodDE(2026, 1) // "Q1 2026"
 * formatTaxPeriodDE(2026, 2) // "Q2 2026"
 */
export function formatTaxPeriodDE(
  year: number,
  quarter?: number | null
): string {
  if (isNaN(year)) {
    return '-';
  }

  if (quarter && quarter >= 1 && quarter <= 4) {
    return `Q${quarter} ${year}`;
  }

  return `Steuerjahr ${year}`;
}

// ==================== DOCUMENT COUNT FORMATTING ====================

/**
 * Formatiert eine Dokumentenanzahl mit korrekter Pluralisierung
 *
 * @example
 * formatDocumentCountDE(0) // "0 Dokumente"
 * formatDocumentCountDE(1) // "1 Dokument"
 * formatDocumentCountDE(5) // "5 Dokumente"
 */
export function formatDocumentCountDE(count: number | null | undefined): string {
  if (count === null || count === undefined) {
    return '-';
  }

  if (isNaN(count)) {
    return '-';
  }

  return count === 1 ? '1 Dokument' : `${count} Dokumente`;
}

// ==================== DAYS REMAINING FORMATTING ====================

/**
 * Formatiert verbleibende Tage
 *
 * @example
 * formatDaysRemainingDE(90) // "noch 90 Tage"
 * formatDaysRemainingDE(1) // "noch 1 Tag"
 * formatDaysRemainingDE(0) // "heute"
 * formatDaysRemainingDE(-1) // "abgelaufen"
 */
export function formatDaysRemainingDE(days: number | null | undefined): string {
  if (days === null || days === undefined) {
    return '-';
  }

  if (isNaN(days)) {
    return '-';
  }

  if (days < 0) {
    return 'abgelaufen';
  }

  if (days === 0) {
    return 'heute';
  }

  if (days === 1) {
    return 'noch 1 Tag';
  }

  return `noch ${days} Tage`;
}

// ==================== CONFIDENCE LEVEL FORMATTING ====================

/**
 * Formatiert eine KI-Konfidenz als Prozentsatz mit deutscher Semantik
 *
 * @example
 * formatConfidenceDE(0.95) // "95 % (sehr hoch)"
 * formatConfidenceDE(0.75) // "75 % (hoch)"
 * formatConfidenceDE(0.50) // "50 % (mittel)"
 */
export function formatConfidenceDE(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined) {
    return '-';
  }

  if (isNaN(confidence)) {
    return '-';
  }

  const percent = Math.round(confidence * 100);
  let label = '';

  if (percent >= 90) {
    label = '(sehr hoch)';
  } else if (percent >= 75) {
    label = '(hoch)';
  } else if (percent >= 50) {
    label = '(mittel)';
  } else if (percent >= 25) {
    label = '(niedrig)';
  } else {
    label = '(sehr niedrig)';
  }

  return `${percent} % ${label}`;
}

// ==================== MONEY DIFFERENCE FORMATTING ====================

/**
 * Formatiert einen Geldbetrag-Unterschied mit + oder - Vorzeichen
 *
 * @example
 * formatCurrencyDifferenceDE(100.50) // "+100,50 EUR"
 * formatCurrencyDifferenceDE(-50.25) // "-50,25 EUR"
 * formatCurrencyDifferenceDE(0) // "±0,00 EUR"
 */
export function formatCurrencyDifferenceDE(
  amount: number | null | undefined,
  currency: string = 'EUR'
): string {
  if (amount === null || amount === undefined) {
    return '-';
  }

  if (isNaN(amount)) {
    return '-';
  }

  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount));

  const sign = amount > 0 ? '+' : amount < 0 ? '-' : '±';

  return `${sign}${formatted} ${currency}`;
}
