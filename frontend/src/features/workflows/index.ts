/**
 * Workflows Feature
 *
 * Visual Workflow Automation für Dokumentverarbeitung.
 *
 * Features:
 * - ReactFlow Visual Editor für Workflow-Erstellung
 * - Trigger-Typen: Dokument-Events, Zeitplaene, Webhooks, Manuell
 * - 20+ Aktionstypen für Dokumentverarbeitung
 * - Bedingungen, Verzweigungen, Schleifen, Parallele Ausführung
 * - Ausführungs-Historie und Statistiken
 * - Template-Galerie für Schnellstart
 */

// Components
export {
  WorkflowBuilder,
  WorkflowBuilderEnhanced,
  WorkflowsList,
  WorkflowExecutionHistory,
  WorkflowTemplates,
  WorkflowStats,
  NodePalette,
  NodeConfigPanel,
  nodeTemplates,
  nodeTypes,
  TriggerNode,
  ConditionNode,
  ActionNode,
  BranchNode,
  DelayNode,
  ParallelNode,
  LoopNode,
} from './components';

// Component Types
export type { NodeTemplate } from './components';

// Hooks
export {
  useWorkflows,
  useWorkflow,
  useCreateWorkflow,
  useUpdateWorkflow,
  useDeleteWorkflow,
  useDuplicateWorkflow,
  useToggleWorkflow,
  useValidateWorkflow,
  useWorkflowSteps,
  useCreateStep,
  useUpdateStep,
  useDeleteStep,
  useReorderSteps,
  useExecuteWorkflow,
  useWorkflowExecutions,
  useExecution,
  useStepExecutions,
  usePauseExecution,
  useResumeExecution,
  useCancelExecution,
  useRetryExecution,
  useTemplates,
  useTemplate,
  useInstantiateTemplate,
  useWebhookConfig,
  useRegenerateWebhookSecret,
  useWorkflowStats,
  useOverviewStats,
  useExecutionHistory,
  useAvailableOperators,
  useAvailableFields,
  workflowKeys,
} from './hooks/useWorkflows';

// API Functions
export * from './api/workflows-api';

// Types
export type {
  TriggerType,
  StepType,
  ExecutionStatus,
  ActionType,
  Workflow,
  WorkflowCreate,
  WorkflowUpdate,
  WorkflowNode,
  WorkflowEdge,
  TriggerConfig,
  RetryConfig,
  WorkflowStep,
  StepConfig,
  StepCreate,
  StepUpdate,
  StepReorderItem,
  ConditionGroup,
  ConditionRule,
  ConditionOperator,
  Branch,
  WorkflowExecution,
  StepExecution,
  ExecutionStart,
  WorkflowListResponse,
  ExecutionListResponse,
  ValidationResult,
  WorkflowStats as WorkflowStatsType,
  OverviewStats,
  ExecutionHistoryItem,
  WebhookConfig,
  OperatorInfo,
  WorkflowListParams,
  ExecutionListParams,
} from './types/workflow-types';
