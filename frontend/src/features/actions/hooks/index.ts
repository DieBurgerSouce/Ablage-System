/**
 * Actions Hooks - Barrel Export
 * Phase 2.2 der Feature-Roadmap (Januar 2026)
 */

export {
  // Query Keys
  predictiveActionsQueryKeys,
  // Query Hooks
  usePredictiveActions,
  useCriticalActions,
  useSkontoActions,
  useDunningActions,
  useActionStatistics,
  useActionTypes,
  // Mutation Hooks
  useAcceptAction,
  useRejectAction,
  useSnoozeAction,
  // Utility Hooks
  useInvalidatePredictiveActionsQueries,
  usePrefetchCriticalActions,
} from './use-predictive-actions';
