/**
 * Predictive Intelligence Types
 *
 * Typdefinitionen fuer KI-basierte Vorhersagen:
 * Cashflow, Zahlungen, System-Gesundheit, Alerts.
 */

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
  type: string;
  date: string;
  message: string;
}

export interface CashflowForecast {
  forecast_days: ForecastDay[];
  warnings: LiquidityWarning[];
  generated_at: string;
}

export interface PaymentPrediction {
  invoice_id: string;
  entity_name?: string;
  predicted_date: string;
  predicted_days: number;
  confidence: number;
  delay_probability: number;
  factors: Record<string, number>;
}

export interface SystemHealthMetric {
  metric: string;
  current_value: number;
  predicted_value: number;
  threshold: number;
  eta_minutes: number | null;
  severity: 'normal' | 'warning' | 'critical';
}

export interface PredictiveAlert {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  recommendation: string;
  eta_minutes: number | null;
  confidence: number;
  source: string;
  created_at: string;
  acknowledged: boolean;
}

export type ForecastPeriod = '30' | '60' | '90';
