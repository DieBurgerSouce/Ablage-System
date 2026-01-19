/**
 * Risk Intelligence Feature Module
 *
 * Erweiterte Risikoanalyse mit Branchen-Benchmarks, Trends und Netzwerk-Analyse.
 */

// Main Dashboard
export { RiskIntelligenceDashboard } from './RiskIntelligenceDashboard';

// Components
export { RiskScoreGauge } from './components/RiskScoreGauge';
export { TrendChart } from './components/TrendChart';
export { BenchmarkComparison } from './components/BenchmarkComparison';
export { NetworkGraph } from './components/NetworkGraph';
export { PortfolioOverview } from './components/PortfolioOverview';
export { RecommendationsList } from './components/RecommendationsList';
export { ExternalSourcesCard } from './components/ExternalSourcesCard';

// Hooks
export {
  useEntityRiskProfile,
  useEntityTrend,
  useEntityBenchmark,
  useEntityNetwork,
  useExternalSourceCheck,
  usePortfolioRisk,
  useIndustryBenchmarks,
  useTrendDirections,
  useExternalSources,
  useRefreshRiskProfile,
  riskIntelligenceKeys,
} from './hooks/use-risk-intelligence';

// API
export {
  getEntityRiskProfile,
  getEntityTrend,
  getEntityBenchmark,
  getEntityNetwork,
  checkExternalSources,
  getPortfolioRisk,
  getIndustryBenchmarks,
  getTrendDirections,
  getExternalSources,
} from './api/risk-intelligence-api';

// Types
export type {
  TrendAnalysis,
  BenchmarkComparison as BenchmarkComparisonType,
  NetworkConnection,
  NetworkAnalysis,
  Recommendation,
  RiskProfile,
  PortfolioRiskOverview,
  ExternalSourceCheck,
  IndustryBenchmark,
  TrendDirection,
  ExternalSource,
} from './api/risk-intelligence-api';
