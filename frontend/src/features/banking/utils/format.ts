/**
 * Banking Format Utilities
 *
 * Gemeinsame Formatierungsfunktionen fuer das Banking-Modul
 */

/**
 * Formatiert einen Betrag als Waehrung (EUR)
 *
 * @param value - Der zu formatierende Betrag
 * @param options - Optionale Formatierungsoptionen
 * @param options.currency - Waehrungscode (Standard: EUR)
 * @param options.decimals - Anzahl Dezimalstellen (Standard: 2, nutze 0 fuer ganze Zahlen)
 * @returns Formatierter Waehrungsstring (z.B. "1.234,56 €")
 */
export function formatCurrency(
    value: number,
    options?: { currency?: string; decimals?: number }
): string {
    const { currency = 'EUR', decimals = 2 } = options ?? {};
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency,
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(value);
}

/**
 * Formatiert ein Datum im deutschen Format
 *
 * @param dateStr - ISO-Datumstring oder null
 * @returns Formatiertes Datum (z.B. "17.12.2024") oder "-" bei null
 */
export function formatDate(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    return new Intl.DateTimeFormat('de-DE').format(new Date(dateStr));
}

/**
 * Formatiert ein Datum kurz (nur Tag und Monat)
 *
 * @param dateStr - ISO-Datumstring
 * @returns Formatiertes Datum (z.B. "17.12.")
 */
export function formatDateShort(dateStr: string): string {
    return new Intl.DateTimeFormat('de-DE', {
        day: '2-digit',
        month: '2-digit',
    }).format(new Date(dateStr));
}

/**
 * Formatiert ein Datum mit Uhrzeit im deutschen Format
 *
 * @param dateStr - ISO-Datumstring oder null
 * @returns Formatiertes Datum mit Zeit (z.B. "17.12.2024, 14:30") oder "-" bei null
 */
export function formatDateTime(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    return new Intl.DateTimeFormat('de-DE', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(dateStr));
}

/**
 * Formatiert einen Prozentsatz
 *
 * @param value - Der Wert als Rohwert (z.B. 85 fuer 85%) oder Dezimalwert (z.B. 0.85)
 * @param options - Optionale Formatierungsoptionen
 * @param options.decimals - Anzahl Dezimalstellen (Standard: 1)
 * @param options.isRawValue - Wenn true, wird value als 0-100 interpretiert (Standard: true)
 * @returns Formatierter Prozentstring (z.B. "85,0 %")
 */
export function formatPercent(
    value: number,
    options?: { decimals?: number; isRawValue?: boolean }
): string {
    const { decimals = 1, isRawValue = true } = options ?? {};
    const normalizedValue = isRawValue ? value / 100 : value;
    return new Intl.NumberFormat('de-DE', {
        style: 'percent',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(normalizedValue);
}

/**
 * Formatiert eine Zahl mit Tausendertrennzeichen
 *
 * @param value - Die zu formatierende Zahl
 * @param decimals - Anzahl Dezimalstellen (Standard: 0)
 * @returns Formatierte Zahl (z.B. "1.234")
 */
export function formatNumber(value: number, decimals = 0): string {
    return new Intl.NumberFormat('de-DE', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(value);
}
