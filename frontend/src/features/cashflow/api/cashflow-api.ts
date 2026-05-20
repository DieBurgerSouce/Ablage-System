/**
 * Predictive Cash-Flow API Client
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface PaymentPrediction {
  invoice_id: string;
  predicted_date: string;
  predicted_days: number;
  confidence: number;
  delay_probability: number;
  factors: Record<string, number | string>;
}

export interface ForecastDay {
  date: string;
  inflows: number;
  outflows: number;
  net_flow: number;
  balance: number;
  is_warning: boolean;
  is_critical: boolean;
}

export interface LiquidityWarning {
  type: 'warning' | 'critical';
  date: string;
  message: string;
}

export interface LiquidityForecast {
  company_id: string;
  forecast_days: number;
  current_balance: number;
  min_balance: number;
  min_balance_date: string;
  total_expected_inflows: number;
  total_expected_outflows: number;
  forecast: ForecastDay[];
  warnings: LiquidityWarning[];
  currency: string;
}

export interface PaymentRecommendation {
  invoice_id: string;
  invoice_number: string | null;
  amount: number;
  due_date: string | null;
  days_until_due: number;
  urgency: 'low' | 'medium' | 'high' | 'critical' | 'overdue';
  recommendation: 'normal' | 'pay_early' | 'pay_soon' | 'pay_immediately';
  reason: string;
  skonto_savings: number;
  skonto_deadline: string | null;
}

export interface ScenarioRequest {
  scenario_type: 'delayed_payments' | 'large_expense' | 'revenue_drop';
  parameters: Record<string, unknown>;
}

export interface ScenarioResponse {
  scenario_type: string;
  parameters: Record<string, unknown>;
  base_min_balance: number;
  scenario_min_balance: number;
  forecast: ForecastDay[];
  impact: 'positive' | 'negative' | 'neutral';
}

export interface CashflowSummary {
  current_balance: number;
  min_balance_7d: number;
  min_balance_30d: number;
  expected_inflows_7d: number;
  expected_outflows_7d: number;
  warnings_count: number;
  urgent_payments: number;
  potential_skonto_savings: number;
  currency: string;
  status: 'healthy' | 'warning' | 'critical';
}

// ==================== API Functions ====================

export async function getLiquidityForecast(days: number = 30): Promise<LiquidityForecast> {
  const response = await apiClient.get<LiquidityForecast>(`/cashflow/forecast?days=${days}`);
  return response.data;
}

export async function predictPayment(invoiceId: string): Promise<PaymentPrediction> {
  const response = await apiClient.get<PaymentPrediction>(`/cashflow/predict/${invoiceId}`);
  return response.data;
}

export async function getPaymentRecommendations(): Promise<PaymentRecommendation[]> {
  const response = await apiClient.get<PaymentRecommendation[]>('/cashflow/recommendations');
  return response.data;
}

export async function runScenario(request: ScenarioRequest): Promise<ScenarioResponse> {
  const response = await apiClient.post<ScenarioResponse>('/cashflow/scenario', request);
  return response.data;
}

export async function getCashflowSummary(): Promise<CashflowSummary> {
  const response = await apiClient.get<CashflowSummary>('/cashflow/summary');
  return response.data;
}
