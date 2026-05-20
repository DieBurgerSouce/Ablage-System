/**
 * RAG Chat Types
 *
 * Type definitions for the document-aware chat feature.
 */

// ==================== Message Types ====================

export type MessageRole = 'user' | 'assistant' | 'system';

export interface ChatMessageSource {
    document_id: string;
    filename: string;
    similarity: number;
    document_type?: string;
}

// ==================== Action Types ====================

export type ChatActionStatus =
    | 'pending_confirmation'
    | 'confirmed'
    | 'executed'
    | 'rejected'
    | 'failed';

// Daily agenda item from get_daily_agenda tool
export interface DailyAgendaItem {
    id: string;
    title: string;
    type: 'deadline' | 'approval' | 'skonto' | 'overdue' | 'reminder';
    due_date: string;
    entity_name?: string;
    amount?: number;
    currency?: string;
    priority: 'critical' | 'high' | 'medium' | 'low';
    document_id?: string;
    days_remaining?: number;
}

// Comparison data for expense charts
export interface ComparisonCategory {
    name: string;
    period_1_value: number;
    period_2_value: number;
    difference: number;
    change_percent: number;
}

export interface ComparisonData {
    period_1_label: string;
    period_2_label: string;
    categories: ComparisonCategory[];
    total_period_1: number;
    total_period_2: number;
    total_difference: number;
    total_change_percent: number;
}

// Extended tool result types
export type ToolResultType = 'agenda' | 'comparison' | 'search_results' | 'action' | 'skonto' | 'text';

// Skonto opportunity
export interface SkontoOpportunity {
    document_id: string;
    entity_name: string;
    invoice_number: string;
    total_amount: number;
    skonto_percent: number;
    skonto_amount: number;
    deadline: string;
    days_remaining: number;
}

export interface ChatToolAction {
    action_id: string;
    tool_name: string;
    parameters: Record<string, unknown>;
    status: ChatActionStatus;
    requires_confirmation: boolean;
    result?: Record<string, unknown>;
    error_message?: string;
    description?: string;
    result_type?: ToolResultType;
    agenda_items?: DailyAgendaItem[];
    comparison_data?: ComparisonData;
    skonto_items?: SkontoOpportunity[];
}

export interface ChatMessage {
    id: string;
    role: MessageRole;
    content: string;
    timestamp: string;
    sources?: ChatMessageSource[];
    isStreaming?: boolean;
    actions?: ChatToolAction[];
}

// ==================== Session Types ====================

export interface ChatSession {
    id: string;
    user_id?: string;
    message_count: number;
    created_at: string;
    updated_at: string;
}

export interface SessionHistory {
    session_id: string;
    messages: ChatMessage[];
    context_documents: ContextDocument[];
    created_at: string;
    updated_at: string;
}

export interface ContextDocument {
    filename: string;
    document_type?: string;
    similarity: number;
}

// ==================== WebSocket Message Types ====================

export type WebSocketMessageType =
    | 'connected'
    | 'token'
    | 'message_complete'
    | 'context'
    | 'processing'
    | 'generating'
    | 'error'
    | 'ping'
    | 'pong'
    | 'history'
    | 'history_cleared';

export interface WSConnectedMessage {
    type: 'connected';
    session_id: string;
    user_id: string;
    message_count: number;
    timestamp: string;
}

export interface WSTokenMessage {
    type: 'token';
    content: string;
    timestamp: string;
}

export interface WSMessageCompleteMessage {
    type: 'message_complete';
    message_id: string;
    content: string;
    sources: ChatMessageSource[];
    timestamp: string;
}

export interface WSContextMessage {
    type: 'context';
    documents: ContextDocument[];
    count: number;
}

export interface WSProcessingMessage {
    type: 'processing' | 'generating';
    message: string;
}

export interface WSErrorMessage {
    type: 'error';
    message: string;
}

export interface WSHistoryMessage {
    type: 'history';
    messages: ChatMessage[];
}

export type WSMessage =
    | WSConnectedMessage
    | WSTokenMessage
    | WSMessageCompleteMessage
    | WSContextMessage
    | WSProcessingMessage
    | WSErrorMessage
    | WSHistoryMessage
    | { type: 'pong' }
    | { type: 'history_cleared'; message: string };

// ==================== API Types ====================

export interface SendMessageRequest {
    content: string;
    session_id?: string;
}

export interface SendMessageResponse {
    message_id: string;
    session_id: string;
    content: string;
    sources: ChatMessageSource[];
    tool_actions: ChatToolAction[];
    timestamp: string;
}

export interface SessionListResponse {
    sessions: ChatSession[];
    total: number;
}

export interface ChatServiceStatus {
    llm_enabled: boolean;
    llm_model: string | null;
    ollama_url: string | null;
    active_sessions: number;
    user_session_count: number;
}

// ==================== Connection State ====================

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface ChatConnectionState {
    status: ConnectionStatus;
    sessionId: string | null;
    error: string | null;
    reconnectAttempt: number;
}

// ==================== UI State ====================

export interface ChatUIState {
    messages: ChatMessage[];
    isLoading: boolean;
    isStreaming: boolean;
    currentStreamingContent: string;
    contextDocuments: ContextDocument[];
    statusMessage: string | null;
}

// ==================== Helper Functions ====================

export function formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
        return date.toLocaleTimeString('de-DE', {
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

export function formatSimilarity(similarity: number): string {
    return `${Math.round(similarity * 100)}%`;
}

export function getMessageClassName(role: MessageRole): string {
    switch (role) {
        case 'user':
            return 'bg-primary text-primary-foreground';
        case 'assistant':
            return 'bg-muted';
        case 'system':
            return 'bg-secondary text-secondary-foreground text-sm';
        default:
            return 'bg-muted';
    }
}
