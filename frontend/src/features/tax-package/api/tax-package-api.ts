/**
 * Tax Package API Client - Steuerberater-Paket Verwaltung
 *
 * API-Funktionen für automatische Buchhaltungspakete.
 * GoBD-konforme Paketgenerierung und -versand.
 *
 * Backend-Endpunkte:
 * - POST /api/v1/tax-advisor/packages/configurations - Konfiguration erstellen
 * - GET /api/v1/tax-advisor/packages/configurations - Konfigurationen auflisten
 * - GET /api/v1/tax-advisor/packages/configurations/{id} - Konfiguration abrufen
 * - POST /api/v1/tax-advisor/packages - Paket erstellen
 * - GET /api/v1/tax-advisor/packages - Pakete auflisten
 * - GET /api/v1/tax-advisor/packages/{id} - Paket abrufen
 * - POST /api/v1/tax-advisor/packages/{id}/generate - Paket generieren
 * - POST /api/v1/tax-advisor/packages/{id}/send - Paket versenden
 * - GET /api/v1/tax-advisor/packages/{id}/download - Paket herunterladen
 * - POST /api/v1/tax-advisor/packages/{id}/remind - Erinnerung senden
 * - GET /api/v1/tax-advisor/packages/statistics/summary - Statistiken
 * - POST /api/v1/tax-advisor/packages/completeness-check - Vollständigkeitsprüfung
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface PackageConfiguration {
  id: string;
  company_id: string;
  name: string;
  frequency: 'monthly' | 'quarterly' | 'yearly' | 'on_demand';
  document_categories: string[];
  period_start_day: number;
  delivery_delay_days: number;
  auto_send: boolean;
  auto_reminder: boolean;
  reminder_days_before: number;
  recipient_email: string | null;
  tax_advisor_user_id: string | null;
  include_datev_export: boolean;
  include_pdf_copies: boolean;
  include_summary_report: boolean;
  is_active: boolean;
  created_at: string;
}

export interface MissingDocument {
  document_type: string;
  description: string;
  expected_date: string | null;
  importance: 'required' | 'recommended' | 'optional';
  notes: string | null;
}

export interface TaxPackage {
  id: string;
  configuration_id: string | null;
  company_id: string;
  period_start: string;
  period_end: string;
  period_label: string;
  status: 'draft' | 'ready' | 'sent' | 'downloaded' | 'expired';
  document_count: number;
  total_size_bytes: number;
  datev_export_path: string | null;
  pdf_archive_path: string | null;
  summary_report_path: string | null;
  created_at: string;
  sent_at: string | null;
  downloaded_at: string | null;
  expires_at: string | null;
  missing_documents: MissingDocument[];
}

export interface MissingItem {
  category: string;
  description: string;
  severity: 'required' | 'recommended' | 'optional';
  suggestion: string;
}

export interface CompletenessReport {
  period: string;
  period_start: string;
  period_end: string;
  completeness_score: number;
  checks_passed: number;
  total_checks: number;
  missing_items: MissingItem[];
  is_complete: boolean;
}

export interface PackageStats {
  total_packages: number;
  by_status: Record<string, number>;
  total_documents: number;
  total_size_bytes: number;
  total_size_mb: number;
  packages_with_missing_documents: number;
  completion_rate: number;
}

export interface PackageCreateRequest {
  period: string;
  config_id?: string;
}

export interface SendPackageRequest {
  recipient_email?: string;
}

export interface ReminderRequest {
  admin_email: string;
  tax_advisor_name?: string;
}

export interface MessageResponse {
  message: string;
  details?: Record<string, unknown>;
}

// ==================== Query Keys ====================

export const taxPackageKeys = {
  all: ['tax-packages'] as const,
  configurations: () => [...taxPackageKeys.all, 'configurations'] as const,
  configuration: (id: string) => [...taxPackageKeys.all, 'configuration', id] as const,
  packages: (statusFilter?: string) =>
    [...taxPackageKeys.all, 'packages', statusFilter ?? 'all'] as const,
  package: (id: string) => [...taxPackageKeys.all, 'package', id] as const,
  stats: () => [...taxPackageKeys.all, 'stats'] as const,
  completeness: (year: number, quarter?: number) =>
    [...taxPackageKeys.all, 'completeness', year, quarter ?? 'all'] as const,
};

// ==================== API Functions ====================

/**
 * Listet alle Paket-Konfigurationen
 */
