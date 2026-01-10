/**
 * Workflow Node Components
 *
 * Export aller ReactFlow Knoten fuer den WorkflowBuilder.
 */

import TriggerNodeComponent from './TriggerNode';
import ConditionNodeComponent from './ConditionNode';
import ActionNodeComponent from './ActionNode';
import BranchNodeComponent from './BranchNode';
import DelayNodeComponent from './DelayNode';
import ParallelNodeComponent from './ParallelNode';
import LoopNodeComponent from './LoopNode';

// Re-export components
export const TriggerNode = TriggerNodeComponent;
export const ConditionNode = ConditionNodeComponent;
export const ActionNode = ActionNodeComponent;
export const BranchNode = BranchNodeComponent;
export const DelayNode = DelayNodeComponent;
export const ParallelNode = ParallelNodeComponent;
export const LoopNode = LoopNodeComponent;

/**
 * Node Types Map fuer ReactFlow
 */
export const nodeTypes = {
  trigger: TriggerNodeComponent,
  condition: ConditionNodeComponent,
  action: ActionNodeComponent,
  branch: BranchNodeComponent,
  delay: DelayNodeComponent,
  parallel: ParallelNodeComponent,
  loop: LoopNodeComponent,
} as const;

export type NodeType = keyof typeof nodeTypes;
