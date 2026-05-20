/**
 * Formatierungsfunktionen für Spesenabrechnung
 */

import type { ExpenseReportStatus, ExpenseType } from '@/types/models/expense';

/**
 * Formatiert einen Betrag als Währung (EUR)
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
 * Formatiert den Abrechnungsstatus auf Deutsch
 */
export function formatStatus(status: ExpenseReportStatus): string {
  const statuses: Record<ExpenseReportStatus, string> = {
    draft: 'Entwurf',
    submitted: 'Eingereicht',
    in_review: 'In Prüfung',
    approved: 'Genehmigt',
    rejected: 'Abgelehnt',
    paid: 'Ausgezahlt',
  };
  return statuses[status] ?? status;
}

/**
 * Gibt die passende Farbe für einen Status zurück
 */
export function getStatusColor(status: ExpenseReportStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'draft':
      return 'secondary';
    case 'submitted':
    case 'in_review':
      return 'outline';
    case 'approved':
    case 'paid':
      return 'default';
    case 'rejected':
      return 'destructive';
    default:
      return 'secondary';
  }
}

/**
 * Formatiert den Positionstyp auf Deutsch
 */
export function formatExpenseType(type: ExpenseType): string {
  const types: Record<ExpenseType, string> = {
    receipt: 'Beleg',
    mileage: 'Kilometergeld',
    per_diem: 'Verpflegungspauschale',
    flat_rate: 'Pauschale',
  };
  return types[type] ?? type;
}

/**
 * Formatiert Kilometer
 */
export function formatKilometers(km: number): string {
  return `${km.toLocaleString('de-DE')} km`;
}

/**
 * Formatiert Stunden
 */
export function formatHours(hours: number): string {
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  if (m === 0) return `${h} Std.`;
  return `${h} Std. ${m} Min.`;
}
