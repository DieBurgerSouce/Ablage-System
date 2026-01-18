/**
 * Supplier Ranking API Layer
 *
 * API-Funktionen fuer das Lieferanten-Ranking System.
 */

import { apiClient } from '@/lib/api/client';
import type {
  SupplierRankingResponse,
  SupplierRankingReportResponse,
  TierDistributionResponse,
  SupplierRanking,
  SupplierRankingReport,
  TierDistribution,
} from '../types/supplier-ranking-types';
import {
  transformSupplierRanking,
  transformSupplierRankingReport,
} from '../types/supplier-ranking-types';

// Error class for Supplier Ranking API
export class SupplierRankingApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public code?: string
  ) {
    super(message);
    this.name = 'SupplierRankingApiError';
  }
}

/**
 * Supplier Ranking Service
 */
export const supplierRankingService = {
  /**
   * Get ranking for a single supplier
   */
  async getSupplierRanking(
    entityId: string,
    periodDays = 365
  ): Promise<SupplierRanking> {
    try {
      const response = await apiClient.get<SupplierRankingResponse>(
        `/supplier-ranking/${entityId}?period_days=${periodDays}`
      );
      return transformSupplierRanking(response);
    } catch (error) {
      throw new SupplierRankingApiError(
        'Fehler beim Laden des Lieferanten-Rankings',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get full supplier ranking report
   */
  async getSupplierRankingReport(
    periodDays = 365,
    topN = 10
  ): Promise<SupplierRankingReport> {
    try {
      const response = await apiClient.get<SupplierRankingReportResponse>(
        `/supplier-ranking?period_days=${periodDays}&top_n=${topN}`
      );
      return transformSupplierRankingReport(response);
    } catch (error) {
      throw new SupplierRankingApiError(
        'Fehler beim Laden des Ranking-Reports',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Compare multiple suppliers
   */
  async compareSuppliers(
    entityIds: string[],
    periodDays = 365
  ): Promise<SupplierRanking[]> {
    try {
      const response = await apiClient.post<SupplierRankingResponse[]>(
        '/supplier-ranking/compare',
        {
          entity_ids: entityIds,
          period_days: periodDays,
        }
      );
      return response.map(transformSupplierRanking);
    } catch (error) {
      throw new SupplierRankingApiError(
        'Fehler beim Vergleichen der Lieferanten',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get tier distribution
   */
  async getTierDistribution(periodDays = 365): Promise<TierDistribution> {
    try {
      const response = await apiClient.get<TierDistributionResponse>(
        `/supplier-ranking/tiers/distribution?period_days=${periodDays}`
      );
      return response;
    } catch (error) {
      throw new SupplierRankingApiError(
        'Fehler beim Laden der Tier-Verteilung',
        error instanceof Error ? undefined : 500
      );
    }
  },
};
