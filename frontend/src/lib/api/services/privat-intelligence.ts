/**
 * Privat Intelligence API Service
 *
 * Enterprise-Level Intelligence Features für das Privat-Modul:
 * - Investment Analytics (Performance, Allocation, Diversification, Risk)
 * - Financial Health Score (6 Dimensionen)
 * - Smart Recommendations Engine
 * - Loan Scenario Simulator
 * - Property/Vehicle Intelligence
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';
import type {
  InvestmentPerformance,
  PortfolioAllocation,
  DiversificationScore,
  RiskProfile,
  RebalancingSuggestion,
  InvestmentFullAnalytics,
  NetWorthComponents,
  FinancialHealthScore,
  SmartRecommendationsList,
  ExtraPaymentScenario,
  RefinancingScenario,
  FullAmortizationSchedule,
  LoanComparison,
  PropertyIntelligence,
  VehicleIntelligence,
} from '@/types/privat';

// ==================== Error Class ====================

export class PrivatIntelligenceApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'PrivatIntelligenceApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new PrivatIntelligenceApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new PrivatIntelligenceApiError(`${context}: ${message}`, 400, error);
    }

    throw new PrivatIntelligenceApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new PrivatIntelligenceApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Backend Types ====================

interface InvestmentPerformanceBackend {
  investment_id: string;
  name: string;
  investment_type: string;
  initial_amount: number;
  current_value: number;
  absolute_return: number;
  percentage_return: number;
  annualized_return: number;
  holding_period_days: number;
  holding_period_years: number;
  calculated_at: string;
}

interface PortfolioAllocationBackend {
  space_id: string;
  total_value: number;
  investment_count: number;
  allocation_by_type: Record<string, { value: number; percentage: number; count: number }>;
  top_holdings: Array<{ name: string; value: number; percentage: number }>;
  calculated_at: string;
}

interface DiversificationScoreBackend {
  space_id: string;
  herfindahl_index: number;
  diversification_score: number;
  interpretation: string;
  type_count: number;
  dominant_type: string;
  dominant_type_percentage: number;
  recommendations: string[];
  calculated_at: string;
}

interface RiskProfileBackend {
  space_id: string;
  overall_risk_score: number;
  risk_category: string;
  risk_by_type: Record<string, { allocation: number; risk_level: number; contribution: number }>;
  volatility_estimate: number;
  recommendations: string[];
  calculated_at: string;
}

interface RebalancingSuggestionBackend {
  space_id: string;
  current_allocation: Record<string, number>;
  target_allocation: Record<string, number>;
  rebalance_actions: Array<{
    type: string;
    current_percentage: number;
    target_percentage: number;
    action: string;
    amount_to_adjust: number;
  }>;
  total_adjustment_needed: number;
  calculated_at: string;
}

interface NetWorthBackend {
  space_id: string;
  total_assets: number;
  total_liabilities: number;
  net_worth: number;
  components: {
    properties: { count: number; value: number };
    vehicles: { count: number; value: number };
    investments: { count: number; value: number };
    loans: { count: number; outstanding: number };
  };
  asset_allocation: Record<string, { value: number; percentage: number }>;
  calculated_at: string;
}

interface HealthDimensionBackend {
  score: number;
  weight: number;
  contribution: number;
  interpretation: string;
  recommendations: string[];
}

interface FinancialHealthBackend {
  space_id: string;
  overall_score: number;
  grade: string;
  dimensions: {
    net_worth_trend: HealthDimensionBackend;
    debt_management: HealthDimensionBackend;
    insurance_coverage: HealthDimensionBackend;
    liquidity: HealthDimensionBackend;
    retirement_readiness: HealthDimensionBackend;
    diversification: HealthDimensionBackend;
  };
  top_strengths: string[];
  top_weaknesses: string[];
  action_items: string[];
  calculated_at: string;
}

interface RecommendationBackend {
  id: string;
  category: string;
  priority: string;
  title: string;
  description: string;
  potential_savings?: number;
  potential_gain?: number;
  related_entity_type?: string;
  related_entity_id?: string;
  related_entity_name?: string;
  action_url?: string;
  created_at: string;
}

interface RecommendationsListBackend {
  space_id: string;
  recommendations: RecommendationBackend[];
  total_count: number;
  critical_count: number;
  high_count: number;
  potential_total_savings: number;
  generated_at: string;
}

interface ExtraPaymentBackend {
  loan_id: string;
  loan_name: string;
  current_balance: number;
  current_monthly_payment: number;
  current_remaining_months: number;
  current_total_interest: number;
  extra_monthly_payment: number;
  new_monthly_payment: number;
  new_remaining_months: number;
  new_total_interest: number;
  interest_saved: number;
  months_saved: number;
  new_payoff_date: string;
  calculated_at: string;
}

interface RefinancingBackend {
  loan_id: string;
  loan_name: string;
  current_balance: number;
  current_rate: number;
  current_monthly_payment: number;
  current_remaining_months: number;
  current_total_cost: number;
  new_rate: number;
  estimated_prepayment_penalty: number;
  refinancing_costs: number;
  new_monthly_payment: number;
  new_total_cost: number;
  total_savings: number;
  break_even_months: number;
  is_worthwhile: boolean;
  recommendation: string;
  calculated_at: string;
}

interface AmortizationEntryBackend {
  month: number;
  date: string;
  payment: number;
  principal: number;
  interest: number;
  balance: number;
  cumulative_interest: number;
  cumulative_principal: number;
}

interface FullAmortizationBackend {
  loan_id: string;
  loan_name: string;
  principal_amount: number;
  interest_rate: number;
  monthly_payment: number;
  total_months: number;
  total_interest: number;
  total_cost: number;
  schedule: AmortizationEntryBackend[];
  summary: {
    first_year_interest: number;
    last_year_interest: number;
    halfway_date: string;
    halfway_balance: number;
  };
  calculated_at: string;
}

interface LoanComparisonBackend {
  loan_id: string;
  loan_name: string;
  scenarios: Array<{
    name: string;
    monthly_payment: number;
    total_months: number;
    total_interest: number;
    total_cost: number;
    payoff_date: string;
  }>;
  recommendation: string;
  calculated_at: string;
}

// ==================== Transformers ====================

function transformInvestmentPerformance(data: InvestmentPerformanceBackend): InvestmentPerformance {
  return {
    investmentId: data.investment_id,
    name: data.name,
    investmentType: data.investment_type as InvestmentPerformance['investmentType'],
    initialAmount: data.initial_amount,
    currentValue: data.current_value,
    absoluteReturn: data.absolute_return,
    percentageReturn: data.percentage_return,
    annualizedReturn: data.annualized_return,
    holdingPeriodDays: data.holding_period_days,
    holdingPeriodYears: data.holding_period_years,
    calculatedAt: data.calculated_at,
  };
}

function transformPortfolioAllocation(data: PortfolioAllocationBackend): PortfolioAllocation {
  return {
    spaceId: data.space_id,
    totalValue: data.total_value,
    investmentCount: data.investment_count,
    allocationByType: data.allocation_by_type,
    topHoldings: data.top_holdings,
    calculatedAt: data.calculated_at,
  };
}

function transformDiversificationScore(data: DiversificationScoreBackend): DiversificationScore {
  return {
    spaceId: data.space_id,
    herfindahlIndex: data.herfindahl_index,
    diversificationScore: data.diversification_score,
    interpretation: data.interpretation as DiversificationScore['interpretation'],
    typeCount: data.type_count,
    dominantType: data.dominant_type,
    dominantTypePercentage: data.dominant_type_percentage,
    recommendations: data.recommendations,
    calculatedAt: data.calculated_at,
  };
}

function transformRiskProfile(data: RiskProfileBackend): RiskProfile {
  return {
    spaceId: data.space_id,
    overallRiskScore: data.overall_risk_score,
    riskCategory: data.risk_category as RiskProfile['riskCategory'],
    riskByType: data.risk_by_type,
    volatilityEstimate: data.volatility_estimate,
    recommendations: data.recommendations,
    calculatedAt: data.calculated_at,
  };
}

function transformRebalancingSuggestion(data: RebalancingSuggestionBackend): RebalancingSuggestion {
  return {
    spaceId: data.space_id,
    currentAllocation: data.current_allocation,
    targetAllocation: data.target_allocation,
    rebalanceActions: data.rebalance_actions.map((action) => ({
      type: action.type,
      currentPercentage: action.current_percentage,
      targetPercentage: action.target_percentage,
      action: action.action as 'kaufen' | 'verkaufen' | 'halten',
      amountToAdjust: action.amount_to_adjust,
    })),
    totalAdjustmentNeeded: data.total_adjustment_needed,
    calculatedAt: data.calculated_at,
  };
}

function transformNetWorth(data: NetWorthBackend): NetWorthComponents {
  return {
    spaceId: data.space_id,
    totalAssets: data.total_assets,
    totalLiabilities: data.total_liabilities,
    netWorth: data.net_worth,
    components: data.components,
    assetAllocation: data.asset_allocation,
    calculatedAt: data.calculated_at,
  };
}

function transformHealthDimension(data: HealthDimensionBackend): FinancialHealthScore['dimensions']['netWorthTrend'] {
  return {
    score: data.score,
    weight: data.weight,
    contribution: data.contribution,
    interpretation: data.interpretation,
    recommendations: data.recommendations,
  };
}

function transformFinancialHealth(data: FinancialHealthBackend): FinancialHealthScore {
  return {
    spaceId: data.space_id,
    overallScore: data.overall_score,
    grade: data.grade as FinancialHealthScore['grade'],
    dimensions: {
      netWorthTrend: transformHealthDimension(data.dimensions.net_worth_trend),
      debtManagement: transformHealthDimension(data.dimensions.debt_management),
      insuranceCoverage: transformHealthDimension(data.dimensions.insurance_coverage),
      liquidity: transformHealthDimension(data.dimensions.liquidity),
      retirementReadiness: transformHealthDimension(data.dimensions.retirement_readiness),
      diversification: transformHealthDimension(data.dimensions.diversification),
    },
    topStrengths: data.top_strengths,
    topWeaknesses: data.top_weaknesses,
    actionItems: data.action_items,
    calculatedAt: data.calculated_at,
  };
}

function transformRecommendations(data: RecommendationsListBackend): SmartRecommendationsList {
  return {
    spaceId: data.space_id,
    recommendations: data.recommendations.map((rec) => ({
      id: rec.id,
      category: rec.category as SmartRecommendationsList['recommendations'][0]['category'],
      priority: rec.priority as SmartRecommendationsList['recommendations'][0]['priority'],
      title: rec.title,
      description: rec.description,
      potentialSavings: rec.potential_savings,
      potentialGain: rec.potential_gain,
      relatedEntityType: rec.related_entity_type,
      relatedEntityId: rec.related_entity_id,
      relatedEntityName: rec.related_entity_name,
      actionUrl: rec.action_url,
      createdAt: rec.created_at,
    })),
    totalCount: data.total_count,
    criticalCount: data.critical_count,
    highCount: data.high_count,
    potentialTotalSavings: data.potential_total_savings,
    generatedAt: data.generated_at,
  };
}

function transformExtraPayment(data: ExtraPaymentBackend): ExtraPaymentScenario {
  return {
    loanId: data.loan_id,
    loanName: data.loan_name,
    currentBalance: data.current_balance,
    currentMonthlyPayment: data.current_monthly_payment,
    currentRemainingMonths: data.current_remaining_months,
    currentTotalInterest: data.current_total_interest,
    extraMonthlyPayment: data.extra_monthly_payment,
    newMonthlyPayment: data.new_monthly_payment,
    newRemainingMonths: data.new_remaining_months,
    newTotalInterest: data.new_total_interest,
    interestSaved: data.interest_saved,
    monthsSaved: data.months_saved,
    newPayoffDate: data.new_payoff_date,
    calculatedAt: data.calculated_at,
  };
}

function transformRefinancing(data: RefinancingBackend): RefinancingScenario {
  return {
    loanId: data.loan_id,
    loanName: data.loan_name,
    currentBalance: data.current_balance,
    currentRate: data.current_rate,
    currentMonthlyPayment: data.current_monthly_payment,
    currentRemainingMonths: data.current_remaining_months,
    currentTotalCost: data.current_total_cost,
    newRate: data.new_rate,
    estimatedPrepaymentPenalty: data.estimated_prepayment_penalty,
    refinancingCosts: data.refinancing_costs,
    newMonthlyPayment: data.new_monthly_payment,
    newTotalCost: data.new_total_cost,
    totalSavings: data.total_savings,
    breakEvenMonths: data.break_even_months,
    isWorthwhile: data.is_worthwhile,
    recommendation: data.recommendation,
    calculatedAt: data.calculated_at,
  };
}

function transformFullAmortization(data: FullAmortizationBackend): FullAmortizationSchedule {
  return {
    loanId: data.loan_id,
    loanName: data.loan_name,
    principalAmount: data.principal_amount,
    interestRate: data.interest_rate,
    monthlyPayment: data.monthly_payment,
    totalMonths: data.total_months,
    totalInterest: data.total_interest,
    totalCost: data.total_cost,
    schedule: data.schedule.map((entry) => ({
      month: entry.month,
      date: entry.date,
      payment: entry.payment,
      principal: entry.principal,
      interest: entry.interest,
      balance: entry.balance,
      cumulativeInterest: entry.cumulative_interest,
      cumulativePrincipal: entry.cumulative_principal,
    })),
    summary: {
      firstYearInterest: data.summary.first_year_interest,
      lastYearInterest: data.summary.last_year_interest,
      halfwayDate: data.summary.halfway_date,
      halfwayBalance: data.summary.halfway_balance,
    },
    calculatedAt: data.calculated_at,
  };
}

function transformLoanComparison(data: LoanComparisonBackend): LoanComparison {
  return {
    loanId: data.loan_id,
    loanName: data.loan_name,
    scenarios: data.scenarios.map((s) => ({
      name: s.name,
      monthlyPayment: s.monthly_payment,
      totalMonths: s.total_months,
      totalInterest: s.total_interest,
      totalCost: s.total_cost,
      payoffDate: s.payoff_date,
    })),
    recommendation: data.recommendation,
    calculatedAt: data.calculated_at,
  };
}

// ==================== Intelligence API Service ====================

export const privatIntelligenceService = {
  // ==================== Investment Intelligence ====================

  /**
   * Holt Performance-Daten für ein Investment
   */
  getInvestmentPerformance: async (investmentId: string): Promise<InvestmentPerformance> => {
    try {
      const response = await apiClient.get<InvestmentPerformanceBackend>(
        `/privat/analytics/investments/${investmentId}/performance`
      );
      return transformInvestmentPerformance(response.data);
    } catch (error) {
      handleApiError(error, 'Investment-Performance laden');
    }
  },

  /**
   * Holt Portfolio-Allokation für einen Space
   */
  getPortfolioAllocation: async (spaceId: string): Promise<PortfolioAllocation> => {
    try {
      const response = await apiClient.get<PortfolioAllocationBackend>(
        `/privat/analytics/spaces/${spaceId}/portfolio/allocation`
      );
      return transformPortfolioAllocation(response.data);
    } catch (error) {
      handleApiError(error, 'Portfolio-Allokation laden');
    }
  },

  /**
   * Holt Diversifikations-Score
   */
  getDiversificationScore: async (spaceId: string): Promise<DiversificationScore> => {
    try {
      const response = await apiClient.get<DiversificationScoreBackend>(
        `/privat/analytics/spaces/${spaceId}/portfolio/diversification`
      );
      return transformDiversificationScore(response.data);
    } catch (error) {
      handleApiError(error, 'Diversifikations-Score laden');
    }
  },

  /**
   * Holt Risiko-Profil
   */
  getRiskProfile: async (spaceId: string): Promise<RiskProfile> => {
    try {
      const response = await apiClient.get<RiskProfileBackend>(
        `/privat/analytics/spaces/${spaceId}/portfolio/risk-profile`
      );
      return transformRiskProfile(response.data);
    } catch (error) {
      handleApiError(error, 'Risiko-Profil laden');
    }
  },

  /**
   * Holt Rebalancing-Vorschläge
   */
  getRebalancingSuggestions: async (spaceId: string): Promise<RebalancingSuggestion> => {
    try {
      const response = await apiClient.get<RebalancingSuggestionBackend>(
        `/privat/analytics/spaces/${spaceId}/portfolio/rebalancing`
      );
      return transformRebalancingSuggestion(response.data);
    } catch (error) {
      handleApiError(error, 'Rebalancing-Vorschläge laden');
    }
  },

  /**
   * Holt vollständige Investment-Analyse
   */
  getFullInvestmentAnalytics: async (spaceId: string): Promise<InvestmentFullAnalytics> => {
    try {
      const response = await apiClient.get<{
        space_id: string;
        allocation: PortfolioAllocationBackend;
        diversification: DiversificationScoreBackend;
        risk_profile: RiskProfileBackend;
        rebalancing: RebalancingSuggestionBackend;
        calculated_at: string;
      }>(`/privat/analytics/spaces/${spaceId}/portfolio/full-analytics`);

      return {
        spaceId: response.data.space_id,
        allocation: transformPortfolioAllocation(response.data.allocation),
        diversification: transformDiversificationScore(response.data.diversification),
        riskProfile: transformRiskProfile(response.data.risk_profile),
        rebalancing: transformRebalancingSuggestion(response.data.rebalancing),
        calculatedAt: response.data.calculated_at,
      };
    } catch (error) {
      handleApiError(error, 'Vollständige Investment-Analyse laden');
    }
  },

  // ==================== Financial Health ====================

  /**
   * Holt Nettovermögen-Aufstellung
   */
  getNetWorth: async (spaceId: string): Promise<NetWorthComponents> => {
    try {
      const response = await apiClient.get<NetWorthBackend>(
        `/privat/analytics/spaces/${spaceId}/net-worth`
      );
      return transformNetWorth(response.data);
    } catch (error) {
      handleApiError(error, 'Nettovermögen laden');
    }
  },

  /**
   * Holt Financial Health Score
   */
  getFinancialHealthScore: async (spaceId: string): Promise<FinancialHealthScore> => {
    try {
      const response = await apiClient.get<FinancialHealthBackend>(
        `/privat/analytics/spaces/${spaceId}/health-score`
      );
      return transformFinancialHealth(response.data);
    } catch (error) {
      handleApiError(error, 'Financial Health Score laden');
    }
  },

  // ==================== Smart Recommendations ====================

  /**
   * Holt Smart Recommendations
   */
  getRecommendations: async (
    spaceId: string,
    options?: { category?: string; priority?: string; limit?: number }
  ): Promise<SmartRecommendationsList> => {
    try {
      const params = new URLSearchParams();
      if (options?.category) params.append('category', options.category);
      if (options?.priority) params.append('priority', options.priority);
      if (options?.limit) params.append('limit', String(options.limit));

      const url = `/privat/analytics/spaces/${spaceId}/recommendations${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<RecommendationsListBackend>(url);
      return transformRecommendations(response.data);
    } catch (error) {
      handleApiError(error, 'Empfehlungen laden');
    }
  },

  // ==================== Loan Scenarios ====================

  /**
   * Simuliert Sonderzahlung für einen Kredit
   */
  simulateExtraPayment: async (
    loanId: string,
    extraMonthlyPayment: number
  ): Promise<ExtraPaymentScenario> => {
    try {
      const response = await apiClient.post<ExtraPaymentBackend>(
        `/privat/analytics/loans/${loanId}/simulate/extra-payment`,
        { extra_monthly_payment: extraMonthlyPayment }
      );
      return transformExtraPayment(response.data);
    } catch (error) {
      handleApiError(error, 'Sonderzahlung simulieren');
    }
  },

  /**
   * Simuliert Umschuldung für einen Kredit
   */
  simulateRefinancing: async (
    loanId: string,
    newRate: number,
    refinancingCosts?: number
  ): Promise<RefinancingScenario> => {
    try {
      const response = await apiClient.post<RefinancingBackend>(
        `/privat/analytics/loans/${loanId}/simulate/refinancing`,
        {
          new_rate: newRate,
          refinancing_costs: refinancingCosts,
        }
      );
      return transformRefinancing(response.data);
    } catch (error) {
      handleApiError(error, 'Umschuldung simulieren');
    }
  },

  /**
   * Holt vollständigen Tilgungsplan
   */
  getFullAmortization: async (loanId: string): Promise<FullAmortizationSchedule> => {
    try {
      const response = await apiClient.get<FullAmortizationBackend>(
        `/privat/analytics/loans/${loanId}/full-amortization`
      );
      return transformFullAmortization(response.data);
    } catch (error) {
      handleApiError(error, 'Tilgungsplan laden');
    }
  },

  /**
   * Vergleicht verschiedene Kredit-Szenarien
   */
  compareScenarios: async (
    loanId: string,
    scenarios: Array<{ name: string; extraPayment?: number; newRate?: number }>
  ): Promise<LoanComparison> => {
    try {
      const response = await apiClient.post<LoanComparisonBackend>(
        `/privat/analytics/loans/${loanId}/compare-scenarios`,
        { scenarios }
      );
      return transformLoanComparison(response.data);
    } catch (error) {
      handleApiError(error, 'Szenarien vergleichen');
    }
  },

  // ==================== Property/Vehicle Intelligence Triggers ====================

  /**
   * Triggert Neuberechnung der Property Intelligence
   */
  recalculatePropertyIntelligence: async (propertyId: string): Promise<{ message: string; taskId: string }> => {
    try {
      const response = await apiClient.post<{ message: string; task_id: string }>(
        `/privat/analytics/properties/${propertyId}/recalculate-intelligence`
      );
      return {
        message: response.data.message,
        taskId: response.data.task_id,
      };
    } catch (error) {
      handleApiError(error, 'Property Intelligence neuberechnen');
    }
  },

  /**
   * Triggert Neuberechnung der Vehicle Intelligence
   */
  recalculateVehicleIntelligence: async (vehicleId: string): Promise<{ message: string; taskId: string }> => {
    try {
      const response = await apiClient.post<{ message: string; task_id: string }>(
        `/privat/analytics/vehicles/${vehicleId}/recalculate-intelligence`
      );
      return {
        message: response.data.message,
        taskId: response.data.task_id,
      };
    } catch (error) {
      handleApiError(error, 'Vehicle Intelligence neuberechnen');
    }
  },

  /**
   * Triggert Berechnung aller Intelligence-Features für einen Space
   */
  calculateAllIntelligence: async (spaceId: string): Promise<{ message: string; taskIds: Record<string, string> }> => {
    try {
      const response = await apiClient.post<{ message: string; task_ids: Record<string, string> }>(
        `/privat/analytics/spaces/${spaceId}/calculate-all-intelligence`
      );
      return {
        message: response.data.message,
        taskIds: response.data.task_ids,
      };
    } catch (error) {
      handleApiError(error, 'Alle Intelligence-Features berechnen');
    }
  },
};

export default privatIntelligenceService;
