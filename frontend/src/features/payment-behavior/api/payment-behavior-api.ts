/**
 * Payment Behavior API Service
 *
 * API-Service für Zahlungsverhaltens-Analyse.
 */

import { apiClient } from '@/lib/api/client';
import type {
  PaymentMetricsApiResponse,
  PaymentBehaviorReportApiResponse,
  CategoryDistributionApiResponse,
  PaymentMetrics,
  PaymentBehaviorReport,
  CategoryDistribution,
} from '../types/payment-behavior-types';
import {
  transformPaymentMetrics,
  transformPaymentBehaviorReport,
  transformCategoryDistribution,
} from '../types/payment-behavior-types';

const BASE_URL = '/api/v1/payment-behavior';

/**
 * Payment Behavior API Error
 */
export class PaymentBehaviorApiError extends Error {
  statusCode?: number;
  details?: unknown;

  constructor(message: string, statusCode?: number, details?: unknown) {
    super(message);
    this.name = 'PaymentBehaviorApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

/**
 * Payment Behavior Service
 */
export const paymentBehaviorService = {
  /**
   * Analysiert Zahlungsverhalten eines einzelnen Kunden.
   */
  async getCustomerPaymentBehavior(
    entityId: string,
    periodDays = 365
  ): Promise<PaymentMetrics> {
    try {
      const response = await apiClient.get<PaymentMetricsApiResponse>(
        `${BASE_URL}/${entityId}`,
        { params: { period_days: periodDays } }
      );
      return transformPaymentMetrics(response.data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      throw new PaymentBehaviorApiError(
        err.response?.data?.detail || 'Fehler beim Laden des Zahlungsverhaltens',
        err.response?.status,
        error
      );
    }
  },

  /**
   * Erstellt Gesamtreport über alle Kunden.
   */
  async getPaymentBehaviorReport(
    periodDays = 365,
    topN = 10
  ): Promise<PaymentBehaviorReport> {
    try {
      const response = await apiClient.get<PaymentBehaviorReportApiResponse>(
        BASE_URL,
        { params: { period_days: periodDays, top_n: topN } }
      );
      return transformPaymentBehaviorReport(response.data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      throw new PaymentBehaviorApiError(
        err.response?.data?.detail || 'Fehler beim Laden des Reports',
        err.response?.status,
        error
      );
    }
  },

  /**
   * Ruft Kunden-Ranking nach Zahlungsverhalten ab.
   */
  async getCustomerRanking(
    periodDays = 365,
    limit = 50,
    sortBy = 'payment_score',
    sortDesc = true
  ): Promise<PaymentMetrics[]> {
    try {
      const response = await apiClient.get<PaymentMetricsApiResponse[]>(
        `${BASE_URL}/ranking/list`,
        {
          params: {
            period_days: periodDays,
            limit,
            sort_by: sortBy,
            sort_desc: sortDesc,
          },
        }
      );
      return response.data.map(transformPaymentMetrics);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      throw new PaymentBehaviorApiError(
        err.response?.data?.detail || 'Fehler beim Laden des Rankings',
        err.response?.status,
        error
      );
    }
  },

  /**
   * Ruft Kategorien-Verteilung ab.
   */
  async getCategoryDistribution(periodDays = 365): Promise<CategoryDistribution> {
    try {
      const response = await apiClient.get<CategoryDistributionApiResponse>(
        `${BASE_URL}/categories/distribution`,
        { params: { period_days: periodDays } }
      );
      return transformCategoryDistribution(response.data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      throw new PaymentBehaviorApiError(
        err.response?.data?.detail || 'Fehler beim Laden der Kategorien',
        err.response?.status,
        error
      );
    }
  },
};
