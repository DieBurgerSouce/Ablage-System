/**
 * Business Rules Types
 *
 * Re-Exports aus dem Admin-Rules-Modul.
 * Canonical source: features/admin/rules/types.ts
 */

export type {
  ConditionOperator,
  ActionType,
  RuleCategory,
  SimpleCondition,
  CompositeCondition,
  RuleCondition,
  RuleAction,
  BusinessRule,
  RuleListResponse,
  RuleCreateRequest,
  RuleUpdateRequest,
  RuleTestRequest,
  RuleTestResponse,
  OperatorInfo,
  ActionTypeInfo,
  OperatorsResponse,
  ExecutionLog,
  RuleTemplate,
} from '@/features/admin/rules/types'

export {
  CATEGORY_LABELS,
  OPERATOR_LABELS,
  ACTION_TYPE_LABELS,
} from '@/features/admin/rules/types'
