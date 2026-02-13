/**
 * Data Quality API Service
 *
 * Handles all API calls for the Data Quality Cockpit.
 */

import { apiClient } from '@/lib/api/client';
import type {
  QualityReportResponse,
  QualityReport,
  QualityTrendResponse,
  QualityTrend,
  FixResultResponse,
  FixResult,
  QualityCategory,
} from '../types/data-quality-types';
import {
  transformQualityReport,
  transformQualityTrend,
  transformFixResult,
} from '../types/data-quality-types';

const BASE_PATH = '/data-quality';

/**
 * Get full data quality report
 */
export async function getQualityReport(): Promise<QualityReport> {
  const response = await apiClient.get<QualityReportResponse>(BASE_PATH);
  return transformQualityReport(response.data);
}

/**
 * Get quality trend over time
 * @param months - Number of months to include (default: 6)
 */
export async function getQualityTrend(months: number = 6): Promise<QualityTrend> {
  const response = await apiClient.get<QualityTrendResponse>(`${BASE_PATH}/trend`, {
    params: { months },
  });
  return transformQualityTrend(response.data);
}

/**
 * Execute cleanup action for a specific category
 * @param category - Quality issue category to fix
 */
export async function fixQualityIssue(
  category: QualityCategory
): Promise<FixResult> {
  const response = await apiClient.post<FixResultResponse>(
    `${BASE_PATH}/${category}/fix`
  );
  return transformFixResult(response.data);
}

// Export all functions as a service object
export const dataQualityApi = {
  getQualityReport,
  getQualityTrend,
  fixQualityIssue,
};
