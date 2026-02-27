/**
 * Business Rules Types
 *
 * TypeScript-Definitionen für das Business Rules System.
 */

export type ConditionOperator =
  | '=='
  | '!='
  | '>'
  | '>='
  | '<'
  | '<='
  | 'eq'
  | 'ne'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'matches'
  | 'regex'
  | 'in'
  | 'not_in'
  | 'is_empty'
  | 'is_not_empty'
  | 'is_null'
  | 'is_not_null'
  | 'is_true'
  | 'is_false'
  | 'in_period'
  | 'before'
  | 'after'
  | 'before_date'
  | 'after_date'
  | 'between'
  | 'is_weekend'
  | 'is_month_end'
  | 'is_quarter_end'
  | 'is_year_end'
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
  | 'send_notification'
  | 'assign_category'
  | 'assign_workflow'
  | 'trigger_webhook'
  | 'log_event'
  | 'set_metadata'
  | 'require_review'
  | 'auto_approve'
  | 'escalate'

export type RuleCategory =
  | 'approval'
  | 'compliance'
  | 'fraud'
  | 'workflow'
  | 'notification'
  | 'assignment'
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

/**
 * Regel-Vorlage fuer die Template-Galerie
 */
export interface RuleTemplate {
  id: string
  name: string
  description: string
  category: RuleCategory
  condition: RuleCondition
  actions: RuleAction[]
  else_actions?: RuleAction[]
  priority: number
}

/**
 * Deutsche Labels fuer Kategorien
 */
export const CATEGORY_LABELS: Record<RuleCategory, string> = {
  approval: 'Genehmigung',
  compliance: 'Compliance',
  fraud: 'Betrugs-Erkennung',
  workflow: 'Workflow',
  notification: 'Benachrichtigung',
  assignment: 'Zuweisung',
  data_quality: 'Datenqualitaet',
  custom: 'Benutzerdefiniert',
}

/**
 * Deutsche Labels fuer Operatoren
 */
export const OPERATOR_LABELS: Record<string, string> = {
  '==': 'gleich',
  '!=': 'ungleich',
  '>': 'groesser als',
  '>=': 'groesser oder gleich',
  '<': 'kleiner als',
  '<=': 'kleiner oder gleich',
  eq: 'gleich',
  ne: 'ungleich',
  gt: 'groesser als',
  gte: 'groesser oder gleich',
  lt: 'kleiner als',
  lte: 'kleiner oder gleich',
  contains: 'enthaelt',
  not_contains: 'enthaelt nicht',
  starts_with: 'beginnt mit',
  ends_with: 'endet mit',
  matches: 'Regex-Match',
  regex: 'Regex-Muster',
  in: 'in Liste',
  not_in: 'nicht in Liste',
  is_empty: 'ist leer',
  is_not_empty: 'ist nicht leer',
  is_null: 'ist null',
  is_not_null: 'existiert',
  is_true: 'ist wahr',
  is_false: 'ist falsch',
  in_period: 'in Periode',
  before: 'vor Datum',
  after: 'nach Datum',
  before_date: 'vor Datum',
  after_date: 'nach Datum',
  between: 'zwischen',
  is_weekend: 'ist Wochenende',
  is_month_end: 'ist Monatsende',
  is_quarter_end: 'ist Quartalsende',
  is_year_end: 'ist Jahresende',
  has_tag: 'hat Tag',
  has_any_tag: 'hat einen der Tags',
  has_all_tags: 'hat alle Tags',
}

/**
 * Deutsche Labels fuer Aktionstypen
 */
export const ACTION_TYPE_LABELS: Record<string, string> = {
  require_approval: 'Genehmigung erforderlich',
  require_cfo_approval: 'CFO-Genehmigung',
  require_manager_approval: 'Manager-Genehmigung',
  set_flag: 'Flag setzen',
  remove_flag: 'Flag entfernen',
  set_status: 'Status setzen',
  set_priority: 'Prioritaet setzen',
  notify_user: 'Benutzer benachrichtigen',
  notify_team: 'Team benachrichtigen',
  notify_admin: 'Admin benachrichtigen',
  send_email: 'E-Mail senden',
  send_slack: 'Slack-Nachricht',
  send_notification: 'Benachrichtigung senden',
  start_workflow: 'Workflow starten',
  assign_to_user: 'Benutzer zuweisen',
  assign_to_team: 'Team zuweisen',
  assign_category: 'Kategorie zuweisen',
  assign_workflow: 'Workflow zuweisen',
  set_field: 'Feld setzen',
  set_metadata: 'Metadaten setzen',
  add_tag: 'Tag hinzufuegen',
  remove_tag: 'Tag entfernen',
  add_comment: 'Kommentar hinzufuegen',
  trigger_ocr: 'OCR ausloesen',
  trigger_webhook: 'Webhook ausloesen',
  log_event: 'Ereignis protokollieren',
  flag_for_review: 'Zur Pruefung markieren',
  require_review: 'Pruefung erforderlich',
  manual_review_required: 'Manuelle Pruefung',
  auto_approve: 'Automatisch genehmigen',
  escalate: 'Eskalieren',
  block_processing: 'Verarbeitung blockieren',
  flag_for_archive: 'Zur Archivierung markieren',
  flag_for_period_close: 'Fuer Periodenabschluss',
}
