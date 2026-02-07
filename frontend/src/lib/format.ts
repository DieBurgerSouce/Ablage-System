/**
 * German Formatting Utilities
 *
 * Zentrale Formatierungsfunktionen fuer deutsche Lokalisierung.
 * Alle Funktionen folgen deutschen Konventionen (Komma als Dezimaltrennzeichen, etc.)
 */

// ==================== CURRENCY FORMATTING ====================

/**
 * Formatiert einen Betrag als deutsche Waehrung
 *
 * @example
 * formatCurrencyDE(1234.56) // "1.234,56 EUR"
 * formatCurrencyDE(1234.56, 'USD') // "1.234,56 USD"
 * formatCurrencyDE(1234.56, 'EUR', false) // "1.234,56"
 */
export function formatCurrencyDE(
  amount: number | string | null | undefined,
  currency: string = 'EUR',
  showCurrency: boolean = true
): string {
  if (amount === null || amount === undefined || amount === '') {
    return '-';
  }

  const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount;

  if (isNaN(numAmount)) {
    return '-';
  }

  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numAmount);

  return showCurrency ? `${formatted} ${currency}` : formatted;
}

/**
 * Formatiert einen Betrag kompakt (fuer Dashboards)
 *
 * @example
 * formatCurrencyCompactDE(1234567.89) // "1,23 Mio. EUR"
 * formatCurrencyCompactDE(1234.56) // "1.234,56 EUR"
 */
export function formatCurrencyCompactDE(
  amount: number | null | undefined,
  currency: string = 'EUR'
): string {
  if (amount === null || amount === undefined) {
    return '-';
  }

  if (isNaN(amount)) {
    return '-';
  }

  const absAmount = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';

  if (absAmount >= 1_000_000) {
    const millions = absAmount / 1_000_000;
    return `${sign}${formatNumberDE(millions, 2)} Mio. ${currency}`;
  }

  if (absAmount >= 100_000) {
    const thousands = absAmount / 1_000;
    return `${sign}${formatNumberDE(thousands, 0)} Tsd. ${currency}`;
  }

  return formatCurrencyDE(amount, currency);
}

// ==================== DATE FORMATTING ====================

/**
 * Formatiert ein Datum im deutschen Format
 *
 * @example
 * formatDateDE(new Date()) // "26.01.2026"
 * formatDateDE('2026-01-26') // "26.01.2026"
 * formatDateDE(new Date(), 'long') // "26. Januar 2026"
 */
export function formatDateDE(
  date: Date | string | null | undefined,
  format: 'short' | 'medium' | 'long' = 'short'
): string {
  if (!date) {
    return '-';
  }

  const dateObj = typeof date === 'string' ? new Date(date) : date;

  if (isNaN(dateObj.getTime())) {
    return '-';
  }

  const options: Intl.DateTimeFormatOptions =
    format === 'short'
      ? { day: '2-digit', month: '2-digit', year: 'numeric' }
      : format === 'medium'
      ? { day: '2-digit', month: 'short', year: 'numeric' }
      : { day: 'numeric', month: 'long', year: 'numeric' };

  return new Intl.DateTimeFormat('de-DE', options).format(dateObj);
}

/**
 * Formatiert Datum und Uhrzeit im deutschen Format
 *
 * @example
 * formatDateTimeDE(new Date()) // "26.01.2026, 14:30"
 * formatDateTimeDE(new Date(), true) // "26.01.2026, 14:30:45"
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

  const options: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...(showSeconds ? { second: '2-digit' } : {}),
  };

  return new Intl.DateTimeFormat('de-DE', options).format(dateObj);
}

/**
 * Formatiert ein Datum relativ zum aktuellen Zeitpunkt
 *
 * @example
 * formatRelativeDateDE(new Date(Date.now() - 60000)) // "vor 1 Minute"
 * formatRelativeDateDE(new Date(Date.now() - 3600000)) // "vor 1 Stunde"
 */
export function formatRelativeDateDE(date: Date | string | null | undefined): string {
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

  if (diffSec < 60) {
    return 'gerade eben';
  }
  if (diffMin < 60) {
    return diffMin === 1 ? 'vor 1 Minute' : `vor ${diffMin} Minuten`;
  }
  if (diffHours < 24) {
    return diffHours === 1 ? 'vor 1 Stunde' : `vor ${diffHours} Stunden`;
  }
  if (diffDays < 7) {
    return diffDays === 1 ? 'gestern' : `vor ${diffDays} Tagen`;
  }
  if (diffWeeks < 4) {
    return diffWeeks === 1 ? 'vor 1 Woche' : `vor ${diffWeeks} Wochen`;
  }
  if (diffMonths < 12) {
    return diffMonths === 1 ? 'vor 1 Monat' : `vor ${diffMonths} Monaten`;
  }

  return formatDateDE(dateObj);
}

