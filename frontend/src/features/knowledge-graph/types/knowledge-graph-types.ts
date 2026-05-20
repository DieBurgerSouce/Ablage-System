/**
 * Knowledge Graph Types
 * Typdefinitionen für die Wissens-Graph-Visualisierung
 */

export type NodeType = 'entity' | 'document' | 'invoice' | 'transaction' | 'payment';
export type EdgeType = 'CONTAINS_DOCUMENT' | 'ISSUED_TO' | 'PAID_VIA' | 'REFERENCES' | 'LINKED_TO';

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: EdgeType;
  label: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SearchResult {
  id: string;
  type: NodeType;
  label: string;
  score: number;
}

export interface GraphCommunity {
  id: string;
  name: string;
  members: Array<{ id: string; type: NodeType; label: string }>;
  size: number;
}

export interface NodePosition {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface GraphViewport {
  zoom: number;
  panX: number;
  panY: number;
}

// =============================================================================
// Phase B: Extended Types
// =============================================================================

// View modes
export type ViewMode = 'graph' | 'financial' | 'timeline' | 'risk' | 'family';

// Extended edge types (13 relation types)
export type RelationType =
  | 'CONTAINS_DOCUMENT'
  | 'ISSUED_TO'
  | 'PAID_VIA'
  | 'REFERENCES'
  | 'LINKED_TO'
  | 'BASED_ON'
  | 'MATCHED_WITH'
  | 'PARENT_OF'
  | 'DERIVED_FROM'
  | 'SUPERSEDES'
  | 'CORRECTS'
  | 'DUNNING_FOR'
  | 'PARTIAL_PAYMENT';

// Financial chain types
export interface FinancialChainStage {
  stage: 'order' | 'delivery' | 'invoice' | 'payment' | 'dunning';
  label: string;
  documents: GraphNode[];
}

export interface FinancialChainData {
  entityId: string;
  entityName: string;
  stages: FinancialChainStage[];
  matchStatus: 'full' | 'partial' | 'none';
  totalAmount: number;
}

// Timeline types
export interface TimelineEvent {
  id: string;
  timestamp: string;
  eventType: string;
  description: string;
  documentId?: string;
  documentName?: string;
  metadata: Record<string, unknown>;
}

export interface TimelineData {
  events: TimelineEvent[];
  totalCount: number;
}

// Risk network types
export interface RiskNodeData {
  entityId: string;
  entityName: string;
  riskScore: number;
  transactionVolume: number;
  communityId: string;
  paymentBehaviorScore: number;
  industryRisk: number;
  lastAnomaly?: string;
}

export interface RiskNetworkData {
  nodes: RiskNodeData[];
  edges: Array<{
    source: string;
    target: string;
    transactionCount: number;
  }>;
  communities: Array<{
    id: string;
    name: string;
    memberIds: string[];
  }>;
}

// Document family types
export interface DocumentFamilyData {
  rootDocument: GraphNode;
  groups: Array<{
    ring: number;
    label: string;
    documents: GraphNode[];
  }>;
  unlinkedCount: number;
}

// Graph filter state
export interface GraphFilterState {
  viewMode: ViewMode;
  edgeFilter: string[];
  confidenceMin: number;
  depth: number;
}
