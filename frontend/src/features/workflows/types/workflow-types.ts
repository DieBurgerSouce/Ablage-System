/**
 * Workflow Automation Types
 *
 * TypeScript-Definitionen fuer Workflow-Automation.
 */

// =============================================================================
// Workflow Types
// =============================================================================

export type TriggerType =
  | 'document_event'
  | 'schedule'
  | 'condition'
  | 'manual'
  | 'webhook';

export type StepType =
  | 'condition'
  | 'action'
  | 'branch'
  | 'delay'
  | 'parallel'
  | 'loop';

export type ExecutionStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timeout';

export type ActionType =
  | 'move_folder'
  | 'assign_tags'
  | 'assign_document_type'
  | 'update_status'
  | 'delete_document'
  | 'send_notification'
  | 'send_email'
  | 'call_webhook'
  | 'http_request'
  | 'start_ocr'
  | 'ai_categorization'
  | 'export_document'
  | 'duplicate_check'
  | 'delay'
  | 'set_variable'
  | 'log_message'
  | 'assign_user'
  | 'create_task'
  | 'request_approval';

// =============================================================================
// ReactFlow Node Types
// =============================================================================

export interface WorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
}

// =============================================================================
// Workflow
// =============================================================================

export interface Workflow {
  id: string;
  user_id: string;
  company_id?: string | null;
  name: string;
  description?: string | null;
  trigger_type: TriggerType;
  trigger_config: TriggerConfig;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  variables: Record<string, unknown>;
  is_active: boolean;
  is_template: boolean;
  max_concurrent_executions: number;
  timeout_seconds: number;
  retry_config: RetryConfig;
  execution_count: number;
  last_executed_at?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface TriggerConfig {
  // Document Event Trigger
  events?: string[];
  document_types?: string[];
  file_extensions?: string[];
  folder_ids?: string[];

  // Schedule Trigger
  cron?: string;
  timezone?: string;

  // Webhook Trigger
  webhook_path?: string;
  webhook_secret?: string;

  // Condition Trigger
  watch_fields?: string[];

  // Common
  scope?: 'user' | 'global';
  allow_manual_trigger?: boolean;
  category?: string;

  [key: string]: unknown;
}

export interface RetryConfig {
  max_retries: number;
  retry_delay: number;
  exponential_backoff?: boolean;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  trigger_type: TriggerType;
  trigger_config: TriggerConfig;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
  variables?: Record<string, unknown>;
  max_concurrent_executions?: number;
  timeout_seconds?: number;
  retry_config?: RetryConfig;
}

export interface WorkflowUpdate {
  name?: string;
  description?: string;
  trigger_type?: TriggerType;
  trigger_config?: TriggerConfig;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
  variables?: Record<string, unknown>;
  is_active?: boolean;
  max_concurrent_executions?: number;
  timeout_seconds?: number;
  retry_config?: RetryConfig;
}

// =============================================================================
// Workflow Step
// =============================================================================

export interface WorkflowStep {
  id: string;
  workflow_id: string;
  step_order: number;
  step_type: StepType;
  step_name?: string | null;
  config: StepConfig;
  retry_on_failure: boolean;
  max_retries: number;
  position_x: number;
  position_y: number;
  created_at: string;
  updated_at?: string | null;
}

export interface StepConfig {
  // Action Step
  action_type?: ActionType;

  // Condition Step
  conditions?: ConditionGroup;

  // Branch Step
  branches?: Branch[];
  default_branch?: string;

  // Delay Step
  delay_seconds?: number;
  delay_until?: string;

  // Parallel Step
  steps?: string[];

  // Loop Step
  loop_type?: 'count' | 'while' | 'for_each';
  count?: number;
  max_iterations?: number;
  items_field?: string;

