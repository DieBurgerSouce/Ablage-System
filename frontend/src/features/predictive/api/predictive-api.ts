/**
 * Predictive API Client
 *
 * API-Anbindung fuer Vorhersage-Endpunkte:
 * - Cashflow-Prognose
 * - Zahlungsempfehlungen
 * - System-Gesundheitsvorhersagen
 * - Proaktive Alerts
 */

import { apiClient } from '@/lib/api/client';
import type {
  CashflowForecast,
  PaymentPrediction,
  SystemHealthMetric,
  PredictiveAlert,
  ForecastPeriod,
} from '../types/predictive-types';

const CASHFLOW_PATH = '/cashflow';
const HEALTH_PATH = '/health/predictions';

export async function getCashflowForecast(
  days: ForecastPeriod = '30',
): Promise<CashflowForecast> {
  const response = await apiClient.get<CashflowForecast>(
    `${CASHFLOW_PATH}/forecast`,
    { params: { days } },
  );
  return response.data;
}

export async function getPaymentPredictions(): Promise<PaymentPrediction[]> {
  const response = await apiClient.get<PaymentPrediction[]>(
    `${CASHFLOW_PATH}/recommendations`,
  );
  return response.data;
}

export async function getSystemHealthPredictions(): Promise<
  SystemHealthMetric[]
> {
  const response = await apiClient.get<SystemHealthMetric[]>(HEALTH_PATH);
  return response.data;
}

export async function getPredictiveAlerts(): Promise<PredictiveAlert[]> {
  const response = await apiClient.get<PredictiveAlert[]>(
    `${HEALTH_PATH}/alerts`,
  );
  return response.data;
}
