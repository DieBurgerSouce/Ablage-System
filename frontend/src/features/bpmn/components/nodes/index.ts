/**
 * BPMN Node Components
 *
 * Export all BPMN node components for React Flow.
 */

export { StartEventNode, default as StartEventNodeDefault } from './StartEventNode';
export { EndEventNode, default as EndEventNodeDefault } from './EndEventNode';
export { TaskNode, default as TaskNodeDefault } from './TaskNode';
export { GatewayNode, default as GatewayNodeDefault } from './GatewayNode';

import type { NodeTypes } from 'reactflow';
import { StartEventNode } from './StartEventNode';
import { EndEventNode } from './EndEventNode';
import { TaskNode } from './TaskNode';
import { GatewayNode } from './GatewayNode';

/**
 * Node types mapping for React Flow
 */
export const bpmnNodeTypes: NodeTypes = {
  // Events
  startEvent: StartEventNode,
  endEvent: EndEventNode,
  intermediateThrowEvent: StartEventNode, // Use similar styling
  intermediateCatchEvent: EndEventNode, // Use similar styling
  boundaryEvent: EndEventNode,
  // Tasks
  userTask: TaskNode,
  serviceTask: TaskNode,
  scriptTask: TaskNode,
  manualTask: TaskNode,
  sendTask: TaskNode,
  receiveTask: TaskNode,
  businessRuleTask: TaskNode,
  // Gateways
  exclusiveGateway: GatewayNode,
  parallelGateway: GatewayNode,
  inclusiveGateway: GatewayNode,
  eventBasedGateway: GatewayNode,
  complexGateway: GatewayNode,
};

/**
 * Default node dimensions for layout
 */
export const nodeDefaults = {
  startEvent: { width: 48, height: 48 },
  endEvent: { width: 48, height: 48 },
  userTask: { width: 160, height: 60 },
  serviceTask: { width: 160, height: 60 },
  scriptTask: { width: 160, height: 60 },
  exclusiveGateway: { width: 48, height: 48 },
  parallelGateway: { width: 48, height: 48 },
  inclusiveGateway: { width: 48, height: 48 },
};
