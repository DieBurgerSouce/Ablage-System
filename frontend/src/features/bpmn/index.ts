/**
 * BPMN Process Engine Feature
 *
 * Enterprise-Grade BPMN 2.0 Process Engine mit visuellem Editor.
 *
 * Features:
 * - BPMN 2.0 konformer Prozess-Designer (React Flow)
 * - Drag & Drop Element-Palette
 * - Properties Panel fuer Element-Konfiguration
 * - Prozess-Definition Deployment & Versionierung
 * - Prozess-Instanz Management
 * - Task Inbox & Bearbeitung
 * - Timer & Ereignis-Verarbeitung
 * - Ausfuehrungs-Historie & Monitoring
 */

// Components
export {
  BpmnEditor,
  BpmnPalette,
  BpmnPropertiesPanel,
  bpmnNodeTypes,
  StartEventNode,
  EndEventNode,
  TaskNode,
  GatewayNode,
} from './components';

// Hooks
export {
  // Query Keys
  bpmnKeys,
  // Definition Hooks
  useDefinitions,
  useDefinition,
  useDefinitionByKey,
  useDefinitionStatistics,
  useCreateDefinition,
  useDeployDefinition,
  useActivateDefinition,
  useDeactivateDefinition,
  useExportDefinitionBpmn,
  // Instance Hooks
  useInstances,
  useInstance,
  useInstanceHistory,
  useInstanceVariables,
  useStartInstance,
  useSignalInstance,
  useSuspendInstance,
  useResumeInstance,
  useTerminateInstance,
  useSetInstanceVariable,
  // Task Hooks
  useTasks,
  useMyTasks,
  useGroupTasks,
  useTask,
  useTaskStatistics,
  useClaimTask,
  useUnclaimTask,
  useStartTask,
  useCompleteTask,
  useDelegateTask,
  useEscalateTask,
  // Timer Hooks
  useTimers,
  useTimerStatistics,
  useCancelTimer,
} from './hooks/useBpmn';

// API Functions
export * from './api/bpmn-api';

// Types
export type {
  // Enums
  ProcessStatus,
  TaskStatus,
  TaskType,
  GatewayType,
  EventType,
  EventTrigger,
  // Definition Types
  ProcessDefinition,
  BPMNProcessData,
  BPMNElement,
  BPMNElementType,
  BPMNFlow,
  // Instance Types
  ProcessInstance,
  ProcessInstanceCreate,
  // Task Types
  ProcessTask,
  TaskComplete,
  TaskClaim,
  TaskDelegate,
  // History & Timer Types
  ProcessHistory,
  ProcessTimer,
  // Statistics Types
  DefinitionStatistics,
  TaskStatistics,
  TimerStatistics,
  // Request/Response Types
  ProcessDefinitionCreate,
  ProcessDefinitionUpdate,
  ProcessDefinitionListParams,
  ProcessInstanceListParams,
  TaskListParams,
  // React Flow Types
  BPMNNodeData,
  BPMNEdgeData,
} from './types/bpmn-types';
