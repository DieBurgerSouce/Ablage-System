/**
 * ESG API Client
 *
 * API-Client für das Nachhaltigkeitsberichterstattungs-Modul.
 * Alle Endpunkte unter /api/v1/esg/
 */

import { apiClient } from '@/lib/api/client';
import type {
  ESGDashboardSummary,
  CarbonEmission,
  CarbonEmissionCreate,
  EmissionFactor,
  EmissionCalculationResult,
  CarbonTrendPoint,
  CarbonEmissionFilterParams,
  SupplierRating,
  SupplierRatingCreate,
  RatingCriterion,
  SupplierRiskSummary,
  SupplierRatingFilterParams,
  Certification,
  CertificationCreate,
  CertificationType,
  CertificationSummary,
  ExpiringCertification,
  UpcomingAudit,
  CertificationFilterParams,
  ESGReport,
  ESGReportCreate,
  ReportTemplate,
  ReportDetail,
  ReportFilterParams,
  ESGGoal,
  ESGGoalCreate,
  ESGGoalProgressUpdate,
  GoalFilterParams,
  SDGMapping,
  PaginatedResponse,
  EmissionRecordResponse,
  SupplierRatingResponse,
  CertificationAddResponse,
  ReportGenerateResponse,
  GoalCreateResponse,
  GoalProgressResponse,
} from '../types';

const BASE_PATH = '/esg';

// ==================== Dashboard ====================

/**
 * Hole ESG-Dashboard-Zusammenfassung
 */
export async function getDashboard(params?: {
  period_start?: string;
  period_end?: string;
}): Promise<ESGDashboardSummary> {
  const response = await apiClient.get<ESGDashboardSummary>(
    `${BASE_PATH}/dashboard`,
    { params }
  );
  return response.data;
}

// ==================== Carbon Footprint ====================

/**
 * Hole verfügbare Emissionsfaktoren
 */
export async function getEmissionFactors(): Promise<{ factors: EmissionFactor[] }> {
  const response = await apiClient.get<{ factors: EmissionFactor[] }>(
    `${BASE_PATH}/carbon-footprint/emission-factors`
  );
  return response.data;
}

/**
 * Berechne CO2-Emissionen ohne Speicherung
 */
export async function calculateEmissions(params: {
  source_category: string;
  consumption_value: number;
  custom_factor?: number;
}): Promise<EmissionCalculationResult> {
  const response = await apiClient.post<EmissionCalculationResult>(
    `${BASE_PATH}/carbon-footprint/calculate`,
    null,
    { params }
  );
  return response.data;
}

/**
 * Erfasse CO2-Emissionen
 */
export async function recordEmission(
  data: CarbonEmissionCreate
): Promise<EmissionRecordResponse> {
  const response = await apiClient.post<EmissionRecordResponse>(
    `${BASE_PATH}/carbon-footprint`,
    data
  );
  return response.data;
}

/**
 * Hole erfasste Emissionen
 */
export async function getEmissions(
  params?: CarbonEmissionFilterParams
): Promise<PaginatedResponse<CarbonEmission>> {
  const response = await apiClient.get<PaginatedResponse<CarbonEmission>>(
    `${BASE_PATH}/carbon-footprint`,
    { params }
  );
  return response.data;
}

/**
 * Hole Emissions-Zusammenfassung
 */
export async function getEmissionsSummary(params: {
  period_start: string;
  period_end: string;
}): Promise<{
  total_kg: number;
  scope_1_kg: number;
  scope_2_kg: number;
  scope_3_kg: number;
  by_category: Record<string, number>;
}> {
  const response = await apiClient.get<{
    total_kg: number;
    scope_1_kg: number;
    scope_2_kg: number;
    scope_3_kg: number;
    by_category: Record<string, number>;
  }>(`${BASE_PATH}/carbon-footprint/summary`, { params });
  return response.data;
}

/**
 * Hole CO2-Fussabdruck-Trend
 */
export async function getCarbonTrend(
  months: number = 12
): Promise<CarbonTrendPoint[]> {
  const response = await apiClient.get<CarbonTrendPoint[]>(
    `${BASE_PATH}/carbon-footprint/trend`,
    { params: { months } }
  );
  return response.data;
}

// ==================== Supplier Ratings ====================

/**
 * Hole Bewertungskriterien für Lieferanten
 */
export async function getRatingCriteria(): Promise<{ criteria: RatingCriterion[] }> {
  const response = await apiClient.get<{ criteria: RatingCriterion[] }>(
    `${BASE_PATH}/supplier-ratings/criteria`
  );
  return response.data;
}

/**
 * Erstelle Lieferanten-Nachhaltigkeitsbewertung
 */
export async function createRating(
  data: SupplierRatingCreate
): Promise<SupplierRatingResponse> {
  const response = await apiClient.post<SupplierRatingResponse>(
    `${BASE_PATH}/supplier-ratings`,
    data
  );
  return response.data;
}

/**
 * Hole Lieferanten-Bewertungen
 */
export async function getRatings(
  params?: SupplierRatingFilterParams
): Promise<PaginatedResponse<SupplierRating>> {
  const response = await apiClient.get<PaginatedResponse<SupplierRating>>(
    `${BASE_PATH}/supplier-ratings`,
    { params }
  );
  return response.data;
}

/**
 * Hole Risiko-Zusammenfassung aller Lieferanten
 */
export async function getRiskSummary(): Promise<SupplierRiskSummary> {
  const response = await apiClient.get<SupplierRiskSummary>(
    `${BASE_PATH}/supplier-ratings/summary`
  );
  return response.data;
}

/**
 * Hole neueste Bewertung für einen Lieferanten
 */
