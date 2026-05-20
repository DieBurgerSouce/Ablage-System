/**
 * Risk Scoring Types
 *
 * TypeScript Definitionen für das Risk Scoring System.
 */

// Risk Level Kategorien
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

// Entity Typen
export type EntityType = 'customer' | 'supplier';

// Risk Faktor Namen
export type RiskFactorName =
  | 'payment_delay'
  | 'default_rate'
  | 'invoice_volume'
  | 'document_frequency'
  | 'relationship_age';

// Risk Faktor Gewichtungen
export const RISK_FACTOR_WEIGHTS: Record<RiskFactorName, number> = {
  payment_delay: 0.35,
  default_rate: 0.25,
  invoice_volume: 0.15,
  document_frequency: 0.10,
  relationship_age: 0.15,
};

// Risk Faktor Labels (German)
export const RISK_FACTOR_LABELS: Record<RiskFactorName, string> = {
  payment_delay: 'Zahlungsverzögerung',
  default_rate: 'Ausfallrate',
  invoice_volume: 'Rechnungsvolumen',
  document_frequency: 'Dokumenthäufigkeit',
  relationship_age: 'Beziehungsdauer',
};

// Risk Faktor Beschreibungen (German)
export const RISK_FACTOR_DESCRIPTIONS: Record<RiskFactorName, string> = {
  payment_delay: 'Durchschnittliche Zahlungsverzögerung in Tagen',
  default_rate: 'Anteil überfälliger Rechnungen',
  invoice_volume: 'Gesamtvolumen aller Rechnungen',
  document_frequency: 'Dokumente pro Monat',
  relationship_age: 'Beziehungsdauer in Monaten',
};

// Risk Level Schwellenwerte
export const RISK_LEVEL_THRESHOLDS = {
  low: { min: 0, max: 25 },
  medium: { min: 25, max: 50 },
  high: { min: 50, max: 75 },
  critical: { min: 75, max: 100 },
} as const;

// Risk Level Labels (German)
export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  low: 'Niedrig',
  medium: 'Mittel',
  high: 'Hoch',
  critical: 'Kritisch',
};

// Risk Level Farben
export const RISK_LEVEL_COLORS: Record<RiskLevel, { bg: string; text: string; border: string }> = {
  low: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    border: 'border-green-500',
  },
  medium: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
    border: 'border-yellow-500',
  },
  high: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    border: 'border-orange-500',
  },
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500',
  },
};

// Backend Response Types (snake_case)
export interface RiskFactorResponse {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  raw_value?: number | string;
}

export interface EntityRiskResponse {
  entity_id: string;
  entity_name: string;
  entity_type: 'customer' | 'supplier';
  risk_score: number;
  payment_behavior_score: number | null;
  risk_factors: RiskFactorResponse[];
  calculated_at: string;
  is_high_risk: boolean;
}

export interface RiskCalculationResponse {
  entity_id: string;
  risk_score: number;
  risk_factors: RiskFactorResponse[];
  calculated_at: string;
}

export interface BatchCalculationResponse {
  processed: number;
  updated: number;
  errors: number;
  duration_seconds: number;
}

export interface RiskStatisticsResponse {
  total_entities: number;
  high_risk_count: number;
  average_risk_score: number;
  risk_distribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  top_risk_factors: Array<{
    name: string;
    average_contribution: number;
  }>;
  trend: Array<{
    date: string;
    average_score: number;
    high_risk_count: number;
  }>;
}

// Frontend Types (camelCase)
export interface RiskFactor {
  name: RiskFactorName;
  value: number;
  weight: number;
  contribution: number;
  rawValue?: number | string;
}

export interface EntityRisk {
  entityId: string;
  entityName: string;
  entityType: EntityType;
  riskScore: number;
  paymentBehaviorScore: number | null;
  riskFactors: RiskFactor[];
  calculatedAt: Date;
  isHighRisk: boolean;
  riskLevel: RiskLevel;
}

export interface RiskCalculation {
  entityId: string;
  riskScore: number;
  riskFactors: RiskFactor[];
  calculatedAt: Date;
}

export interface BatchCalculation {
  processed: number;
  updated: number;
  errors: number;
  durationSeconds: number;
}