// ==================== NUMBER FORMATTING ====================

/**
 * Formatiert eine Zahl im deutschen Format
 *
 * @example
 * formatNumberDE(1234567.89) // "1.234.567,89"
 * formatNumberDE(1234.5, 0) // "1.235"
 * formatNumberDE(0.1234, 2) // "0,12"
 */
export function formatNumberDE(
  value: number | string | null | undefined,
  decimals: number = 2
): string {
  if (value === null || value === undefined || value === '') {
    return '-';
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (isNaN(numValue)) {
    return '-';
  }

  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(numValue);
}

/**
 * Formatiert einen Prozentwert
 *
 * @example
 * formatPercentDE(0.1234) // "12,34 %"
 * formatPercentDE(0.1234, 0) // "12 %"
 * formatPercentDE(12.34, 1, false) // "12,3 %" (bereits als Prozent)
 */
export function formatPercentDE(
  value: number | null | undefined,
  decimals: number = 2,
  isDecimal: boolean = true
): string {
  if (value === null || value === undefined) {
    return '-';
  }

  if (isNaN(value)) {
    return '-';
  }

  const percentValue = isDecimal ? value * 100 : value;
  return `${formatNumberDE(percentValue, decimals)} %`;
}

/**
 * Formatiert eine Dateigroesse
 *
 * @example
 * formatFileSizeDE(1024) // "1,0 KB"
 * formatFileSizeDE(1048576) // "1,0 MB"
 */
export function formatFileSizeDE(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) {
    return '-';
  }

  if (isNaN(bytes) || bytes < 0) {
    return '-';
  }

  const units = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  const decimals = unitIndex === 0 ? 0 : 1;
  return `${formatNumberDE(size, decimals)} ${units[unitIndex]}`;
}

// ==================== IBAN/VAT FORMATTING ====================

/**
 * Formatiert eine IBAN mit Leerzeichen
 *
 * @example
 * formatIBANDE('DE89370400440532013000') // "DE89 3704 0044 0532 0130 00"
 */
export function formatIBANDE(iban: string | null | undefined): string {
  if (!iban) {
    return '-';
  }

  // Entferne bestehende Leerzeichen und mache uppercase
  const cleaned = iban.replace(/\s/g, '').toUpperCase();

  // Fuege alle 4 Zeichen ein Leerzeichen ein
  return cleaned.replace(/(.{4})/g, '$1 ').trim();
}

/**
 * Formatiert eine USt-IdNr
 *
 * @example
 * formatVATID('DE123456789') // "DE 123 456 789"
 */
export function formatVATID(vatId: string | null | undefined): string {
  if (!vatId) {
    return '-';
  }

  const cleaned = vatId.replace(/\s/g, '').toUpperCase();

  // Deutsche USt-IdNr: DE + 9 Ziffern
  if (cleaned.startsWith('DE') && cleaned.length === 11) {
    return `DE ${cleaned.slice(2, 5)} ${cleaned.slice(5, 8)} ${cleaned.slice(8)}`;
  }

  // Andere: Laendercode + Rest
  const countryCode = cleaned.slice(0, 2);
  const number = cleaned.slice(2);
  return `${countryCode} ${number}`;
}

// ==================== TEXT FORMATTING ====================

/**
 * Kuerzt einen Text und fuegt Ellipsis hinzu
 *
 * @example
 * truncateText('Ein sehr langer Text', 10) // "Ein sehr l..."
 */
export function truncateText(
  text: string | null | undefined,
  maxLength: number
): string {
  if (!text) {
    return '-';
  }

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength)}...`;
}

/**
 * Formatiert einen Namen (Vorname Nachname oder E-Mail)
 *
 * @example
 * formatUserName({ first_name: 'Max', last_name: 'Mustermann' }) // "Max Mustermann"
 * formatUserName({ email: 'max@example.com' }) // "max@example.com"
 */
export function formatUserName(
  user: { first_name?: string | null; last_name?: string | null; email?: string | null } | null | undefined
): string {
  if (!user) {
    return '-';
  }

  const { first_name, last_name, email } = user;

  if (first_name && last_name) {
    return `${first_name} ${last_name}`;
  }

  if (first_name) {
    return first_name;
  }

  if (last_name) {
    return last_name;
  }

  if (email) {
    return email;
  }

  return '-';
}
