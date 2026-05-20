/**
 * BPMN Process Engine Types
 *
 * TypeScript types for the BPMN 2.0 Process Engine.
 */

// =============================================================================
// Enums
// =============================================================================

export type ProcessStatus =
  | 'created'
  | 'running'
  | 'suspended'
  | 'completed'
  | 'terminated'
  | 'failed';

export type TaskStatus =
  | 'created'
  | 'ready'
  | 'reserved'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'skipped';

export type TaskType =
  | 'user_task'
  | 'service_task'
  | 'script_task'
  | 'manual_task'
  | 'send_task'
  | 'receive_task'
  | 'business_rule_task';

export type GatewayType =
  | 'exclusive'
  | 'parallel'
  | 'inclusive'
  | 'event_based'
  | 'complex';

export type EventType =
  | 'start'
  | 'end'
  | 'intermediate_catch'
  | 'intermediate_throw'
  | 'boundary';

export type EventTrigger =
  | 'none'
  | 'message'
  | 'timer'
  | 'error'
  | 'escalation'
  | 'cancel'
  | 'compensation'
  | 'signal'
  | 'terminate';

// =============================================================================
// Process Definition Types
// =============================================================================

export interface ProcessDefinition {
  id: string;
  company_id: string;
  process_key: string;
  name: string;
  description?: string;
  version: number;
  bpmn_xml?: string;
  process_data: BPMNProcessData;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by_id?: string;
}

export interface BPMNProcessData {
  id: string;
  name: string;
  elements: BPMNElement[];
  flows: BPMNFlow[];
  metadata?: Record<string, unknown>;
}

export interface BPMNElement {
  id: string;
  type: BPMNElementType;
  name?: string;
  description?: string;
  incoming?: string[];
  outgoing?: string[];
  properties?: Record<string, unknown>;
  // Position for React Flow
  position?: { x: number; y: number };
}

export type BPMNElementType =
  | 'startEvent'
  | 'endEvent'
  | 'intermediateThrowEvent'
  | 'intermediateCatchEvent'
  | 'boundaryEvent'
  | 'userTask'
  | 'serviceTask'
  | 'scriptTask'
  | 'manualTask'
  | 'sendTask'
  | 'receiveTask'
  | 'businessRuleTask'
  | 'exclusiveGateway'
  | 'parallelGateway'
  | 'inclusiveGateway'
  | 'eventBasedGateway'
  | 'complexGateway'
  | 'subProcess'
  | 'callActivity';

export interface BPMNFlow {
  id: string;
  source: string;
  target: string;
  name?: string;
  condition?: string;
}

// =============================================================================
// Process Instance Types
// =============================================================================

export interface ProcessInstance {
  id: string;
  definition_id: string;
  company_id: string;
  business_key?: string;
  status: ProcessStatus;
  started_at?: string;
  ended_at?: string;
  variables: Record<string, unknown>;
  current_elements: string[];
  started_by_id?: string;
  correlation_id?: string;
}

export interface ProcessInstanceCreate {
  definition_id?: string;
  process_key?: string;
  business_key?: string;
  variables?: Record<string, unknown>;
}

// =============================================================================
// Task Types
// =============================================================================

export interface ProcessTask {
  id: string;
  instance_id: string;
  company_id: string;
  element_id: string;
  element_name?: string;
  task_type: TaskType;
  status: TaskStatus;
  assignee_id?: string;
  candidate_groups?: string[];
  candidate_users?: string[];
  priority: number;
  due_date?: string;
  follow_up_date?: string;
  form_key?: string;
  task_variables: Record<string, unknown>;
  created_at: string;
  claimed_at?: string;
  started_at?: string;
  completed_at?: string;
  escalated_at?: string;
  escalation_level: number;
}

export interface TaskComplete {
  variables?: Record<string, unknown>;
}

export interface TaskClaim {
  assignee_id?: string;
}

export interface TaskDelegate {
  target_user_id: string;
  comment?: string;
}

// =============================================================================
// History Types
// =============================================================================

export interface ProcessHistory {
  id: string;
  instance_id: string;
  event_type: string;
  element_id?: string;
  message?: string;
  old_status?: string;
  new_status?: string;
  actor_id?: string;
  actor_type: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

// =============================================================================
// Timer Types
// =============================================================================

export interface ProcessTimer {
  id: string;
  instance_id: string;
  company_id: string;
  element_id: string;
  timer_type: 'date' | 'duration' | 'cycle';
  timer_value: string;
  due_at: string;
  is_active: boolean;
  repeat_count?: number;
  last_executed_at?: string;
  created_at: string;
}

// =============================================================================
// Statistics Types
// =============================================================================

export interface DefinitionStatistics {
  total_definitions: number;
  active_definitions: number;
  total_instances: number;
  by_status: Record<ProcessStatus, number>;
}

export interface TaskStatistics {
  total: number;
  by_status: Record<TaskStatus, number>;
  by_type: Record<TaskType, number>;
  overdue: number;
  avg_completion_time_hours?: number;
}

export interface TimerStatistics {
  active: number;
  due: number;
  by_type: Record<string, number>;
}

// =============================================================================
// API Request/Response Types
// =============================================================================

export interface ProcessDefinitionCreate {
  process_key: string;
  name: string;
  description?: string;
  bpmn_xml?: string;
  process_data?: BPMNProcessData;
  activate?: boolean;
}

export interface ProcessDefinitionUpdate {
  name?: string;
  description?: string;
  bpmn_xml?: string;
  process_data?: BPMNProcessData;
}

export interface ProcessDefinitionListParams {
  include_inactive?: boolean;
  page?: number;
  page_size?: number;
}

export interface ProcessInstanceListParams {
  definition_id?: string;
  status?: ProcessStatus;
  business_key?: string;
  page?: number;
  page_size?: number;
}

export interface TaskListParams {
  status?: TaskStatus;
  assignee_id?: string;
  unassigned?: boolean;
  page?: number;
  page_size?: number;
}

// =============================================================================
// React Flow Node Types
// =============================================================================

export interface BPMNNodeData {
  element: BPMNElement;
  label: string;
  type: BPMNElementType;
  isSelected?: boolean;
  onDelete?: () => void;
  onConfigure?: () => void;
}

export interface BPMNEdgeData {
  flow: BPMNFlow;
  label?: string;
  condition?: string;
}
