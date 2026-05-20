/**
 * Finance Assistant API Service
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Integrates with the intelligent Finance Assistant backend:
 * - Chat with AI assistant
 * - Execute actions
 * - Proactive insights
 * - Booking suggestions (SKR03/04)
 */

import { apiClient } from '../client';

// ===== Types =====

export interface ChatRequest {
  message: string;
  current_page?: string;
  selected_documents?: string[];
  session_id?: string;
}

export interface ActionData {
  action_type: string;
  description: string;
  parameters: Record<string, unknown>;
  confidence: number;
  requires_confirmation: boolean;
  affected_count: number;
}

export interface BookingSuggestionData {
  debit_account: string;
  debit_account_name: string;
  credit_account: string;
  credit_account_name: string;
  amount: number;
  description: string;
  tax_code?: string;
  confidence: number;
  reasoning: string;
}

export interface InsightData {
  title: string;
  content: string;
  category: string;
  severity: string;
  related_documents: string[];
  data?: Record<string, unknown>;
}

export interface ChatResponse {
  message: string;
  intent: AssistantIntent;
  success: boolean;
  confidence: number;
  actions: ActionData[];
  booking_suggestions: BookingSuggestionData[];
  insights: InsightData[];
  search_results?: Record<string, unknown>[];
  result_count: number;
  processing_time_ms: number;
  follow_up_suggestions: string[];
  error_message?: string;
}

export interface ExecuteActionRequest {
  action_type: string;
  parameters: Record<string, unknown>;
}

export interface ExecuteActionResponse {
  action_id: string;
  status: ActionExecutionStatus;
  success: boolean;
  message: string;
  affected_count: number;
  rollback_possible: boolean;
  execution_time_ms: number;
  error_details?: string;
  metadata: Record<string, unknown>;
}

export interface RollbackRequest {
  action_id: string;
}

export interface InsightResponse {
  id: string;
  category: InsightCategory;
  severity: InsightSeverity;
  title: string;
  summary: string;
  details: string;
  recommendations: string[];
  affected_entities: string[];
  metrics: Record<string, unknown>;
  action_url?: string;
}

export interface InsightsListResponse {
  insights: InsightResponse[];
  count: number;
  generated_at: string;
}

export interface AssistantCapability {
  name: string;
  description: string;
  examples: string[];
}

export interface AssistantHelpResponse {
  version: string;
  capabilities: AssistantCapability[];
  supported_languages: string[];
  requires_ollama: boolean;
}

// ===== Enums =====

export enum AssistantIntent {
  SEARCH = 'search',
  EXECUTE_ACTION = 'execute_action',
  EXPLAIN = 'explain',
  SUGGEST_BOOKING = 'suggest_booking',
  ANALYZE = 'analyze',
  PREDICT = 'predict',
  HELP = 'help',
  CHAT = 'chat',
}

export enum ActionExecutionStatus {
  PENDING = 'pending',
  EXECUTING = 'executing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  ROLLED_BACK = 'rolled_back',
}

export enum InsightCategory {
  OVERDUE = 'overdue',
  CASHFLOW = 'cashflow',
  SKONTO = 'skonto',
  ANOMALY = 'anomaly',
  TREND = 'trend',
  RISK = 'risk',
  OPPORTUNITY = 'opportunity',
}

export enum InsightSeverity {
  INFO = 'info',
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical',
}

// ===== Intent Metadata (German Labels) =====

