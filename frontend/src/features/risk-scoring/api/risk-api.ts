/**
 * Risk Scoring API Layer
 *
 * API-Funktionen für das Risk Scoring System.
 */

import { apiClient } from '@/lib/api/client';
import type {
  EntityRiskResponse,
  RiskCalculationResponse,
  BatchCalculationResponse,
  RiskStatisticsResponse,
  EntityRisk,
  RiskCalculation,
  BatchCalculation,
  RiskStatistics,
  RiskFilter,
  EntityType,
} from '../types/risk-types';
import {
  transformEntityRisk,
  transformRiskStatistics,
} from '../types/risk-types';

// Error class for Risk API
export class RiskApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public code?: string
  ) {
    super(message);
    this.name = 'RiskApiError';
  }
}

// API Response wrapper
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

/**
 * Risk Scoring Service
 */
export const riskService = {
  /**
   * Get risk score for a single entity
   */
  async getEntityRisk(entityId: string): Promise<EntityRisk> {
    try {
      const response = await apiClient.get<EntityRiskResponse>(
        `/entities/${entityId}/risk`
      );
      return transformEntityRisk(response);
    } catch (error) {
      throw new RiskApiError(
        'Fehler beim Laden des Risiko-Scores',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Recalculate risk score for a single entity
   */
  async calculateEntityRisk(entityId: string): Promise<RiskCalculation> {
    try {
      const response = await apiClient.post<RiskCalculationResponse>(
        `/entities/${entityId}/risk/calculate`
      );
      return {
        entityId: response.entity_id,
        riskScore: response.risk_score,
        riskFactors: response.risk_factors.map((f) => ({
          name: f.name as RiskCalculation['riskFactors'][0]['name'],
          value: f.value,
          weight: f.weight,
          contribution: f.contribution,
          rawValue: f.raw_value,
        })),
        calculatedAt: new Date(response.calculated_at),
      };
    } catch (error) {
      throw new RiskApiError(
        'Fehler bei der Neuberechnung des Risiko-Scores',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Recalculate all risk scores (batch)
   */
  async calculateAllRisks(params?: {
    entityType?: EntityType;
    limit?: number;
  }): Promise<BatchCalculation> {
    try {
      const response = await apiClient.post<BatchCalculationResponse>(
        '/entities/risk/calculate-all',
        {
          entity_type: params?.entityType,
          limit: params?.limit,
        }
      );
      return {
        processed: response.processed,
        updated: response.updated,
        errors: response.errors,
        durationSeconds: response.duration_seconds,
      };
    } catch (error) {
      throw new RiskApiError(
        'Fehler bei der Batch-Neuberechnung',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get high-risk entities list
   */
  async getHighRiskEntities(filter?: RiskFilter): Promise<{
    entities: EntityRisk[];
    total: number;
    page: number;
    perPage: number;
    pages: number;
  }> {
    try {
      const params = new URLSearchParams();

      if (filter?.entityType) {
        params.append('entity_type', filter.entityType);
      }
      if (filter?.riskLevel) {
        params.append('risk_level', filter.riskLevel);
      }
      if (filter?.minScore !== undefined) {
        params.append('min_score', filter.minScore.toString());
      }
      if (filter?.maxScore !== undefined) {
        params.append('max_score', filter.maxScore.toString());
      }
      if (filter?.sortBy) {
        params.append('sort_by', filter.sortBy);
      }
      if (filter?.sortOrder) {
        params.append('sort_order', filter.sortOrder);
      }
      if (filter?.page) {
        params.append('page', filter.page.toString());
      }
      if (filter?.perPage) {
        params.append('per_page', filter.perPage.toString());
      }

      // Default: high-risk threshold (>= 50)
      if (!filter?.minScore && !filter?.riskLevel) {
        params.append('min_score', '50');
      }

      const response = await apiClient.get<PaginatedResponse<EntityRiskResponse>>(
        `/entities/risk/high-risk?${params.toString()}`
      );

      return {
        entities: response.items.map(transformEntityRisk),
        total: response.total,
        page: response.page,
        perPage: response.per_page,
        pages: response.pages,
      };
    } catch (error) {
      throw new RiskApiError(
        'Fehler beim Laden der Hoch-Risiko Entities',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get all entities with risk scores
   */
  async getAllEntitiesWithRisk(filter?: RiskFilter): Promise<{
    entities: EntityRisk[];
    total: number;
    page: number;
    perPage: number;
    pages: number;
  }> {
    try {
      const params = new URLSearchParams();

      if (filter?.entityType) {
        params.append('entity_type', filter.entityType);
      }
      if (filter?.riskLevel) {
        params.append('risk_level', filter.riskLevel);
      }
      if (filter?.minScore !== undefined) {
        params.append('min_score', filter.minScore.toString());
      }
      if (filter?.maxScore !== undefined) {
        params.append('max_score', filter.maxScore.toString());
      }
      if (filter?.sortBy) {
        params.append('sort_by', filter.sortBy);
      }
      if (filter?.sortOrder) {
        params.append('sort_order', filter.sortOrder);
      }
      if (filter?.page) {
        params.append('page', filter.page.toString());
      }
      if (filter?.perPage) {
        params.append('per_page', filter.perPage.toString());
      }

      const response = await apiClient.get<PaginatedResponse<EntityRiskResponse>>(
        `/entities/risk?${params.toString()}`
      );

      return {
        entities: response.items.map(transformEntityRisk),
        total: response.total,
        page: response.page,
        perPage: response.per_page,
        pages: response.pages,
      };
    } catch (error) {
      throw new RiskApiError(
        'Fehler beim Laden der Risiko-Daten',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get risk statistics
   */
  async getRiskStatistics(entityType?: EntityType): Promise<RiskStatistics> {
    try {
      const params = entityType ? `?entity_type=${entityType}` : '';
      const response = await apiClient.get<RiskStatisticsResponse>(
        `/entities/risk/statistics${params}`
      );
      return transformRiskStatistics(response);
    } catch (error) {
      throw new RiskApiError(
        'Fehler beim Laden der Risiko-Statistiken',
        error instanceof Error ? undefined : 500
      );
    }
  },

  /**
   * Get risk trend for an entity
   */
  async getEntityRiskTrend(
    entityId: string,
    days: number = 30
  ): Promise<Array<{ date: Date; score: number }>> {
    try {
      const response = await apiClient.get<
        Array<{ date: string; risk_score: number }>
      >(`/entities/${entityId}/risk/trend?days=${days}`);

      return response.map((item) => ({
        date: new Date(item.date),
        score: item.risk_score,
      }));
    } catch (error) {
      throw new RiskApiError(
        'Fehler beim Laden des Risiko-Trends',
        error instanceof Error ? undefined : 500
      );
    }
  },
};
