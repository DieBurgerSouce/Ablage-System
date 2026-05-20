/**
 * Finance Hooks - Barrel Export
 * Phase 2.1 der Feature-Roadmap (Januar 2026)
 */

export {
  // Query Keys
  budgetQueryKeys,
  // Kostenstellen
  useKostenstellen,
  useKostenstellenTree,
  useCreateKostenstelle,
  // Budgets
  useBudgets,
  useBudget,
  useBudgetSummary,
  useCreateBudget,
  useActivateBudget,
  useCloseBudget,
  // Budget Lines
  useBudgetLines,
  useCreateBudgetLine,
  // Allocations
  useAllocations,
  useCreateAllocation,
  // Variance Report
  useVarianceReport,
  // Alerts
  useBudgetAlerts,
  useAcknowledgeAlert,
  // Utilities
  useInvalidateBudgetQueries,
} from './use-budget-queries';
