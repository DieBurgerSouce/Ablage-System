/**
 * Workflow Node Components
 *
 * Export aller ReactFlow Knoten fuer den WorkflowBuilder.
 */

export { default as TriggerNode } from './TriggerNode';
export { default as ConditionNode } from './ConditionNode';
export { default as ActionNode } from './ActionNode';
export { default as BranchNode } from './BranchNode';
export { default as DelayNode } from './DelayNode';
export { default as ParallelNode } from './ParallelNode';
export { default as LoopNode } from './LoopNode';

/**
 * Node Types Map fuer ReactFlow
 */
export const nodeTypes = {
  trigger: TriggerNode,
  condition: ConditionNode,
  action: ActionNode,
  branch: BranchNode,
  delay: DelayNode,
  parallel: ParallelNode,
  loop: LoopNode,
} as const;

export type NodeType = keyof typeof nodeTypes;
