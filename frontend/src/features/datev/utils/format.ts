/**
 * DATEV Formatierungs-Utilities
 *
 * Hilfsfunktionen für die Anzeige von DATEV-Daten.
 */

import type { DATEVExportStatus, Kontenrahmen } from '@/lib/api/services/datev';

// =============================================================================
// KONTENRAHMEN FORMATTING
// =============================================================================

/**
 * Formatiert Kontenrahmen-Name für Anzeige
 */
export function formatKontenrahmen(kontenrahmen: Kontenrahmen): string {
    switch (kontenrahmen) {
        case 'SKR03':
            return 'SKR 03';
        case 'SKR04':
            return 'SKR 04';
        default:
            return kontenrahmen;
    }
}

/**
 * Gibt die vollständige Beschreibung eines Kontenrahmens zurück
 */
export function getKontenrahmenDescription(kontenrahmen: Kontenrahmen): string {
    switch (kontenrahmen) {
        case 'SKR03':
            return 'Standardkontenrahmen für Industrie, Handel und Handwerk (prozessorientiert)';
        case 'SKR04':
            return 'Standardkontenrahmen für bilanzierende Unternehmen (abschlussorientiert)';
        default:
            return '';
    }
}

// =============================================================================
// EXPORT STATUS FORMATTING
// =============================================================================

/**
 * Formatiert Export-Status für Anzeige
 */
export function formatExportStatus(status: DATEVExportStatus): string {
    switch (status) {
        case 'completed':
            return 'Erfolgreich';
        case 'failed':
            return 'Fehlgeschlagen';
        case 'partial':
            return 'Teilweise exportiert';
        default:
            return status;
    }
}

/**
 * Gibt die Farbe/Variante für einen Export-Status zurück
 */
export function getExportStatusVariant(
    status: DATEVExportStatus
): 'default' | 'success' | 'destructive' | 'warning' {
    switch (status) {
        case 'completed':
            return 'success';
        case 'failed':
            return 'destructive';
        case 'partial':
            return 'warning';
        default:
            return 'default';
    }
}

// =============================================================================
// NUMBER FORMATTING
// =============================================================================

/**
 * Formatiert einen Betrag als Währung (EUR)
 */
export function formatCurrency(amount: number | null | undefined): string {
    if (amount == null) return '–';
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
    }).format(amount);
}

/**
 * Formatiert eine Zahl mit Tausendertrennzeichen
 */
export function formatNumber(value: number | null | undefined): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE').format(value);
}

/**
 * Formatiert Bytes als lesbare Größe
 */
export function formatFileSize(bytes: number | null | undefined): string {
    if (bytes == null) return '–';

    const units = ['B', 'KB', 'MB', 'GB'];
    let unitIndex = 0;
    let size = bytes;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }

    return `${size.toFixed(1)} ${units[unitIndex]}`;
}

// =============================================================================
// DATE FORMATTING
// =============================================================================

/**
 * Formatiert ein ISO-Datum als deutsches Datum
 */
export function formatDate(date: string | null | undefined): string {
    if (!date) return '–';
    return new Date(date).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
}

/**
 * Formatiert ein ISO-Datum als deutsches Datum mit Uhrzeit
 */
export function formatDateTime(date: string | null | undefined): string {
    if (!date) return '–';
    return new Date(date).toLocaleString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * Formatiert einen Zeitraum als "von - bis"
 */
export function formatPeriod(from: string | null, to: string | null): string {
    if (!from && !to) return 'Gesamter Zeitraum';
    if (from && !to) return `Ab ${formatDate(from)}`;
    if (!from && to) return `Bis ${formatDate(to)}`;
    return `${formatDate(from)} – ${formatDate(to)}`;
}

// =============================================================================
// ACCOUNT FORMATTING
// =============================================================================

/**
 * Formatiert eine Kontonummer (mit Leerzeichen alle 4 Stellen)
 */
export function formatAccountNumber(account: string | null | undefined): string {
    if (!account) return '–';
    // Für kurze Kontonummern keine Formatierung
    if (account.length <= 4) return account;
    // Sonst von rechts alle 4 Stellen ein Leerzeichen
    return account.replace(/(\d)(?=(\d{4})+$)/g, '$1 ');
}

/**
 * Formatiert eine IBAN mit Leerzeichen
 */
export function formatIban(iban: string | null | undefined): string {
    if (!iban) return '–';
    return iban.replace(/(.{4})/g, '$1 ').trim();
}

/**
 * Formatiert eine USt-IdNr (Ländercode + Nummer getrennt)
 */
export function formatVatId(vatId: string | null | undefined): string {
    if (!vatId || vatId.length < 3) return vatId || '–';
    const countryCode = vatId.slice(0, 2);
    const rest = vatId.slice(2);
    return `${countryCode} ${rest}`;
}

// =============================================================================
// TEXT FORMATTING
// =============================================================================

/**
 * Kürzt einen Text auf maximale Länge mit Ellipsis
 */
export function truncateText(text: string | null | undefined, maxLength: number): string {
    if (!text) return '–';
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 3)}...`;
}

/**
 * Formatiert einen Firmennamen (entfernt übermäßige Whitespaces)
 */
export function formatCompanyName(name: string | null | undefined): string {
    if (!name) return '–';
    return name.replace(/\s+/g, ' ').trim();
}