export const INTENT_METADATA: Record<AssistantIntent, { label: string; icon: string; color: string }> = {
  [AssistantIntent.SEARCH]: {
    label: 'Suche',
    icon: 'search',
    color: 'blue',
  },
  [AssistantIntent.EXECUTE_ACTION]: {
    label: 'Aktion',
    icon: 'play',
    color: 'green',
  },
  [AssistantIntent.EXPLAIN]: {
    label: 'Erklärung',
    icon: 'info',
    color: 'purple',
  },
  [AssistantIntent.SUGGEST_BOOKING]: {
    label: 'Buchungsvorschlag',
    icon: 'calculator',
    color: 'orange',
  },
  [AssistantIntent.ANALYZE]: {
    label: 'Analyse',
    icon: 'chart',
    color: 'cyan',
  },
  [AssistantIntent.PREDICT]: {
    label: 'Vorhersage',
    icon: 'trending-up',
    color: 'pink',
  },
  [AssistantIntent.HELP]: {
    label: 'Hilfe',
    icon: 'help-circle',
    color: 'gray',
  },
  [AssistantIntent.CHAT]: {
    label: 'Chat',
    icon: 'message-circle',
    color: 'gray',
  },
};

// ===== Severity Metadata (German Labels) =====

export const SEVERITY_METADATA: Record<InsightSeverity, { label: string; color: string }> = {
  [InsightSeverity.INFO]: { label: 'Information', color: 'blue' },
  [InsightSeverity.LOW]: { label: 'Niedrig', color: 'green' },
  [InsightSeverity.MEDIUM]: { label: 'Mittel', color: 'yellow' },
  [InsightSeverity.HIGH]: { label: 'Hoch', color: 'orange' },
  [InsightSeverity.CRITICAL]: { label: 'Kritisch', color: 'red' },
};

// ===== Category Metadata (German Labels) =====

export const CATEGORY_METADATA: Record<InsightCategory, { label: string; icon: string }> = {
  [InsightCategory.OVERDUE]: { label: 'Überfällig', icon: 'clock' },
  [InsightCategory.CASHFLOW]: { label: 'Cash Flow', icon: 'dollar-sign' },
  [InsightCategory.SKONTO]: { label: 'Skonto', icon: 'percent' },
  [InsightCategory.ANOMALY]: { label: 'Anomalie', icon: 'alert-triangle' },
  [InsightCategory.TREND]: { label: 'Trend', icon: 'trending-up' },
  [InsightCategory.RISK]: { label: 'Risiko', icon: 'shield' },
  [InsightCategory.OPPORTUNITY]: { label: 'Chance', icon: 'star' },
};

// ===== API Functions =====

/**
 * Chat with the Finance Assistant
 */
export async function chatWithAssistant(request: ChatRequest): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>('/finance-assistant/chat', request);
  return response.data;
}

/**
 * Execute an action proposed by the assistant
 */
export async function executeAction(request: ExecuteActionRequest): Promise<ExecuteActionResponse> {
  const response = await apiClient.post<ExecuteActionResponse>('/finance-assistant/execute', request);
  return response.data;
}

/**
 * Rollback a previously executed action
 */
export async function rollbackAction(request: RollbackRequest): Promise<ExecuteActionResponse> {
  const response = await apiClient.post<ExecuteActionResponse>('/finance-assistant/rollback', request);
  return response.data;
}

/**
 * Get proactive insights
 */
export async function getInsights(includePredictions = true): Promise<InsightsListResponse> {
  const response = await apiClient.get<InsightsListResponse>('/finance-assistant/insights', {
    params: { include_predictions: includePredictions },
  });
  return response.data;
}

/**
 * Get assistant help information
 */
export async function getAssistantHelp(): Promise<AssistantHelpResponse> {
  const response = await apiClient.get<AssistantHelpResponse>('/finance-assistant/help');
  return response.data;
}

// ===== Action Type Helpers =====

export const ACTION_TYPE_LABELS: Record<string, string> = {
  create_payment_run: 'Zahlungslauf erstellen',
  start_dunning: 'Mahnlauf starten',
  export_datev: 'DATEV-Export',
  archive_documents: 'Dokumente archivieren',
  approve_invoices: 'Rechnungen genehmigen',
  categorize_documents: 'Dokumente kategorisieren',
  link_entities: 'Entitäten verknüpfen',
  generate_report: 'Bericht erstellen',
};

