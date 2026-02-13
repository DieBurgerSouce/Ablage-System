/**
 * Digital Twin API Service
 *
 * Handles all API calls for the Digital Twin feature.
 */

import { apiClient } from '@/lib/api/client';
import type {
  DigitalTwinResponse,
  DigitalTwin,
  FinancialHealthResponse,
  FinancialHealth,
  RiskOverviewResponse,
  RiskOverview,
  DocumentPipelineResponse,
  DocumentPipeline,
  ComplianceResponse,
  Compliance,
  KeyMetricsResponse,
  KeyMetrics,
  TrendsResponse,
  Trends,
} from '../types/digital-twin-types';
import {
  transformDigitalTwin,
  transformFinancialHealth,
  transformRiskOverview,
  transformDocumentPipeline,
  transformCompliance,
  transformKeyMetrics,
  transformTrends,
} from '../types/digital-twin-types';

const BASE_PATH = '/digital-twin';

/**
 * Get full 360-degree digital twin snapshot
 */
export async function getDigitalTwin(): Promise<DigitalTwin> {
  const response = await apiClient.get<DigitalTwinResponse>(BASE_PATH);
  return transformDigitalTwin(response.data);
}

/**
 * Get financial health section only
 */
export async function getFinancialHealth(): Promise<FinancialHealth> {
  const response = await apiClient.get<FinancialHealthResponse>(
    `${BASE_PATH}/financial_health`
  );
  return transformFinancialHealth(response.data);
}

/**
 * Get risk overview section only
 */
export async function getRiskOverview(): Promise<RiskOverview> {
  const response = await apiClient.get<RiskOverviewResponse>(
    `${BASE_PATH}/risk_overview`
  );
  return transformRiskOverview(response.data);
}

/**
 * Get document pipeline section only
 */
export async function getDocumentPipeline(): Promise<DocumentPipeline> {
  const response = await apiClient.get<DocumentPipelineResponse>(
    `${BASE_PATH}/document_pipeline`
  );
  return transformDocumentPipeline(response.data);
}

/**
 * Get compliance section only
 */
export async function getCompliance(): Promise<Compliance> {
  const response = await apiClient.get<ComplianceResponse>(
    `${BASE_PATH}/compliance`
  );
  return transformCompliance(response.data);
}

/**
 * Get key metrics section only
 */
export async function getKeyMetrics(): Promise<KeyMetrics> {
  const response = await apiClient.get<KeyMetricsResponse>(
    `${BASE_PATH}/key_metrics`
  );
  return transformKeyMetrics(response.data);
}

/**
 * Get trends section only
 */
export async function getTrends(): Promise<Trends> {
  const response = await apiClient.get<TrendsResponse>(`${BASE_PATH}/trends`);
  return transformTrends(response.data);
}

// Export all functions as a service object
export const digitalTwinApi = {
  getDigitalTwin,
  getFinancialHealth,
  getRiskOverview,
  getDocumentPipeline,
  getCompliance,
  getKeyMetrics,
  getTrends,
};
