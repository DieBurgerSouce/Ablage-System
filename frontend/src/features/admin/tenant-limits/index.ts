/**
 * Tenant Limits Feature Module
 *
 * Multi-Tenant Rate Limiting Dashboard und Verwaltung.
 */

// Page
export { TenantMetricsDashboard } from './TenantMetricsDashboard';

// Hooks
export {
  useOwnLimits,
  useCompanyLimits,
  useUsageMetrics,
  useViolations,
  useUpdateLimit,
  useResetLimits,
  tenantLimitKeys,
} from './hooks/use-tenant-limits';
export type {
  TierDefaultsResponse,
  CustomLimitResponse,
  CompanyLimitsResponse,
  UsageSummaryResponse,
  UsageTimelineItem,
  ViolationResponse,
  UpdateLimitRequest,
} from './hooks/use-tenant-limits';

// Components
export { LimitsCard } from './components/LimitsCard';
export { UsageChart } from './components/UsageChart';
export { ViolationsTable } from './components/ViolationsTable';
export { StatsCards } from './components/StatsCards';
