/**
 * Dashboard Widgets API Service
 *
 * API-Funktionen fuer Dashboard-Widget-Daten:
 * - Cash-Flow Forecast (30/60/90 Tage Prognose)
 * - Supplier Performance (Lieferanten-Metriken)
 * - Customer Lifetime Value (Kundenwert-Analyse)
 *
 * Phase 7: Dashboard Widgets (Januar 2026)
 */

import { apiClient } from '@/lib/api/client';

const BASE_URL = '/dashboard-widgets';

// =============================================================================
// Types - Cash-Flow Forecast
// =============================================================================

export interface ForecastDataPoint {
  date: string;
  income: number;
  expenses: number;
  net: number;
  balance: number;
  confidence: number;
}

export interface PeriodForecast {
  periodDays: number;
  totalIncome: number;
  totalExpenses: number;
  netFlow: number;
  endingBalance: number;
  confidenceScore: number;
  incomeInvoiceCount: number;
  expenseInvoiceCount: number;
}

export interface SkontoImpact {
  invoiceCount: number;
  potentialSavings: number;
}

export interface CashFlowForecastData {
  generatedAt: string;
  currentBalance: number;
  forecast30: PeriodForecast;
  forecast60: PeriodForecast;
  forecast90: PeriodForecast;
  dailyData: ForecastDataPoint[];
  skontoImpact: SkontoImpact;
  riskWarning: string | null;
}

// =============================================================================
// Types - Supplier Performance
// =============================================================================

export interface SupplierMetrics {
  id: string;
  name: string;
  punctuality: number;
  accuracy: number;
  orders: number;
  volume: number;
  priceTrend: number;
  trendDirection: 'up' | 'down' | 'stable';
}

export interface PriceTrendData {
  period: string;
  change: number;
  orders: number;
}

export interface SupplierPerformanceData {
  generatedAt: string;
  periodDays: number;
  overallPunctuality: number;
  overallAccuracy: number;
  totalSuppliers: number;
  activeSuppliers: number;
  avgPriceChange: number;
  topSuppliers: SupplierMetrics[];
  priceTrendData: PriceTrendData[];
  criticalCount: number;
}

// =============================================================================
// Types - Customer LTV
// =============================================================================

export interface CustomerMetrics {
  id: string;
  name: string;
  ltv: number;
  orders: number;
  avgOrder: number;
  trend: 'growing' | 'stable' | 'declining';
  trendPct: number;
  churnRisk: 'low' | 'medium' | 'high' | 'critical';
  churnScore: number;
  daysSinceOrder: number;
}

export interface AtRiskCustomer {
  id: string;
  name: string;
  ltv: number;
  churnRisk: 'low' | 'medium' | 'high' | 'critical';
  churnScore: number;
  daysSinceOrder: number;
}

export interface TrendDataPoint {
  period: string;
  revenue: number;
  customers: number;
  avgOrder: number;
}

