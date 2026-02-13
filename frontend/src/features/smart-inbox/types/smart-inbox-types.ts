/**
 * Smart Inbox Types
 *
 * TypeScript Typen für Smart Inbox Feature.
 */

// ==================== Enums ====================

export type InboxStatus = 'pending' | 'in_progress' | 'completed' | 'dismissed';
export type InboxCategory =
  | 'invoice_overdue'
  | 'invoice_due_soon'
  | 'invoice_pending'
  | 'skonto_expiring'
  | 'document_needs_review'
  | 'entity_risk_high'
  | 'chain_incomplete'
  | 'shipment_delayed'
  | 'payment_received'
  | 'alert_critical'
  | 'alert_warning'
  | 'alert_info';

export type InboxSourceType =
  | 'invoice'
  | 'document'
  | 'entity'
  | 'chain'
  | 'shipment'
  | 'alert'
  | 'payment';

export type InboxActionType =
  | 'complete'
  | 'approve'
  | 'reject'
  | 'escalate'
  | 'review'
  | 'pay';

export type InsightTrend = 'up' | 'down' | 'stable';

// ==================== Recommended Action Types ====================

export interface RecommendedAction {
  action: InboxActionType;
  label: string;
  description: string;
  confidence: number;
  reasoning: string;
}

// ==================== Smart Inbox Item Types ====================

export interface SmartInboxItemBackend {
  id: string;
  source_type: InboxSourceType;
  source_id: string;
  title: string;
  description: string;
  category: InboxCategory;
  raw_priority: number;
  ml_priority: number;
  status: InboxStatus;
  deadline: string | null;
  recommended_actions: RecommendedAction[];
  context_data: Record<string, unknown>;
  document_id: string | null;
  entity_id: string | null;
  created_at: string;
}

export interface SmartInboxItemResponse {
  id: string;
  sourceType: InboxSourceType;
  sourceId: string;
  title: string;
  description: string;
  category: InboxCategory;
  rawPriority: number;
  mlPriority: number;
  status: InboxStatus;
  deadline: string | null;
  recommendedActions: RecommendedAction[];
  contextData: Record<string, unknown>;
  documentId: string | null;
  entityId: string | null;
  createdAt: string;
}

// ==================== Inbox List Response ====================

export interface InboxListResponseBackend {
  items: SmartInboxItemBackend[];
  total: number;
  has_more: boolean;
}

export interface InboxListResponse {
  items: SmartInboxItemResponse[];
  total: number;
  hasMore: boolean;
}

// ==================== Action Request ====================

export interface InboxActionRequest {
  action: InboxActionType;
  data?: Record<string, unknown>;
}

// ==================== Snooze Request ====================

export interface InboxSnoozeRequest {
  snoozeUntil: string;
}

// ==================== AI Insights Types ====================

export interface AIInsightBackend {
  title: string;
  description: string;
  metric: string;
  value: string | number;
  trend: InsightTrend;
}

export interface AIInsightResponse {
  title: string;
  description: string;
  metric: string;
  value: string | number;
  trend: InsightTrend;
}

export interface InsightsResponseBackend {
  insights: AIInsightBackend[];
}

export interface InsightsResponse {
  insights: AIInsightResponse[];
}

// ==================== Statistics Types ====================

export interface InboxStatsBackend {
  total: number;
  pending: number;
  in_progress: number;
  completed_today: number;
  dismissed_today: number;
  avg_response_time_ms: number;
  by_category: Record<InboxCategory, number>;
  by_source: Record<InboxSourceType, number>;
}

export interface InboxStatsResponse {
  total: number;
  pending: number;
  inProgress: number;
  completedToday: number;
  dismissedToday: number;
  avgResponseTimeMs: number;
  byCategory: Record<InboxCategory, number>;
  bySource: Record<InboxSourceType, number>;
}

// ==================== Aggregation Response ====================

export interface AggregationResponseBackend {
  message: string;
  task_id: string;
}

export interface AggregationResponse {
  message: string;
  taskId: string;
}

// ==================== Sort Types ====================

export type InboxSortBy = 'mlPriority' | 'deadline' | 'createdAt';

// ==================== Filter Types ====================

export interface InboxFilter {
  limit?: number;
  offset?: number;
  status?: InboxStatus;
  category?: InboxCategory;
}
