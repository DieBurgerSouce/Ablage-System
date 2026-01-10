/**
 * Formatierungsfunktionen für Kassenbuch
 */

/**
 * Formatiert einen Betrag als Waehrung (EUR)
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

/**
 * Formatiert ein Datum im deutschen Format
 */
export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

/**
 * Formatiert Datum und Uhrzeit im deutschen Format
 */
export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

/**
 * Formatiert den Eintragstyp auf Deutsch
 */
export function formatEntryType(type: string): string {
  const types: Record<string, string> = {
    income: 'Einnahme',
    deposit: 'Einlage',
    expense: 'Ausgabe',
    withdrawal: 'Entnahme',
    entertainment: 'Bewirtung',
    travel: 'Reisekosten',
    office: 'Buerobedarf',
    fuel: 'Kraftstoff',
    parking: 'Parkgebuehren',
    postage: 'Porto',
    tips: 'Trinkgeld',
    gifts: 'Geschenke',
    difference_plus: 'Kassendifferenz +',
    difference_minus: 'Kassendifferenz -',
    cancellation: 'Storno',
    opening: 'Eröffnung',
  };
  return types[type] ?? type;
}

/**
 * Gibt die passende Farbe für einen Eintragstyp zurück
 */
export function getEntryTypeColor(type: string): 'green' | 'red' | 'yellow' | 'blue' | 'gray' {
  const incomeTypes = ['income', 'deposit', 'difference_plus', 'opening'];
  const expenseTypes = ['expense', 'withdrawal', 'entertainment', 'travel', 'office', 'fuel', 'parking', 'postage', 'tips', 'gifts', 'difference_minus'];
  const cancelTypes = ['cancellation'];

  if (incomeTypes.includes(type)) return 'green';
  if (expenseTypes.includes(type)) return 'red';
  if (cancelTypes.includes(type)) return 'yellow';
  return 'gray';
}

/**
 * Formatiert den MwSt-Satz
 */
export function formatTaxRate(rate: number): string {
  if (rate === 0) return '0%';
  if (rate === 7) return '7%';
  if (rate === 19) return '19%';
  return `${rate}%`;
}
