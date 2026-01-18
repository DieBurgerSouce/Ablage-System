/**
 * Supplier Ranking Types
 *
 * TypeScript Definitionen fuer das Lieferanten-Ranking System.
 */

// Ranking Kategorien
export type RankingCategory =
  | 'punctuality'
  | 'price'
  | 'reliability'
  | 'communication'
  | 'payment_terms';

// Supplier Tiers
export type SupplierTier = 'platinum' | 'gold' | 'silver' | 'bronze' | 'critical';

// Score Trend
export type ScoreTrend = 'improving' | 'declining' | 'stable';
export type CategoryTrend = 'up' | 'down' | 'stable';

// Kategorie-Gewichtungen
export const CATEGORY_WEIGHTS: Record<RankingCategory, number> = {
  punctuality: 0.30,
  price: 0.25,
  reliability: 0.25,
  communication: 0.10,
  payment_terms: 0.10,
};

// Kategorie-Labels (German)
export const CATEGORY_LABELS: Record<RankingCategory, string> = {
  punctuality: 'Puenktlichkeit',
  price: 'Preis-Leistung',
  reliability: 'Zuverlaessigkeit',
  communication: 'Kommunikation',
  payment_terms: 'Zahlungsbedingungen',
};

// Kategorie-Beschreibungen
export const CATEGORY_DESCRIPTIONS: Record<RankingCategory, string> = {
  punctuality: 'Liefertreue und termingerechte Rechnungsstellung',
  price: 'Preiskonsistenz und Skonto-Nutzung',
  reliability: 'Reklamationsquote und Qualitaet',
  communication: 'Dokumentenqualitaet und Erreichbarkeit',
  payment_terms: 'Zahlungsziele und Skonto-Angebote',
};

// Tier-Labels (German)
export const TIER_LABELS: Record<SupplierTier, string> = {
  platinum: 'Top-Lieferant',
  gold: 'Bevorzugter Lieferant',
  silver: 'Standard-Lieferant',
  bronze: 'Unter Beobachtung',
  critical: 'Kritischer Lieferant',
};

// Tier-Schwellenwerte
export const TIER_THRESHOLDS: Record<SupplierTier, { min: number; max: number }> = {
  platinum: { min: 90, max: 100 },
  gold: { min: 75, max: 89 },
  silver: { min: 60, max: 74 },
  bronze: { min: 40, max: 59 },
  critical: { min: 0, max: 39 },
};

// Tier-Farben
export const TIER_COLORS: Record<SupplierTier, { bg: string; text: string; border: string; icon: string }> = {
  platinum: {
    bg: 'bg-gradient-to-r from-violet-100 to-purple-100 dark:from-violet-900/30 dark:to-purple-900/30',
    text: 'text-violet-700 dark:text-violet-400',
    border: 'border-violet-500',
    icon: '🏆',
  },
  gold: {
    bg: 'bg-gradient-to-r from-amber-100 to-yellow-100 dark:from-amber-900/30 dark:to-yellow-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    border: 'border-amber-500',
    icon: '🥇',
  },
  silver: {
    bg: 'bg-gradient-to-r from-slate-100 to-gray-100 dark:from-slate-800/50 dark:to-gray-800/50',
    text: 'text-slate-700 dark:text-slate-400',
    border: 'border-slate-400',
    icon: '🥈',
  },
  bronze: {
    bg: 'bg-gradient-to-r from-orange-100 to-amber-100 dark:from-orange-900/30 dark:to-amber-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    border: 'border-orange-400',
    icon: '🥉',
  },
  critical: {
    bg: 'bg-gradient-to-r from-red-100 to-rose-100 dark:from-red-900/30 dark:to-rose-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500',
    icon: '⚠️',
  },
};

// Backend Response Types (snake_case)
export interface CategoryScoreResponse {
  category: string;
  category_label: string;
  score: number;
  weight: number;
  data_points: number;
  trend: string;
  details: Record<string, unknown>;
}

export interface SupplierRankingResponse {
  entity_id: string;
  entity_name: string;
  overall_score: number;
  tier: string;
  tier_label: string;
  category_scores: CategoryScoreResponse[];
  total_orders: number;
  total_volume: number;
  first_order_date: string | null;
  last_order_date: string | null;
  avg_order_value: number;
  score_trend: string;
  previous_score: number | null;
  recommendations: string[];
  calculated_at: string;
}

export interface TierDistributionResponse {
  platinum: number;
  gold: number;
  silver: number;
  bronze: number;
  critical: number;
}

export interface SupplierRankingReportResponse {
  company_id: string;
  total_suppliers: number;
  ranked_suppliers: number;
  tier_distribution: TierDistributionResponse;
  top_suppliers: SupplierRankingResponse[];
  critical_suppliers: SupplierRankingResponse[];
  improving_suppliers: SupplierRankingResponse[];
  declining_suppliers: SupplierRankingResponse[];
  avg_overall_score: number;
  avg_punctuality: number;
  avg_reliability: number;
  analysis_period_start: string;
  analysis_period_end: string;
  generated_at: string;
}

