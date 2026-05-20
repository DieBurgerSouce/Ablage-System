/**
 * Retirement Planning API Service
 *
 * API-Service für Altersvorsorge-Planung:
 * - Rentenlücken-Berechnung
 * - Monte-Carlo-Simulation
 * - Entnahmestrategien
 * - Riester/Rürup-Optimierung
 * - bAV-Analyse
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Class ====================

export class RetirementApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'RetirementApiError';
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
      throw new RetirementApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new RetirementApiError(`${context}: ${message}`, 400, error);
    }

    throw new RetirementApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new RetirementApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Types ====================

export type PensionType =
  | 'gesetzlich'
  | 'riester'
  | 'ruerup'
  | 'bav'
  | 'private'
  | 'depot'
  | 'immobilie';

export type WithdrawalStrategy =
  | 'fixed_percentage'
  | 'dynamic'
  | 'floor_ceiling'
  | 'guyton_klinger'
  | 'vpw';

export type RiskProfile = 'konservativ' | 'ausgewogen' | 'wachstum';

export interface PensionSource {
  pensionType: PensionType;
  name: string;
  currentValue: number;
  expectedMonthlyBenefit: number;
  guaranteedMonthlyBenefit?: number;
  startAge: number;
  annualContribution: number;
  employerContribution: number;
  taxTreatment: string;
  notes?: string;
}

export interface PensionGapResult {
  spaceId: string;
  currentAge: number;
  retirementAge: number;
  yearsUntilRetirement: number;
  targetMonthlyIncome: number;
  targetReplacementRatio: number;
  expectedStatutoryPension: number;
  expectedRiester: number;
  expectedRuerup: number;
  expectedBav: number;
  expectedPrivate: number;
  expectedInvestmentIncome: number;
  totalExpectedPension: number;
  pensionGap: number;
  pensionGapYearly: number;
  capitalNeededForGap: number;
  currentSavings: number;
  additionalSavingsNeeded: number;
  monthlySavingsRequired: number;
  currentPensionPoints: number;
  projectedPensionPoints: number;
  recommendations: string[];
  calculatedAt: string;
}

export interface WithdrawalPlan {
  strategy: WithdrawalStrategy;
  initialPortfolio: number;
  annualWithdrawalRate: number;
  initialAnnualWithdrawal: number;
  inflationAdjusted: boolean;
  yearlyProjections: Array<{
    year: number;
    portfolioStart: number;
    withdrawal: number;
    portfolioAfterWithdrawal: number;
    expectedReturn: string;
    portfolioEnd: number;
  }>;
  successProbability: number;
  medianEndPortfolio: number;
  worstCaseEndPortfolio: number;
  bestCaseEndPortfolio: number;
  safeWithdrawalRate: number;
  recommendations: string[];
}

export interface MonteCarloResult {
  iterations: number;
  timeHorizonYears: number;
  initialPortfolio: number;
  annualWithdrawal: number;
  successRate: number;
  medianEndPortfolio: number;
  percentile5: number;
  percentile95: number;
  meanEndPortfolio: number;
  stdDev: number;
  portfolioPaths: number[][];
  recommendations: string[];
}

export interface RiesterOptimization {
  eligible: boolean;
  optimalEigenbeitrag: number;
  totalZulagen: number;
  grundzulage: number;
  kinderzulagen: number;
  taxBenefit: number;
  netCost: number;
  effectiveReturnBoost: number;
  recommendations: string[];
}

export interface BAVAnalysis {
  currentContribution: number;
  employerMatch: number;
  employerMatchPercent: number;
  totalContribution: number;
  taxSavings: number;
  socialSecuritySavings: number;
  totalImmediateBenefit: number;
  projectedCapitalAtRetirement: number;
  projectedMonthlyPension: number;
  optimalContribution: number;
  maxTaxFreeContribution: number;
  additionalEmployerMatchAvailable: boolean;
  recommendations: string[];
}

export interface RetirementSummary {
  spaceId: string;
  currentAge: number;
  targetRetirementAge: number;
  pensionGapAnalysis: PensionGapResult;
  withdrawalPlan?: WithdrawalPlan;
  monteCarloResult?: MonteCarloResult;
  riesterAnalysis?: RiesterOptimization;
  bavAnalysis?: BAVAnalysis;
  retirementReadinessScore: number;
  overallRating: 'gut' | 'ausreichend' | 'kritisch';
  priorityActions: string[];
  calculatedAt: string;
}

// ==================== Request Types ====================

export interface PensionGapRequest {
  birthDate: string;
  currentGrossAnnualIncome: number;
  targetReplacementRatio?: number;
  currentPensionPoints?: number;
  pensionSources?: PensionSource[];
  retirementAge?: number;
}

export interface WithdrawalPlanRequest {
  initialPortfolio: number;
  annualWithdrawalRate?: number;
  timeHorizonYears?: number;
  strategy?: WithdrawalStrategy;
  inflationAdjusted?: boolean;
  riskProfile?: RiskProfile;
  floorRate?: number;
  ceilingRate?: number;
}

export interface MonteCarloRequest {
  initialPortfolio: number;
  annualWithdrawal: number;
  timeHorizonYears: number;
  riskProfile?: RiskProfile;
  iterations?: number;
  inflationAdjusted?: boolean;
}

export interface RiesterOptimizationRequest {
  grossAnnualIncome: number;
  marginalTaxRate: number;
  childrenBornAfter2007?: number;
  childrenBornBefore2008?: number;
  currentRiesterContribution?: number;
}

export interface BAVAnalysisRequest {
  currentContribution: number;
  employerMatchPercent: number;
  employerMatchCap?: number;
  marginalTaxRate?: number;
  socialSecurityRate?: number;
  yearsUntilRetirement?: number;
}

export interface RetirementSummaryRequest {
  birthDate: string;
  currentGrossAnnualIncome: number;
  pensionSources?: PensionSource[];
  riskProfile?: RiskProfile;
  targetRetirementAge?: number;
  childrenBornAfter2007?: number;
  childrenBornBefore2008?: number;
}

// ==================== Backend Response Types ====================

interface PensionGapBackend {
  space_id: string;
  current_age: number;
  retirement_age: number;
  years_until_retirement: number;
  target_monthly_income: string;
  target_replacement_ratio: string;
  expected_statutory_pension: string;
  expected_riester: string;
  expected_ruerup: string;
  expected_bav: string;
  expected_private: string;
  expected_investment_income: string;
  total_expected_pension: string;
  pension_gap: string;
  pension_gap_yearly: string;
  capital_needed_for_gap: string;
  current_savings: string;
  additional_savings_needed: string;
  monthly_savings_required: string;
  current_pension_points: string;
  projected_pension_points: string;
  recommendations: string[];
  calculated_at: string;
}

interface MonteCarloBackend {
  iterations: number;
  time_horizon_years: number;
  initial_portfolio: string;
  annual_withdrawal: string;
  success_rate: string;
  median_end_portfolio: string;
  percentile_5: string;
  percentile_95: string;
  mean_end_portfolio: string;
  std_dev: string;
  portfolio_paths: string[][];
  recommendations: string[];
}

interface WithdrawalPlanBackend {
  strategy: WithdrawalStrategy;
  initial_portfolio: string;
  annual_withdrawal_rate: string;
  initial_annual_withdrawal: string;
  inflation_adjusted: boolean;
  yearly_projections: Array<{
    year: number;
    portfolio_start: string;
    withdrawal: string;
    portfolio_after_withdrawal: string;
    expected_return: string;
    portfolio_end: string;
  }>;
  success_probability: string;
  median_end_portfolio: string;
  worst_case_end_portfolio: string;
  best_case_end_portfolio: string;
  safe_withdrawal_rate: string;
  recommendations: string[];
}

interface RiesterBackend {
  eligible: boolean;
  optimal_eigenbeitrag: string;
  total_zulagen: string;
  grundzulage: string;
  kinderzulagen: string;
  tax_benefit: string;
  net_cost: string;
  effective_return_boost: string;
  recommendations: string[];
}

interface BAVBackend {
  current_contribution: string;
  employer_match: string;
  employer_match_percent: string;
  total_contribution: string;
  tax_savings: string;
  social_security_savings: string;
  total_immediate_benefit: string;
  projected_capital_at_retirement: string;
  projected_monthly_pension: string;
  optimal_contribution: string;
  max_tax_free_contribution: string;
  additional_employer_match_available: boolean;
  recommendations: string[];
}

interface RetirementSummaryBackend {
  space_id: string;
  current_age: number;
  target_retirement_age: number;
  pension_gap_analysis: PensionGapBackend;
  withdrawal_plan?: WithdrawalPlanBackend;
  monte_carlo_result?: MonteCarloBackend;
  riester_analysis?: RiesterBackend;
  bav_analysis?: BAVBackend;
  retirement_readiness_score: string;
  overall_rating: 'gut' | 'ausreichend' | 'kritisch';
  priority_actions: string[];
  calculated_at: string;
}

// ==================== Transformers ====================

function parseDecimal(value: string | number): number {
  if (typeof value === 'number') return value;
  return parseFloat(value) || 0;
}

function transformPensionGap(data: PensionGapBackend): PensionGapResult {
  return {
    spaceId: data.space_id,
    currentAge: data.current_age,
    retirementAge: data.retirement_age,
    yearsUntilRetirement: data.years_until_retirement,
    targetMonthlyIncome: parseDecimal(data.target_monthly_income),
    targetReplacementRatio: parseDecimal(data.target_replacement_ratio),
    expectedStatutoryPension: parseDecimal(data.expected_statutory_pension),
    expectedRiester: parseDecimal(data.expected_riester),
    expectedRuerup: parseDecimal(data.expected_ruerup),
    expectedBav: parseDecimal(data.expected_bav),
    expectedPrivate: parseDecimal(data.expected_private),
    expectedInvestmentIncome: parseDecimal(data.expected_investment_income),
    totalExpectedPension: parseDecimal(data.total_expected_pension),
    pensionGap: parseDecimal(data.pension_gap),
    pensionGapYearly: parseDecimal(data.pension_gap_yearly),
    capitalNeededForGap: parseDecimal(data.capital_needed_for_gap),
    currentSavings: parseDecimal(data.current_savings),
    additionalSavingsNeeded: parseDecimal(data.additional_savings_needed),
    monthlySavingsRequired: parseDecimal(data.monthly_savings_required),
    currentPensionPoints: parseDecimal(data.current_pension_points),
    projectedPensionPoints: parseDecimal(data.projected_pension_points),
    recommendations: data.recommendations,
    calculatedAt: data.calculated_at,
  };
}

function transformMonteCarlo(data: MonteCarloBackend): MonteCarloResult {
  return {
    iterations: data.iterations,
    timeHorizonYears: data.time_horizon_years,
    initialPortfolio: parseDecimal(data.initial_portfolio),
    annualWithdrawal: parseDecimal(data.annual_withdrawal),
    successRate: parseDecimal(data.success_rate),
    medianEndPortfolio: parseDecimal(data.median_end_portfolio),
    percentile5: parseDecimal(data.percentile_5),
    percentile95: parseDecimal(data.percentile_95),
    meanEndPortfolio: parseDecimal(data.mean_end_portfolio),
    stdDev: parseDecimal(data.std_dev),
    portfolioPaths: data.portfolio_paths.map((path) =>
      path.map((val) => parseDecimal(val))
    ),
    recommendations: data.recommendations,
  };
}

function transformWithdrawalPlan(data: WithdrawalPlanBackend): WithdrawalPlan {
  return {
    strategy: data.strategy,
    initialPortfolio: parseDecimal(data.initial_portfolio),
    annualWithdrawalRate: parseDecimal(data.annual_withdrawal_rate),
    initialAnnualWithdrawal: parseDecimal(data.initial_annual_withdrawal),
    inflationAdjusted: data.inflation_adjusted,
    yearlyProjections: data.yearly_projections.map((proj) => ({
      year: proj.year,
      portfolioStart: parseDecimal(proj.portfolio_start),
      withdrawal: parseDecimal(proj.withdrawal),
      portfolioAfterWithdrawal: parseDecimal(proj.portfolio_after_withdrawal),
      expectedReturn: proj.expected_return,
      portfolioEnd: parseDecimal(proj.portfolio_end),
    })),
    successProbability: parseDecimal(data.success_probability),
    medianEndPortfolio: parseDecimal(data.median_end_portfolio),
    worstCaseEndPortfolio: parseDecimal(data.worst_case_end_portfolio),
    bestCaseEndPortfolio: parseDecimal(data.best_case_end_portfolio),
    safeWithdrawalRate: parseDecimal(data.safe_withdrawal_rate),
    recommendations: data.recommendations,
  };
}

function transformRiester(data: RiesterBackend): RiesterOptimization {
  return {
    eligible: data.eligible,
    optimalEigenbeitrag: parseDecimal(data.optimal_eigenbeitrag),
    totalZulagen: parseDecimal(data.total_zulagen),
    grundzulage: parseDecimal(data.grundzulage),
    kinderzulagen: parseDecimal(data.kinderzulagen),
    taxBenefit: parseDecimal(data.tax_benefit),
    netCost: parseDecimal(data.net_cost),
    effectiveReturnBoost: parseDecimal(data.effective_return_boost),
    recommendations: data.recommendations,
  };
}

function transformBAV(data: BAVBackend): BAVAnalysis {
  return {
    currentContribution: parseDecimal(data.current_contribution),
    employerMatch: parseDecimal(data.employer_match),
    employerMatchPercent: parseDecimal(data.employer_match_percent),
    totalContribution: parseDecimal(data.total_contribution),
    taxSavings: parseDecimal(data.tax_savings),
    socialSecuritySavings: parseDecimal(data.social_security_savings),
    totalImmediateBenefit: parseDecimal(data.total_immediate_benefit),
    projectedCapitalAtRetirement: parseDecimal(data.projected_capital_at_retirement),
    projectedMonthlyPension: parseDecimal(data.projected_monthly_pension),
    optimalContribution: parseDecimal(data.optimal_contribution),
    maxTaxFreeContribution: parseDecimal(data.max_tax_free_contribution),
    additionalEmployerMatchAvailable: data.additional_employer_match_available,
    recommendations: data.recommendations,
  };
}

function transformRetirementSummary(data: RetirementSummaryBackend): RetirementSummary {
  return {
    spaceId: data.space_id,
    currentAge: data.current_age,
    targetRetirementAge: data.target_retirement_age,
    pensionGapAnalysis: transformPensionGap(data.pension_gap_analysis),
    withdrawalPlan: data.withdrawal_plan
      ? transformWithdrawalPlan(data.withdrawal_plan)
      : undefined,
    monteCarloResult: data.monte_carlo_result
      ? transformMonteCarlo(data.monte_carlo_result)
      : undefined,
    riesterAnalysis: data.riester_analysis
      ? transformRiester(data.riester_analysis)
      : undefined,
    bavAnalysis: data.bav_analysis ? transformBAV(data.bav_analysis) : undefined,
    retirementReadinessScore: parseDecimal(data.retirement_readiness_score),
    overallRating: data.overall_rating,
    priorityActions: data.priority_actions,
    calculatedAt: data.calculated_at,
  };
}

// ==================== API Service ====================

export const retirementService = {
  /**
   * Berechnet die Rentenlücke
   */
  calculatePensionGap: async (
    spaceId: string,
    request: PensionGapRequest
  ): Promise<PensionGapResult> => {
    try {
      const response = await apiClient.post<PensionGapBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/pension-gap`,
        {
          birth_date: request.birthDate,
          current_gross_annual_income: request.currentGrossAnnualIncome,
          target_replacement_ratio: request.targetReplacementRatio,
          current_pension_points: request.currentPensionPoints,
          pension_sources: request.pensionSources?.map((s) => ({
            pension_type: s.pensionType,
            name: s.name,
            current_value: s.currentValue,
            expected_monthly_benefit: s.expectedMonthlyBenefit,
            guaranteed_monthly_benefit: s.guaranteedMonthlyBenefit,
            start_age: s.startAge,
            annual_contribution: s.annualContribution,
            employer_contribution: s.employerContribution,
            tax_treatment: s.taxTreatment,
            notes: s.notes,
          })),
          retirement_age: request.retirementAge,
        }
      );
      return transformPensionGap(response.data);
    } catch (error) {
      handleApiError(error, 'Rentenlücke berechnen');
    }
  },

  /**
   * Führt Monte-Carlo-Simulation durch
   */
  runMonteCarlo: async (
    spaceId: string,
    request: MonteCarloRequest
  ): Promise<MonteCarloResult> => {
    try {
      const response = await apiClient.post<MonteCarloBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/monte-carlo`,
        {
          initial_portfolio: request.initialPortfolio,
          annual_withdrawal: request.annualWithdrawal,
          time_horizon_years: request.timeHorizonYears,
          risk_profile: request.riskProfile,
          iterations: request.iterations,
          inflation_adjusted: request.inflationAdjusted,
        }
      );
      return transformMonteCarlo(response.data);
    } catch (error) {
      handleApiError(error, 'Monte-Carlo-Simulation');
    }
  },

  /**
   * Erstellt Entnahmeplan
   */
  createWithdrawalPlan: async (
    spaceId: string,
    request: WithdrawalPlanRequest
  ): Promise<WithdrawalPlan> => {
    try {
      const response = await apiClient.post<WithdrawalPlanBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/withdrawal-plan`,
        {
          initial_portfolio: request.initialPortfolio,
          annual_withdrawal_rate: request.annualWithdrawalRate,
          time_horizon_years: request.timeHorizonYears,
          strategy: request.strategy,
          inflation_adjusted: request.inflationAdjusted,
          risk_profile: request.riskProfile,
          floor_rate: request.floorRate,
          ceiling_rate: request.ceilingRate,
        }
      );
      return transformWithdrawalPlan(response.data);
    } catch (error) {
      handleApiError(error, 'Entnahmeplan erstellen');
    }
  },

  /**
   * Optimiert Riester-Beiträge
   */
  optimizeRiester: async (
    spaceId: string,
    request: RiesterOptimizationRequest
  ): Promise<RiesterOptimization> => {
    try {
      const response = await apiClient.post<RiesterBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/riester-optimize`,
        {
          gross_annual_income: request.grossAnnualIncome,
          marginal_tax_rate: request.marginalTaxRate,
          children_born_after_2007: request.childrenBornAfter2007,
          children_born_before_2008: request.childrenBornBefore2008,
          current_riester_contribution: request.currentRiesterContribution,
        }
      );
      return transformRiester(response.data);
    } catch (error) {
      handleApiError(error, 'Riester optimieren');
    }
  },

  /**
   * Analysiert betriebliche Altersvorsorge
   */
  analyzeBAV: async (
    spaceId: string,
    request: BAVAnalysisRequest
  ): Promise<BAVAnalysis> => {
    try {
      const response = await apiClient.post<BAVBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/bav-analyze`,
        {
          current_contribution: request.currentContribution,
          employer_match_percent: request.employerMatchPercent,
          employer_match_cap: request.employerMatchCap,
          marginal_tax_rate: request.marginalTaxRate,
          social_security_rate: request.socialSecurityRate,
          years_until_retirement: request.yearsUntilRetirement,
        }
      );
      return transformBAV(response.data);
    } catch (error) {
      handleApiError(error, 'bAV analysieren');
    }
  },

  /**
   * Generiert vollständige Altersvorsorge-Zusammenfassung
   */
  getRetirementSummary: async (
    spaceId: string,
    request: RetirementSummaryRequest
  ): Promise<RetirementSummary> => {
    try {
      const response = await apiClient.post<RetirementSummaryBackend>(
        `/privat/analytics/spaces/${spaceId}/retirement/summary`,
        {
          birth_date: request.birthDate,
          current_gross_annual_income: request.currentGrossAnnualIncome,
          pension_sources: request.pensionSources?.map((s) => ({
            pension_type: s.pensionType,
            name: s.name,
            current_value: s.currentValue,
            expected_monthly_benefit: s.expectedMonthlyBenefit,
            guaranteed_monthly_benefit: s.guaranteedMonthlyBenefit,
            start_age: s.startAge,
            annual_contribution: s.annualContribution,
            employer_contribution: s.employerContribution,
            tax_treatment: s.taxTreatment,
            notes: s.notes,
          })),
          risk_profile: request.riskProfile,
          target_retirement_age: request.targetRetirementAge,
          children_born_after_2007: request.childrenBornAfter2007,
          children_born_before_2008: request.childrenBornBefore2008,
        }
      );
      return transformRetirementSummary(response.data);
    } catch (error) {
      handleApiError(error, 'Altersvorsorge-Zusammenfassung laden');
    }
  },

  /**
   * Berechnet Rentenpunkte für ein Jahr
   */
  calculatePensionPoints: async (
    grossAnnualIncome: number,
    year?: number
  ): Promise<{ points: number; relevantIncome: number }> => {
    try {
      const response = await apiClient.post<{
        points: string;
        relevant_income: string;
      }>('/privat/analytics/retirement/pension-points', {
        gross_annual_income: grossAnnualIncome,
        year: year,
      });
      return {
        points: parseDecimal(response.data.points),
        relevantIncome: parseDecimal(response.data.relevant_income),
      };
    } catch (error) {
      handleApiError(error, 'Rentenpunkte berechnen');
    }
  },

  /**
   * Berechnet gesetzliche Rente aus Punkten
   */
  calculateStatutoryPension: async (
    totalPensionPoints: number,
    earlyRetirementMonths?: number
  ): Promise<{ monthlyPension: number; zugangsfaktor: number }> => {
    try {
      const response = await apiClient.post<{
        monthly_pension: string;
        zugangsfaktor: string;
      }>('/privat/analytics/retirement/statutory-pension', {
        total_pension_points: totalPensionPoints,
        early_retirement_months: earlyRetirementMonths,
      });
      return {
        monthlyPension: parseDecimal(response.data.monthly_pension),
        zugangsfaktor: parseDecimal(response.data.zugangsfaktor),
      };
    } catch (error) {
      handleApiError(error, 'Gesetzliche Rente berechnen');
    }
  },
};

export default retirementService;
