/**
 * Business Rules Types
 *
 * TypeScript-Definitionen fuer das Business Rules System.
 */

export type ConditionOperator =
  | '=='
  | '!='
  | '>'
  | '>='
  | '<'
  | '<='
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'matches'
  | 'in'
  | 'not_in'
  | 'is_empty'
  | 'is_not_empty'
  | 'is_null'
  | 'is_not_null'
  | 'in_period'
  | 'before'
  | 'after'
  | 'between'
  | 'has_tag'
  | 'has_any_tag'
  | 'has_all_tags'

export type ActionType =
  | 'require_approval'
  | 'require_cfo_approval'
  | 'require_manager_approval'
  | 'set_flag'
  | 'remove_flag'
  | 'set_status'
  | 'set_priority'
  | 'notify_user'
  | 'notify_team'
  | 'notify_admin'
  | 'send_email'
  | 'send_slack'
  | 'start_workflow'
  | 'assign_to_user'
  | 'assign_to_team'
  | 'set_field'
  | 'add_tag'
  | 'remove_tag'
  | 'add_comment'
  | 'trigger_ocr'
  | 'flag_for_review'
  | 'manual_review_required'
  | 'block_processing'
  | 'flag_for_archive'
  | 'flag_for_period_close'

export type RuleCategory =
  | 'approval'
  | 'compliance'
  | 'fraud'
  | 'workflow'
  | 'notification'
  | 'data_quality'
  | 'custom'

export interface SimpleCondition {
  field: string
  op: ConditionOperator
  value?: unknown
  case_sensitive?: boolean
  negate?: boolean
}

export interface CompositeCondition {
  and?: Array<SimpleCondition | CompositeCondition>
  or?: Array<SimpleCondition | CompositeCondition>
  not?: SimpleCondition | CompositeCondition
}

export type RuleCondition = SimpleCondition | CompositeCondition

export interface RuleAction {
  type: ActionType
  params: Record<string, unknown>
}

export interface BusinessRule {
  id: string
  name: string
  description: string | null
  code: string | null
  condition: RuleCondition
  actions: RuleAction[]
  else_actions: RuleAction[] | null
  priority: number
  category: RuleCategory
  is_active: boolean
  stop_on_match: boolean
  applies_to_document_types: string[] | null
  applies_to_sources: string[] | null
  valid_from: string | null
  valid_until: string | null
  execution_count: number
  match_count: number
  last_executed_at: string | null
  last_matched_at: string | null
  created_by_id: string | null
  created_at: string
  updated_at: string
}

export interface RuleListResponse {
  items: BusinessRule[]
  total: number
  limit: number
  offset: number
}

export interface RuleCreateRequest {
  name: string
  description?: string
  code?: string
  condition: RuleCondition
  actions: RuleAction[]
  else_actions?: RuleAction[]
  priority?: number
  category?: RuleCategory
  is_active?: boolean
  stop_on_match?: boolean
  applies_to_document_types?: string[]
  applies_to_sources?: string[]
  valid_from?: string
  valid_until?: string
}

export interface RuleUpdateRequest extends Partial<RuleCreateRequest> {}

export interface RuleTestRequest {
  condition: RuleCondition
  actions: RuleAction[]
  else_actions?: RuleAction[]
  context: Record<string, unknown>
}

export interface RuleTestResponse {
  matched: boolean
  condition_details: Record<string, unknown>
  would_trigger_actions: RuleAction[]
  context_used: Record<string, unknown>
}

export interface OperatorInfo {
  value: ConditionOperator
  name: string
  description: string
}

export interface ActionTypeInfo {
  value: ActionType
  name: string
  description: string
}

export interface OperatorsResponse {
  operators: OperatorInfo[]
  action_types: ActionTypeInfo[]
  categories: string[]
}

export interface ExecutionLog {
  id: string
  rule_id: string
  document_id: string | null
  matched: boolean
  condition_details: Record<string, unknown>
  triggered_actions: RuleAction[]
  execution_errors: string[]
  dry_run: boolean
  executed_at: string
  execution_time_ms: number | null
}