export interface RiskStatistics {
  totalEntities: number;
  highRiskCount: number;
  averageRiskScore: number;
  riskDistribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  topRiskFactors: Array<{
    name: RiskFactorName;
    averageContribution: number;
  }>;
  trend: Array<{
    date: Date;
    averageScore: number;
    highRiskCount: number;
  }>;
}

// Filter Types
export interface RiskFilter {
  entityType?: EntityType;
  riskLevel?: RiskLevel;
  minScore?: number;
  maxScore?: number;
  sortBy?: 'risk_score' | 'name' | 'calculated_at';
  sortOrder?: 'asc' | 'desc';
  page?: number;
  perPage?: number;
}

// Transformer Functions
export function transformRiskFactor(factor: RiskFactorResponse): RiskFactor {
  return {
    name: factor.name as RiskFactorName,
    value: factor.value,
    weight: factor.weight,
    contribution: factor.contribution,
    rawValue: factor.raw_value,
  };
}

export function getRiskLevel(score: number): RiskLevel {
  if (score >= RISK_LEVEL_THRESHOLDS.critical.min) return 'critical';
  if (score >= RISK_LEVEL_THRESHOLDS.high.min) return 'high';
  if (score >= RISK_LEVEL_THRESHOLDS.medium.min) return 'medium';
  return 'low';
}

export function transformEntityRisk(response: EntityRiskResponse): EntityRisk {
  return {
    entityId: response.entity_id,
    entityName: response.entity_name,
    entityType: response.entity_type,
    riskScore: response.risk_score,
    paymentBehaviorScore: response.payment_behavior_score,
    riskFactors: response.risk_factors.map(transformRiskFactor),
    calculatedAt: new Date(response.calculated_at),
    isHighRisk: response.is_high_risk,
    riskLevel: getRiskLevel(response.risk_score),
  };
}

export function transformRiskStatistics(response: RiskStatisticsResponse): RiskStatistics {
  return {
    totalEntities: response.total_entities,
    highRiskCount: response.high_risk_count,
    averageRiskScore: response.average_risk_score,
    riskDistribution: response.risk_distribution,
    topRiskFactors: response.top_risk_factors.map((f) => ({
      name: f.name as RiskFactorName,
      averageContribution: f.average_contribution,
    })),
    trend: response.trend.map((t) => ({
      date: new Date(t.date),
      averageScore: t.average_score,
      highRiskCount: t.high_risk_count,
    })),
  };
}

// UI Labels
export const UI_LABELS = {
  pageTitle: 'Risiko-Scoring',
  pageSubtitle: 'Risikobewertung für Kunden und Lieferanten',

  // Dashboard
  dashboardTitle: 'Risiko-Dashboard',
  totalEntities: 'Gesamt Entities',
  highRiskEntities: 'Hoch-Risiko',
  averageScore: 'Durchschnitt',
  riskDistribution: 'Risiko-Verteilung',

  // Risk Score
  riskScore: 'Risiko-Score',
  paymentBehavior: 'Zahlungsverhalten',
  calculatedAt: 'Berechnet am',

  // Actions
  recalculate: 'Neu berechnen',
  recalculateAll: 'Alle neu berechnen',
  viewDetails: 'Details anzeigen',

  // Filters
  filterByType: 'Nach Typ filtern',
  filterByLevel: 'Nach Risikostufe',
  allTypes: 'Alle Typen',
  allLevels: 'Alle Stufen',
  customers: 'Kunden',
  suppliers: 'Lieferanten',

  // Table
  entity: 'Entity',
  type: 'Typ',
  score: 'Score',
  level: 'Stufe',
  lastCalculated: 'Letzte Berechnung',

  // Messages
  successRecalculate: 'Risiko-Score wurde neu berechnet',
  successRecalculateAll: 'Alle Risiko-Scores wurden aktualisiert',
  errorRecalculate: 'Fehler bei der Neuberechnung',
  errorLoad: 'Fehler beim Laden der Risiko-Daten',
  noData: 'Keine Risiko-Daten verfügbar',

  // Chart
  trendTitle: 'Risiko-Trend (30 Tage)',
  scoreLabel: 'Score',
  countLabel: 'Anzahl',
};