// Frontend Types (camelCase)
export interface CategoryScore {
  category: RankingCategory;
  categoryLabel: string;
  score: number;
  weight: number;
  dataPoints: number;
  trend: CategoryTrend;
  details: Record<string, unknown>;
}

export interface SupplierRanking {
  entityId: string;
  entityName: string;
  overallScore: number;
  tier: SupplierTier;
  tierLabel: string;
  categoryScores: CategoryScore[];
  totalOrders: number;
  totalVolume: number;
  firstOrderDate: Date | null;
  lastOrderDate: Date | null;
  avgOrderValue: number;
  scoreTrend: ScoreTrend;
  previousScore: number | null;
  recommendations: string[];
  calculatedAt: Date;
}

export interface TierDistribution {
  platinum: number;
  gold: number;
  silver: number;
  bronze: number;
  critical: number;
}

export interface SupplierRankingReport {
  companyId: string;
  totalSuppliers: number;
  rankedSuppliers: number;
  tierDistribution: TierDistribution;
  topSuppliers: SupplierRanking[];
  criticalSuppliers: SupplierRanking[];
  improvingSuppliers: SupplierRanking[];
  decliningSuppliers: SupplierRanking[];
  avgOverallScore: number;
  avgPunctuality: number;
  avgReliability: number;
  analysisPeriodStart: Date;
  analysisPeriodEnd: Date;
  generatedAt: Date;
}

// Transformer Functions
export function transformCategoryScore(response: CategoryScoreResponse): CategoryScore {
  return {
    category: response.category as RankingCategory,
    categoryLabel: response.category_label,
    score: response.score,
    weight: response.weight,
    dataPoints: response.data_points,
    trend: response.trend as CategoryTrend,
    details: response.details,
  };
}

export function getTierFromScore(score: number): SupplierTier {
  if (score >= TIER_THRESHOLDS.platinum.min) return 'platinum';
  if (score >= TIER_THRESHOLDS.gold.min) return 'gold';
  if (score >= TIER_THRESHOLDS.silver.min) return 'silver';
  if (score >= TIER_THRESHOLDS.bronze.min) return 'bronze';
  return 'critical';
}

export function transformSupplierRanking(response: SupplierRankingResponse): SupplierRanking {
  return {
    entityId: response.entity_id,
    entityName: response.entity_name,
    overallScore: response.overall_score,
    tier: response.tier as SupplierTier,
    tierLabel: response.tier_label,
    categoryScores: response.category_scores.map(transformCategoryScore),
    totalOrders: response.total_orders,
    totalVolume: response.total_volume,
    firstOrderDate: response.first_order_date ? new Date(response.first_order_date) : null,
    lastOrderDate: response.last_order_date ? new Date(response.last_order_date) : null,
    avgOrderValue: response.avg_order_value,
    scoreTrend: response.score_trend as ScoreTrend,
    previousScore: response.previous_score,
    recommendations: response.recommendations,
    calculatedAt: new Date(response.calculated_at),
  };
}

export function transformSupplierRankingReport(
  response: SupplierRankingReportResponse
): SupplierRankingReport {
  return {
    companyId: response.company_id,
    totalSuppliers: response.total_suppliers,
    rankedSuppliers: response.ranked_suppliers,
    tierDistribution: response.tier_distribution,
    topSuppliers: response.top_suppliers.map(transformSupplierRanking),
    criticalSuppliers: response.critical_suppliers.map(transformSupplierRanking),
    improvingSuppliers: response.improving_suppliers.map(transformSupplierRanking),
    decliningSuppliers: response.declining_suppliers.map(transformSupplierRanking),
    avgOverallScore: response.avg_overall_score,
    avgPunctuality: response.avg_punctuality,
    avgReliability: response.avg_reliability,
    analysisPeriodStart: new Date(response.analysis_period_start),
    analysisPeriodEnd: new Date(response.analysis_period_end),
    generatedAt: new Date(response.generated_at),
  };
}

// UI Labels
export const UI_LABELS = {
  pageTitle: 'Lieferanten-Ranking',
  pageSubtitle: 'Bewertung und Vergleich von Lieferanten',

  // Dashboard
  totalSuppliers: 'Gesamt Lieferanten',
  rankedSuppliers: 'Bewertete Lieferanten',
  avgScore: 'Durchschnitts-Score',
  tierDistribution: 'Tier-Verteilung',

  // Ranking
  overallScore: 'Gesamtscore',
  categoryScores: 'Kategorien',
  recommendations: 'Empfehlungen',

  // Table
  supplier: 'Lieferant',
  tier: 'Tier',
  score: 'Score',
  orders: 'Bestellungen',
  volume: 'Volumen',
  trend: 'Trend',
  lastOrder: 'Letzte Bestellung',

  // Actions
  compare: 'Vergleichen',
  viewDetails: 'Details anzeigen',
  exportReport: 'Report exportieren',

  // Filters
  filterByTier: 'Nach Tier filtern',
  allTiers: 'Alle Tiers',
  periodDays: 'Auswertungszeitraum',

  // Messages
  noSuppliers: 'Keine Lieferanten gefunden',
  errorLoad: 'Fehler beim Laden der Ranking-Daten',
  noData: 'Keine Ranking-Daten verfuegbar',
};
