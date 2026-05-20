/**
 * Business Rules Feature
 *
 * Public API fuer das Rule Builder Feature.
 * Canonical implementation: features/admin/rules/
 */

// Components
export {
  RuleBuilderView,
  RuleTable,
  RuleFormDialog,
  ConditionBuilder,
  ActionBuilder,
  AIRuleGenerator,
  RuleTestPanel,
  RuleTemplateGallery,
} from './components'

// Hooks
export {
  useRules,
  useRule,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  useTestRule,
  useOperators,
  useExecutionLogs,
} from './hooks/use-rules'

// Types
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
  RuleTemplate,
} from './types/rules.types'

export {
  CATEGORY_LABELS,
  OPERATOR_LABELS,
  ACTION_TYPE_LABELS,
} from './types/rules.types'