export function getActionTypeLabel(actionType: string): string {
  return ACTION_TYPE_LABELS[actionType] || actionType;
}

// ===== Booking Account Helpers =====

export const COMMON_ACCOUNTS_SKR03: Record<string, { number: string; name: string }> = {
  bank: { number: '1200', name: 'Bank' },
  kasse: { number: '1000', name: 'Kasse' },
  forderungen: { number: '1400', name: 'Forderungen aus L+L' },
  verbindlichkeiten: { number: '1600', name: 'Verbindlichkeiten aus L+L' },
  umsatzerloese: { number: '8400', name: 'Umsatzerlöse 19%' },
  wareneinkauf: { number: '3400', name: 'Wareneingang 19%' },
  vorsteuer: { number: '1576', name: 'Vorsteuer 19%' },
  umsatzsteuer: { number: '1776', name: 'Umsatzsteuer 19%' },
};

export const COMMON_ACCOUNTS_SKR04: Record<string, { number: string; name: string }> = {
  bank: { number: '1800', name: 'Bank' },
  kasse: { number: '1600', name: 'Kasse' },
  forderungen: { number: '1200', name: 'Forderungen aus L+L' },
  verbindlichkeiten: { number: '3300', name: 'Verbindlichkeiten aus L+L' },
  umsatzerloese: { number: '4400', name: 'Umsatzerlöse 19%' },
  wareneinkauf: { number: '5400', name: 'Wareneingang 19%' },
  vorsteuer: { number: '1406', name: 'Vorsteuer 19%' },
  umsatzsteuer: { number: '3806', name: 'Umsatzsteuer 19%' },
};

// ===== Conversation Persistence Types (Vision 2.0 Phase 1) =====

export type MessageRole = 'user' | 'assistant' | 'system';
export type ActionStatus = 'proposed' | 'confirmed' | 'executed' | 'cancelled' | 'failed';
export type FeedbackType = 'helpful' | 'not_helpful' | 'incorrect' | 'confusing' | 'other';

export interface ConversationSummary {
  id: string;
  session_id: string;
  title: string | null;
  context_page: string | null;
  language: string;
  is_active: boolean;
  is_starred: boolean;
  message_count: number;
  action_count: number;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  context_data: Record<string, unknown> | null;
  preferences: Record<string, unknown> | null;
  total_tokens: number | null;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  intent: AssistantIntent | null;
  confidence: number | null;
  search_results_count: number | null;
  actions_proposed: number | null;
  processing_time_ms: number | null;
  model_used: string | null;
  tokens_used: number | null;
  extra_data: Record<string, unknown> | null;
  referenced_documents: string[] | null;
  created_at: string;
}

export interface ConversationAction {
  id: string;
  conversation_id: string;
  message_id: string | null;
  action_type: string;
  description: string;
  status: ActionStatus;
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  affected_documents: string[] | null;
  affected_count: number | null;
  success_count: number | null;
  failure_count: number | null;
  requires_confirmation: boolean;
  confirmed_by_id: string | null;
  confirmed_at: string | null;
  proposed_at: string;
  executed_at: string | null;
}

export interface ConversationFeedback {
  id: string;
  message_id: string;
  user_id: string;
  feedback_type: FeedbackType;
  rating: number | null;
  comment: string | null;
  correction: string | null;
  expected_intent: string | null;
  created_at: string;
}

export interface CreateConversationRequest {
  session_id?: string;
  context_page?: string;
  context_data?: Record<string, unknown>;
  preferences?: Record<string, unknown>;
  language?: string;
}

