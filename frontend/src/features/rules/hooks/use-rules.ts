/**
 * Business Rules TanStack Query Hooks
 *
 * Re-Exports aus dem Admin-Rules-Modul.
 * Canonical source: features/admin/rules/api.ts
 */

export {
  useRulesList as useRules,
  useRule,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  useTestRule,
  useOperators,
  useExecutionLogs,
  useGenerateRule,
} from '@/features/admin/rules/api'
