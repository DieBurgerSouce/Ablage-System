/**
 * Payment Behavior Types
 *
 * TypeScript Types fuer Zahlungsverhaltens-Analyse.
 */

// =============================================================================
// Enums & Constants
// =============================================================================

export type PaymentBehaviorCategory =
  | 'excellent'
  | 'punctual'
  | 'delayed'
  | 'problematic'
  | 'defaulter';

export type PaymentTrend = 'improving' | 'stable' | 'declining';

export const BEHAVIOR_CATEGORY_LABELS: Record<PaymentBehaviorCategory, string> = {
  excellent: 'Exzellent',
  punctual: 'Puenktlich',
  delayed: 'Verzoegert',
  problematic: 'Problematisch',
  defaulter: 'Zahlungsausfall',
};

export const BEHAVIOR_CATEGORY_DESCRIPTIONS: Record<PaymentBehaviorCategory, string> = {
  excellent: 'Zahlt vor Faelligkeit, nutzt Skonto optimal',
  punctual: 'Zahlt innerhalb der Zahlungsfrist',
  delayed: '1-14 Tage nach Faelligkeit',
  problematic: 'Haeufig stark verzoegert (>30%)',
  defaulter: 'Regelmaessige Ausfaelle (>90 Tage)',
};

export const BEHAVIOR_CATEGORY_COLORS: Record<
  PaymentBehaviorCategory,
  { bg: string; text: string; border: string; icon: string }
> = {
  excellent: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
    text: 'text-emerald-700 dark:text-emerald-400',
    border: 'border-emerald-300 dark:border-emerald-700',
    icon: '🌟',
  },
  punctual: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    border: 'border-green-300 dark:border-green-700',
    icon: '✅',
  },
  delayed: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
    border: 'border-yellow-300 dark:border-yellow-700',
    icon: '⏳',
  },
  problematic: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    border: 'border-orange-300 dark:border-orange-700',
    icon: '⚠️',
  },
  defaulter: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-300 dark:border-red-700',
    icon: '🚫',
  },
};

export const PAYMENT_TREND_LABELS: Record<PaymentTrend, string> = {
  improving: 'Verbessernd',
  stable: 'Stabil',
  declining: 'Verschlechternd',
};

export const PAYMENT_TREND_COLORS: Record<PaymentTrend, { text: string; bg: string }> = {
  improving: {
    text: 'text-green-600 dark:text-green-400',
    bg: 'bg-green-100 dark:bg-green-900/30',
  },
  stable: {
    text: 'text-gray-600 dark:text-gray-400',
    bg: 'bg-gray-100 dark:bg-gray-900/30',
  },
  declining: {
    text: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/30',
  },
};

// =============================================================================
// API Response Types (snake_case)
// =============================================================================

export interface PaymentMetricsApiResponse {
  entity_id: string;
  entity_name: string;
  total_invoices: number;
  paid_invoices: number;
  unpaid_invoices: number;
  overdue_invoices: number;
  total_volume: number;
  paid_volume: number;
  outstanding_volume: number;
  overdue_volume: number;
  avg_payment_days: number;
  min_payment_days: number;
  max_payment_days: number;
  median_payment_days: number;
  punctuality_rate: number;
  early_payment_rate: number;
  late_payment_rate: number;
  default_rate: number;
  skonto_utilization_rate: number;
  skonto_saved: number;
  behavior_category: PaymentBehaviorCategory;
  behavior_category_label: string;
  payment_trend: PaymentTrend;
  payment_trend_label: string;
  payment_score: number;
  first_invoice_date: string | null;
  last_invoice_date: string | null;
  analysis_period_days: number;
}

export interface PaymentBehaviorSummaryApiResponse {
  excellent_count: number;
  punctual_count: number;
  delayed_count: number;
  problematic_count: number;
  defaulter_count: number;
  avg_payment_days_overall: number;
  avg_punctuality_rate: number;
  avg_payment_score: number;
  volume_at_risk: number;
  overdue_total: number;
  improving_count: number;
  stable_count: number;
  declining_count: number;
}