export async function getPackageConfigurations(): Promise<PackageConfiguration[]> {
  const response = await apiClient.get<PackageConfiguration[]>(
    '/tax-advisor/packages/configurations'
  );
  return response.data;
}

/**
 * Ruft eine spezifische Konfiguration ab
 */
export async function getPackageConfiguration(id: string): Promise<PackageConfiguration> {
  const response = await apiClient.get<PackageConfiguration>(
    `/tax-advisor/packages/configurations/${id}`
  );
  return response.data;
}

/**
 * Listet alle Pakete
 *
 * @param statusFilter - Optionaler Status-Filter
 */
export async function getPackages(statusFilter?: string): Promise<TaxPackage[]> {
  const response = await apiClient.get<TaxPackage[]>('/tax-advisor/packages', {
    params: statusFilter ? { status_filter: statusFilter } : {},
  });
  return response.data;
}

/**
 * Ruft ein spezifisches Paket ab
 */
export async function getPackage(id: string): Promise<TaxPackage> {
  const response = await apiClient.get<TaxPackage>(`/tax-advisor/packages/${id}`);
  return response.data;
}

/**
 * Holt Paket-Statistiken
 */
export async function getPackageStats(): Promise<PackageStats> {
  const response = await apiClient.get<PackageStats>('/tax-advisor/packages/statistics/summary');
  return response.data;
}

/**
 * Führt eine Vollständigkeitsprüfung durch
 *
 * @param year - Jahr (2020-2030)
 * @param quarter - Optionales Quartal (1-4)
 */
export async function checkCompleteness(
  year: number,
  quarter?: number
): Promise<CompletenessReport> {
  const response = await apiClient.post<CompletenessReport>(
    '/tax-advisor/packages/completeness-check',
    null,
    {
      params: {
        year,
        ...(quarter ? { quarter } : {}),
      },
    }
  );
  return response.data;
}

/**
 * Erstellt ein neues Paket
 *
 * @param data - Paket-Daten (period, config_id)
 */
export async function createPackage(data: PackageCreateRequest): Promise<TaxPackage> {
  const response = await apiClient.post<TaxPackage>('/tax-advisor/packages', data);
  return response.data;
}

/**
 * Generiert Paket-Dateien (DATEV, PDF, Report)
 *
 * @param packageId - Paket-ID
 */
export async function generatePackage(packageId: string): Promise<TaxPackage> {
  const response = await apiClient.post<TaxPackage>(
    `/tax-advisor/packages/${packageId}/generate`
  );
  return response.data;
}

/**
 * Versendet ein Paket per E-Mail
 *
 * @param packageId - Paket-ID
 * @param data - Versand-Daten (optional recipient_email)
 */
export async function sendPackage(
  packageId: string,
  data?: SendPackageRequest
): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(
    `/tax-advisor/packages/${packageId}/send`,
    data ?? {}
  );
  return response.data;
}

/**
 * Sendet eine Erinnerung für fehlende Dokumente
 *
 * @param packageId - Paket-ID
 * @param data - Erinnerungs-Daten
 */
export async function sendReminder(
  packageId: string,
  data: ReminderRequest
): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(
    `/tax-advisor/packages/${packageId}/remind`,
    data
  );
  return response.data;
}

/**
 * Lädt ein Paket herunter
 *
 * @param packageId - Paket-ID
 * @param fileType - Dateityp (all, datev, pdf, report)
 */
export async function downloadPackage(
  packageId: string,
  fileType: 'all' | 'datev' | 'pdf' | 'report' = 'all'
): Promise<Blob> {
  const response = await apiClient.get(`/tax-advisor/packages/${packageId}/download`, {
    params: { file_type: fileType },
    responseType: 'blob',
  });
  return response.data;
}