export interface CustomerLTVData {
  generatedAt: string;
  periodDays: number;
  totalCustomers: number;
  activeCustomers: number;
  totalLTV: number;
  avgLTV: number;
  avgChurnRisk: number;
  overallTrend: 'growing' | 'stable' | 'declining';
  trendPercentage: number;
  topCustomers: CustomerMetrics[];
  atRiskCustomers: AtRiskCustomer[];
  trendData: TrendDataPoint[];
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Hole Cash-Flow Prognose-Daten
 */
export async function getCashFlowForecast(
  startingBalance?: number
): Promise<CashFlowForecastData> {
  const params = new URLSearchParams();
  if (startingBalance !== undefined) {
    params.append('starting_balance', startingBalance.toString());
  }

  const url = `${BASE_URL}/cash-flow-forecast${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await apiClient.get<CashFlowForecastData>(url);
  return response.data;
}

/**
 * Hole Cash-Flow Chart-Daten
 */
export async function getCashFlowChartData(
  days: number = 30
): Promise<ForecastDataPoint[]> {
  const response = await apiClient.get<ForecastDataPoint[]>(
    `${BASE_URL}/cash-flow-forecast/chart`,
    { params: { days } }
  );
  return response.data;
}

/**
 * Hole Lieferanten-Performance-Daten
 */
export async function getSupplierPerformance(
  periodDays: number = 90
): Promise<SupplierPerformanceData> {
  const response = await apiClient.get<SupplierPerformanceData>(
    `${BASE_URL}/supplier-performance`,
    { params: { period_days: periodDays } }
  );
  return response.data;
}

/**
 * Hole Customer LTV-Daten
 */
export async function getCustomerLTV(
  periodDays: number = 365
): Promise<CustomerLTVData> {
  const response = await apiClient.get<CustomerLTVData>(
    `${BASE_URL}/customer-ltv`,
    { params: { period_days: periodDays } }
  );
  return response.data;
}

// =============================================================================
// Types - Revenue Trend
// =============================================================================

export interface RevenueTrendDataPoint {
  period: string;
  revenue: number;
  expense: number;
  net: number;
  documentCount: number;
  category: string;
}

export interface RevenueTrendData {
  generatedAt: string;
  dateFrom: string;
  dateTo: string;
  totalRevenue: number;
  totalExpenses: number;
  netIncome: number;
  dataPoints: RevenueTrendDataPoint[];
  comparison?: {
    revenueChangePct: number;
    expenseChangePct: number;
    previousFrom: string;
    previousTo: string;
  } | null;
}

// =============================================================================
// Types - DSO Tracker
// =============================================================================

export interface DSOTrackerData {
  generatedAt: string;
  currentDSO: number;
  previousDSO: number;
  industryBenchmark: number;
  trend: { period: string; dso: number }[];
  rating: 'gut' | 'mittel' | 'schlecht';
}

// =============================================================================
// Types - Margin Analyzer
// =============================================================================

export interface MarginDataPoint {
  category: string;
  revenue: number;
  cost: number;
  margin: number;
  marginPct: number;
}

export interface MarginAnalyzerData {
  generatedAt: string;
  overallMargin: number;
  overallMarginPct: number;
  dataPoints: MarginDataPoint[];
}

// =============================================================================
// API Functions - Business KPIs (Phase C)
// =============================================================================

/**
 * Hole Umsatzentwicklungs-Daten
 */
export async function getRevenueTrend(
  dateFrom?: string,
  dateTo?: string,
  comparePeriod?: string,
): Promise<RevenueTrendData> {
  const params = new URLSearchParams();
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  if (comparePeriod) params.append('compare_period', comparePeriod);
  const url = `${BASE_URL}/revenue-trend${params.toString() ? `?${params}` : ''}`;
  const response = await apiClient.get<RevenueTrendData>(url);
  return response.data;
}

/**
 * Hole DSO-Tracker-Daten
 */
export async function getDSOTracker(
  dateFrom?: string,
  dateTo?: string,
): Promise<DSOTrackerData> {
  const params = new URLSearchParams();
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  const response = await apiClient.get<DSOTrackerData>(
    `${BASE_URL}/dso-tracker${params.toString() ? `?${params}` : ''}`,
  );
  return response.data;
}

/**
 * Hole Margenanalyse-Daten
 */
export async function getMarginAnalyzer(
  dateFrom?: string,
  dateTo?: string,
): Promise<MarginAnalyzerData> {
  const params = new URLSearchParams();
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  const response = await apiClient.get<MarginAnalyzerData>(
    `${BASE_URL}/margin-analyzer${params.toString() ? `?${params}` : ''}`,
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const dashboardWidgetKeys = {
  all: ['dashboard-widgets'] as const,
  cashFlowForecast: () => [...dashboardWidgetKeys.all, 'cash-flow-forecast'] as const,
  cashFlowChart: (days: number) =>
    [...dashboardWidgetKeys.all, 'cash-flow-chart', days] as const,
  supplierPerformance: (periodDays: number) =>
    [...dashboardWidgetKeys.all, 'supplier-performance', periodDays] as const,
  customerLTV: (periodDays: number) =>
    [...dashboardWidgetKeys.all, 'customer-ltv', periodDays] as const,
  revenueTrend: (from?: string, to?: string) =>
    [...dashboardWidgetKeys.all, 'revenue-trend', from, to] as const,
  dsoTracker: (from?: string, to?: string) =>
    [...dashboardWidgetKeys.all, 'dso-tracker', from, to] as const,
  marginAnalyzer: (from?: string, to?: string) =>
    [...dashboardWidgetKeys.all, 'margin-analyzer', from, to] as const,
};

// =============================================================================
// German Labels
// =============================================================================

export const DASHBOARD_LABELS = {
  cashFlowForecast: 'Liquiditaetsprognose',
  income: 'Einnahmen',
  expenses: 'Ausgaben',
  balance: 'Saldo',
  supplierPerformance: 'Lieferanten-Performance',
  punctuality: 'Puenktlichkeit',
  accuracy: 'Genauigkeit',
  priceTrend: 'Preistrend',
  customerValue: 'Kundenwert',
  revenue: 'Umsatz',
  trend: 'Trend',
  churnRisk: 'Churn-Risiko',
  days: 'Tage',
  forecast: 'Prognose',
  // Trend labels
  growing: 'Wachsend',
  stable: 'Stabil',
  declining: 'Ruecklaeufig',
  // Churn risk labels
  low: 'Niedrig',
  medium: 'Mittel',
  high: 'Hoch',
  critical: 'Kritisch',
} as const;

/**
 * Formatiere Trend-Label (Deutsch)
 */
export function formatTrendLabel(trend: 'growing' | 'stable' | 'declining' | 'up' | 'down'): string {
  const labels: Record<string, string> = {
    growing: 'Wachsend',
    stable: 'Stabil',
    declining: 'Ruecklaeufig',
    up: 'Steigend',
    down: 'Fallend',
  };
  return labels[trend] || trend;
}

/**
 * Formatiere Churn-Risiko-Label (Deutsch)
 */
export function formatChurnRiskLabel(risk: 'low' | 'medium' | 'high' | 'critical'): string {
  const labels: Record<string, string> = {
    low: 'Niedrig',
    medium: 'Mittel',
    high: 'Hoch',
    critical: 'Kritisch',
  };
  return labels[risk] || risk;
}
