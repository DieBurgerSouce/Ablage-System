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