  // Action-specific
  folder_id?: string;
  tag_ids?: string[];
  tag_names?: string[];
  document_type?: string;
  status?: string;
  user_id?: string;
  user_ids?: string[];
  title?: string;
  message?: string;
  url?: string;
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  backend?: string;
  priority?: string;
  format?: string;
  destination?: string;
  name?: string;
  value?: unknown;
  level?: string;
  assignee_id?: string;
  due_date?: string;
  approver_ids?: string[];
  to?: string[];
  subject?: string;
  html_body?: string;
  template?: string;
  notification_type?: string;
  soft_delete?: boolean;
  append?: boolean;
  timeout?: number;
  event_type?: string;
  payload?: Record<string, unknown>;

  [key: string]: unknown;
}

export interface ConditionGroup {
  operator: 'AND' | 'OR';
  rules: (ConditionRule | ConditionGroup)[];
}

export interface ConditionRule {
  field: string;
  operator: ConditionOperator;
  value: unknown;
}

export type ConditionOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'regex'
  | 'greater_than'
  | 'greater_equal'
  | 'less_than'
  | 'less_equal'
  | 'in_list'
  | 'not_in_list'
  | 'is_empty'
  | 'is_not_empty'
  | 'is_null'
  | 'is_not_null'
  | 'is_true'
  | 'is_false'
  | 'changed'
  | 'changed_to'
  | 'changed_from';

export interface Branch {
  name: string;
  conditions: ConditionGroup;
}

export interface StepCreate {
  step_order: number;
  step_type: StepType;
  step_name?: string;
  config: StepConfig;
  retry_on_failure?: boolean;
  max_retries?: number;
  position_x?: number;
  position_y?: number;
}

export interface StepUpdate {
  step_order?: number;
  step_type?: StepType;
  step_name?: string;
  config?: StepConfig;
  retry_on_failure?: boolean;
  max_retries?: number;
  position_x?: number;
  position_y?: number;
}

export interface StepReorderItem {
  step_id: string;
  step_order: number;
}

// =============================================================================
// Workflow Execution
// =============================================================================

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  user_id: string;
  document_id?: string | null;
  status: ExecutionStatus;
  trigger_data: Record<string, unknown>;
  variables: Record<string, unknown>;
  current_step_id?: string | null;
  progress_percent: number;
  started_at: string;
  completed_at?: string | null;
  result?: Record<string, unknown> | null;
  error_message?: string | null;
}

export interface StepExecution {
  id: string;
  execution_id: string;
  step_id: string;
  status: ExecutionStatus;
  started_at: string;
  completed_at?: string | null;
  input_data?: Record<string, unknown> | null;
  output_data?: Record<string, unknown> | null;
  error_message?: string | null;
}

export interface ExecutionStart {
  document_id?: string;
  variables?: Record<string, unknown>;
}

// =============================================================================
// API Responses
// =============================================================================

export interface WorkflowListResponse {
  items: Workflow[];
  total: number;
  offset: number;
  limit: number;
}

export interface ExecutionListResponse {
  items: WorkflowExecution[];
  total: number;
  offset: number;
  limit: number;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface WorkflowStats {
  workflow_id: string;
  name: string;
  is_active: boolean;
  execution_count: number;
  last_executed_at?: string | null;
  statistics: {
    total_executions: number;
    completed: number;
    failed: number;
    success_rate: number;
    avg_duration_seconds: number;
  };
}

export interface OverviewStats {
  total_workflows: number;
  active_workflows: number;
  total_executions: number;
  executions_today: number;
  success_rate: number;
}

export interface ExecutionHistoryItem {
  date: string;
  total: number;
  completed: number;
  failed: number;
}

export interface WebhookConfig {
  webhook_path: string;
  webhook_url: string;
  has_secret: boolean;
}

export interface OperatorInfo {
  id: string;
  name: string;
  description: string;
}

// =============================================================================
// Query Parameters
// =============================================================================

export interface WorkflowListParams {
  trigger_type?: TriggerType;
  is_active?: boolean;
  is_template?: boolean;
  search?: string;
  offset?: number;
  limit?: number;
}

export interface ExecutionListParams {
  status?: ExecutionStatus;
  offset?: number;
  limit?: number;
}
