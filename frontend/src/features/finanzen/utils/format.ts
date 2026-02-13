/**
 * Finanzen-Modul: Formatierungs-Hilfsfunktionen
 */

/**
 * Formatiert einen Geldbetrag fuer die Anzeige
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

/**
 * Formatiert einen Saldo mit Vorzeichen
 */
export function formatSaldo(saldo: number): string {
  const formatted = formatCurrency(Math.abs(saldo));
  if (saldo > 0) {
    return `+${formatted}`;
  } else if (saldo < 0) {
    return `-${formatted}`;
  }
  return formatted;
}

/**
 * Formatiert ein Datum fuer die Anzeige
 */
export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}