export interface PaymentBehaviorReportApiResponse {
  company_id: string;
  total_customers: number;
  analyzed_customers: number;
  summary: PaymentBehaviorSummaryApiResponse;
  top_payers: PaymentMetricsApiResponse[];
  worst_payers: PaymentMetricsApiResponse[];
  improving_customers: PaymentMetricsApiResponse[];
  declining_customers: PaymentMetricsApiResponse[];
  high_risk_customers: PaymentMetricsApiResponse[];
  analysis_period_start: string;
  analysis_period_end: string;
  benchmark_avg_payment_days: number;
  benchmark_punctuality_rate: number;
  generated_at: string;
}

export interface CategoryDistributionApiResponse {
  excellent: number;
  punctual: number;
  delayed: number;
  problematic: number;
  defaulter: number;
}

// =============================================================================
// Frontend Types (camelCase)
// =============================================================================

export interface PaymentMetrics {
  entityId: string;
  entityName: string;
  totalInvoices: number;
  paidInvoices: number;
  unpaidInvoices: number;
  overdueInvoices: number;
  totalVolume: number;
  paidVolume: number;
  outstandingVolume: number;
  overdueVolume: number;
  avgPaymentDays: number;
  minPaymentDays: number;
  maxPaymentDays: number;
  medianPaymentDays: number;
  punctualityRate: number;
  earlyPaymentRate: number;
  latePaymentRate: number;
  defaultRate: number;
  skontoUtilizationRate: number;
  skontoSaved: number;
  behaviorCategory: PaymentBehaviorCategory;
  behaviorCategoryLabel: string;
  paymentTrend: PaymentTrend;
  paymentTrendLabel: string;
  paymentScore: number;
  firstInvoiceDate: Date | null;
  lastInvoiceDate: Date | null;
  analysisPeriodDays: number;
}

export interface PaymentBehaviorSummary {
  excellentCount: number;
  punctualCount: number;
  delayedCount: number;
  problematicCount: number;
  defaulterCount: number;
  avgPaymentDaysOverall: number;
  avgPunctualityRate: number;
  avgPaymentScore: number;
  volumeAtRisk: number;
  overdueTotal: number;
  improvingCount: number;
  stableCount: number;
  decliningCount: number;
}

export interface PaymentBehaviorReport {
  companyId: string;
  totalCustomers: number;
  analyzedCustomers: number;
  summary: PaymentBehaviorSummary;
  topPayers: PaymentMetrics[];
  worstPayers: PaymentMetrics[];
  improvingCustomers: PaymentMetrics[];
  decliningCustomers: PaymentMetrics[];
  highRiskCustomers: PaymentMetrics[];
  analysisPeriodStart: Date;
  analysisPeriodEnd: Date;
  benchmarkAvgPaymentDays: number;
  benchmarkPunctualityRate: number;
  generatedAt: Date;
}

export interface CategoryDistribution {
  excellent: number;
  punctual: number;
  delayed: number;
  problematic: number;
  defaulter: number;
  total: number;
}

// =============================================================================
// Transformer Functions
// =============================================================================