export async function getLatestRating(
  entityId: string
): Promise<SupplierRating> {
  const response = await apiClient.get<SupplierRating>(
    `${BASE_PATH}/supplier-ratings/${entityId}/latest`
  );
  return response.data;
}

// ==================== Certifications ====================

/**
 * Hole bekannte Zertifizierungstypen
 */
export async function getCertificationTypes(): Promise<{ types: CertificationType[] }> {
  const response = await apiClient.get<{ types: CertificationType[] }>(
    `${BASE_PATH}/certifications/types`
  );
  return response.data;
}

/**
 * Fuege Zertifizierung hinzu
 */
export async function addCertification(
  data: CertificationCreate
): Promise<CertificationAddResponse> {
  const response = await apiClient.post<CertificationAddResponse>(
    `${BASE_PATH}/certifications`,
    data
  );
  return response.data;
}

/**
 * Hole Zertifizierungen
 */
export async function getCertifications(
  params?: CertificationFilterParams
): Promise<PaginatedResponse<Certification>> {
  const response = await apiClient.get<PaginatedResponse<Certification>>(
    `${BASE_PATH}/certifications`,
    { params }
  );
  return response.data;
}

/**
 * Hole Zertifizierungs-Zusammenfassung
 */
export async function getCertificationSummary(): Promise<CertificationSummary> {
  const response = await apiClient.get<CertificationSummary>(
    `${BASE_PATH}/certifications/summary`
  );
  return response.data;
}

/**
 * Hole bald ablaufende Zertifizierungen
 */
export async function getExpiring(
  days: number = 90
): Promise<{ items: ExpiringCertification[] }> {
  const response = await apiClient.get<{ items: ExpiringCertification[] }>(
    `${BASE_PATH}/certifications/expiring`,
    { params: { days } }
  );
  return response.data;
}

/**
 * Hole anstehende Audits
 */
export async function getUpcomingAudits(
  days: number = 60
): Promise<{ items: UpcomingAudit[] }> {
  const response = await apiClient.get<{ items: UpcomingAudit[] }>(
    `${BASE_PATH}/certifications/upcoming-audits`,
    { params: { days } }
  );
  return response.data;
}

/**
 * Hole Zertifizierungs-Details
 */
export async function getCertificationDetail(
  certificationId: string
): Promise<Certification> {
  const response = await apiClient.get<Certification>(
    `${BASE_PATH}/certifications/${certificationId}`
  );
  return response.data;
}

// ==================== Reports ====================

/**
 * Hole verfügbare Berichtsvorlagen
 */
export async function getTemplates(): Promise<{ templates: ReportTemplate[] }> {
  const response = await apiClient.get<{ templates: ReportTemplate[] }>(
    `${BASE_PATH}/reports/templates`
  );
  return response.data;
}

/**
 * Generiere einen ESG-Bericht
 */
export async function generateReport(
  data: ESGReportCreate
): Promise<ReportGenerateResponse> {
  const response = await apiClient.post<ReportGenerateResponse>(
    `${BASE_PATH}/reports/generate`,
    data
  );
  return response.data;
}

/**
 * Hole ESG-Berichte
 */
export async function getReports(
  params?: ReportFilterParams
): Promise<PaginatedResponse<ESGReport>> {
  const response = await apiClient.get<PaginatedResponse<ESGReport>>(
    `${BASE_PATH}/reports`,
    { params }
  );
  return response.data;
}

/**
 * Hole Bericht-Details
 */
export async function getReportDetail(
  reportId: string
): Promise<ReportDetail> {
  const response = await apiClient.get<ReportDetail>(
    `${BASE_PATH}/reports/${reportId}`
  );
  return response.data;
}

// ==================== Goals ====================

/**
 * Erstelle ein ESG-Ziel
 */
export async function createGoal(
  data: ESGGoalCreate
): Promise<GoalCreateResponse> {
  const response = await apiClient.post<GoalCreateResponse>(
    `${BASE_PATH}/goals`,
    data
  );
  return response.data;
}

/**
 * Hole ESG-Ziele
 */
export async function getGoals(
  params?: GoalFilterParams
): Promise<{ items: ESGGoal[] }> {
  const response = await apiClient.get<{ items: ESGGoal[] }>(
    `${BASE_PATH}/goals`,
    { params }
  );
  return response.data;
}

/**
 * Aktualisiere Ziel-Fortschritt
 */
export async function updateGoalProgress(
  goalId: string,
  data: ESGGoalProgressUpdate
): Promise<GoalProgressResponse> {
  const response = await apiClient.patch<GoalProgressResponse>(
    `${BASE_PATH}/goals/${goalId}/progress`,
    data
  );
  return response.data;
}

// ==================== SDG Mapping ====================

/**
 * Hole SDG-Mapping
 */
export async function getSDGMapping(): Promise<{ mapping: SDGMapping[] }> {
  const response = await apiClient.get<{ mapping: SDGMapping[] }>(
    `${BASE_PATH}/sdg-mapping`
  );
  return response.data;
}

// ==================== Export all functions ====================

export const esgApi = {
  // Dashboard
  getDashboard,

  // Carbon
  getEmissionFactors,
  calculateEmissions,
  recordEmission,
  getEmissions,
  getEmissionsSummary,
  getCarbonTrend,

  // Suppliers
  getRatingCriteria,
  createRating,
  getRatings,
  getRiskSummary,
  getLatestRating,

  // Certifications
  getCertificationTypes,
  addCertification,
  getCertifications,
  getCertificationSummary,
  getExpiring,
  getUpcomingAudits,
  getCertificationDetail,

  // Reports
  getTemplates,
  generateReport,
  getReports,
  getReportDetail,

  // Goals
  createGoal,
  getGoals,
  updateGoalProgress,

  // SDG
  getSDGMapping,
};

export default esgApi;
