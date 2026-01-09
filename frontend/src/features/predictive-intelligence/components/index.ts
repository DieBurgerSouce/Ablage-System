/**
 * Predictive Intelligence Components.
 *
 * Exportiert alle KI-basierten Komponenten fuer
 * Vorhersagen, Anomalie-Erkennung und semantische Suche.
 */

export { default as PredictiveInsights } from './PredictiveInsights';
export type {
  CashFlowPrediction,
  UpcomingDeadline,
  MaintenancePrediction,
  CostTrend,
} from './PredictiveInsights';

export { default as AnomalyAlerts } from './AnomalyAlerts';
export type { Anomaly, AnomalyType, AnomalySeverity, AnomalyStatus } from './AnomalyAlerts';

export { default as SmartSearch } from './SmartSearch';
export type { EntityType, SearchResult, SearchSuggestion } from './SmartSearch';
