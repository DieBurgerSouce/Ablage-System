/**
 * Workflows Feature
 *
 * Visual Workflow Automation fuer Dokumentverarbeitung.
 *
 * Features:
 * - ReactFlow Visual Editor fuer Workflow-Erstellung
 * - Trigger-Typen: Dokument-Events, Zeitplaene, Webhooks, Manuell
 * - 20+ Aktionstypen fuer Dokumentverarbeitung
 * - Bedingungen, Verzweigungen, Schleifen, Parallele Ausfuehrung
 * - Ausfuehrungs-Historie und Statistiken
 * - Template-Galerie fuer Schnellstart
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