export function transformPaymentMetrics(api: PaymentMetricsApiResponse): PaymentMetrics {
  return {
    entityId: api.entity_id,
    entityName: api.entity_name,
    totalInvoices: api.total_invoices,
    paidInvoices: api.paid_invoices,
    unpaidInvoices: api.unpaid_invoices,
    overdueInvoices: api.overdue_invoices,
    totalVolume: api.total_volume,
    paidVolume: api.paid_volume,
    outstandingVolume: api.outstanding_volume,
    overdueVolume: api.overdue_volume,
    avgPaymentDays: api.avg_payment_days,
    minPaymentDays: api.min_payment_days,
    maxPaymentDays: api.max_payment_days,
    medianPaymentDays: api.median_payment_days,
    punctualityRate: api.punctuality_rate,
    earlyPaymentRate: api.early_payment_rate,
    latePaymentRate: api.late_payment_rate,
    defaultRate: api.default_rate,
    skontoUtilizationRate: api.skonto_utilization_rate,
    skontoSaved: api.skonto_saved,
    behaviorCategory: api.behavior_category,
    behaviorCategoryLabel: api.behavior_category_label,
    paymentTrend: api.payment_trend,
    paymentTrendLabel: api.payment_trend_label,
    paymentScore: api.payment_score,
    firstInvoiceDate: api.first_invoice_date ? new Date(api.first_invoice_date) : null,
    lastInvoiceDate: api.last_invoice_date ? new Date(api.last_invoice_date) : null,
    analysisPeriodDays: api.analysis_period_days,
  };
}

export function transformPaymentBehaviorReport(
  api: PaymentBehaviorReportApiResponse
): PaymentBehaviorReport {
  return {
    companyId: api.company_id,
    totalCustomers: api.total_customers,
    analyzedCustomers: api.analyzed_customers,
    summary: {
      excellentCount: api.summary.excellent_count,
      punctualCount: api.summary.punctual_count,
      delayedCount: api.summary.delayed_count,
      problematicCount: api.summary.problematic_count,
      defaulterCount: api.summary.defaulter_count,
      avgPaymentDaysOverall: api.summary.avg_payment_days_overall,
      avgPunctualityRate: api.summary.avg_punctuality_rate,
      avgPaymentScore: api.summary.avg_payment_score,
      volumeAtRisk: api.summary.volume_at_risk,
      overdueTotal: api.summary.overdue_total,
      improvingCount: api.summary.improving_count,
      stableCount: api.summary.stable_count,
      decliningCount: api.summary.declining_count,
    },
    topPayers: api.top_payers.map(transformPaymentMetrics),
    worstPayers: api.worst_payers.map(transformPaymentMetrics),
    improvingCustomers: api.improving_customers.map(transformPaymentMetrics),
    decliningCustomers: api.declining_customers.map(transformPaymentMetrics),
    highRiskCustomers: api.high_risk_customers.map(transformPaymentMetrics),
    analysisPeriodStart: new Date(api.analysis_period_start),
    analysisPeriodEnd: new Date(api.analysis_period_end),
    benchmarkAvgPaymentDays: api.benchmark_avg_payment_days,
    benchmarkPunctualityRate: api.benchmark_punctuality_rate,
    generatedAt: new Date(api.generated_at),
  };
}

export function transformCategoryDistribution(
  api: CategoryDistributionApiResponse
): CategoryDistribution {
  const total =
    api.excellent + api.punctual + api.delayed + api.problematic + api.defaulter;
  return {
    excellent: api.excellent,
    punctual: api.punctual,
    delayed: api.delayed,
    problematic: api.problematic,
    defaulter: api.defaulter,
    total,
  };
}

// =============================================================================
// UI Labels
// =============================================================================

export const UI_LABELS = {
  dashboard: 'Zahlungsverhalten',
  customer: 'Kunde',
  score: 'Payment-Score',
  category: 'Kategorie',
  trend: 'Trend',
  invoices: 'Rechnungen',
  volume: 'Volumen',
  avgDays: 'Durchschn. Zahldauer',
  punctuality: 'Puenktlichkeit',
  skonto: 'Skonto-Nutzung',
  overdue: 'Ueberfaellig',
  topPayers: 'Beste Zahler',
  worstPayers: 'Schlechteste Zahler',
  improving: 'Verbessernd',
  declining: 'Verschlechternd',
  highRisk: 'Risiko-Kunden',
  benchmark: 'Benchmark',
  noData: 'Keine Daten verfuegbar',
};
