/**
 * Executive Dashboard Feature
 *
 * Barrel exports for executive reporting feature.
 */

// Types
export type {
  KPIResponse,
  DepartmentBreakdown as DepartmentBreakdownData,
  TrendDataPoint,
  TrendResponse,
  ExecutiveSummaryResponse,
  TrendMetric,
} from './types/executive-types'

// API
export { getKPIs, getDepartments, getTrend, getSummary } from './api/executive-api'

// Hooks
export {
  useKPIs,
  useDepartments,
  useTrend,
  useExecutiveSummary,
  executiveKeys,
} from './hooks/useExecutiveData'

// Components
export { KPICard } from './components/KPICard'
export { TrendChart } from './components/TrendChart'
export { DepartmentBreakdown } from './components/DepartmentBreakdown'
export { ExportButton } from './components/ExportButton'
export { ExecutiveDashboard } from './components/ExecutiveDashboard'