export interface UpdateConversationRequest {
  title?: string;
  is_active?: boolean;
  is_starred?: boolean;
  preferences?: Record<string, unknown>;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ConversationMessagesResponse {
  messages: ConversationMessage[];
  total: number;
}

export interface ConversationActionsResponse {
  actions: ConversationAction[];
  total: number;
}

export interface AddFeedbackRequest {
  feedback_type: FeedbackType;
  rating?: number;
  comment?: string;
  correction?: string;
  expected_intent?: string;
}

export interface ConversationStatsResponse {
  total_conversations: number;
  active_conversations: number;
  total_messages: number;
  total_actions: number;
  total_feedbacks: number;
  actions_by_status: Record<ActionStatus, number>;
  conversations_by_day: Array<{ date: string; count: number }>;
  top_intents: Array<{ intent: string; count: number }>;
  average_messages_per_conversation: number;
  average_actions_per_conversation: number;
}

// ===== Conversation Persistence API Functions =====

/**
 * Create a new conversation
 */
export async function createConversation(
  request: CreateConversationRequest = {}
): Promise<ConversationDetail> {
  const response = await apiClient.post<ConversationDetail>('/ai/conversations', request);
  return response.data;
}

/**
 * List conversations with pagination and filtering
 */
export async function listConversations(params: {
  page?: number;
  page_size?: number;
  is_active?: boolean;
  is_starred?: boolean;
  search?: string;
} = {}): Promise<ConversationListResponse> {
  const response = await apiClient.get<ConversationListResponse>('/ai/conversations', { params });
  return response.data;
}

/**
 * Get a conversation by ID
 */
export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const response = await apiClient.get<ConversationDetail>(`/ai/conversations/${conversationId}`);
  return response.data;
}

/**
 * Get a conversation by session ID
 */
export async function getConversationBySession(sessionId: string): Promise<ConversationDetail> {
  const response = await apiClient.get<ConversationDetail>(`/ai/conversations/session/${sessionId}`);
  return response.data;
}

/**
 * Update a conversation
 */
export async function updateConversation(
  conversationId: string,
  request: UpdateConversationRequest
): Promise<ConversationDetail> {
  const response = await apiClient.patch<ConversationDetail>(
    `/ai/conversations/${conversationId}`,
    request
  );
  return response.data;
}

/**
 * Delete a conversation
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  await apiClient.delete(`/ai/conversations/${conversationId}`);
}

/**
 * Get messages for a conversation
 */
export async function getConversationMessages(
  conversationId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<ConversationMessagesResponse> {
  const response = await apiClient.get<ConversationMessagesResponse>(
    `/ai/conversations/${conversationId}/messages`,
    { params }
  );
  return response.data;
}

/**
 * Get actions for a conversation
 */
export async function getConversationActions(
  conversationId: string,
  params: { status?: ActionStatus } = {}
): Promise<ConversationActionsResponse> {
  const response = await apiClient.get<ConversationActionsResponse>(
    `/ai/conversations/${conversationId}/actions`,
    { params }
  );
  return response.data;
}

/**
 * Confirm an action
 */
export async function confirmConversationAction(
  conversationId: string,
  actionId: string
): Promise<ConversationAction> {
  const response = await apiClient.post<ConversationAction>(
    `/ai/conversations/${conversationId}/actions/${actionId}/confirm`
  );
  return response.data;
}

/**
 * Cancel an action
 */
export async function cancelConversationAction(
  conversationId: string,
  actionId: string
): Promise<ConversationAction> {
  const response = await apiClient.post<ConversationAction>(
    `/ai/conversations/${conversationId}/actions/${actionId}/cancel`
  );
  return response.data;
}

/**
 * Add feedback to a message
 */
export async function addMessageFeedback(
  messageId: string,
  request: AddFeedbackRequest
): Promise<ConversationFeedback> {
  const response = await apiClient.post<ConversationFeedback>(
    `/ai/conversations/messages/${messageId}/feedback`,
    request
  );
  return response.data;
}

/**
 * Get conversation statistics
 */
export async function getConversationStats(): Promise<ConversationStatsResponse> {
  const response = await apiClient.get<ConversationStatsResponse>('/ai/conversations/stats');
  return response.data;
}
