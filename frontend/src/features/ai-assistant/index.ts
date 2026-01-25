/**
 * AI Assistant Feature Module
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Global AI assistant widget with context-aware suggestions.
 * Supports role-based AI actions (Viewer/Editor/Admin autonomy levels).
 *
 * NEW: Finance Assistant integration with:
 * - Natural language chat
 * - Action execution with rollback
 * - Booking suggestions (SKR03/04)
 * - Proactive insights
 */

// Components
export { GlobalAIAssistant } from './components/GlobalAIAssistant';
export { GlobalAIAssistantV2 } from './components/GlobalAIAssistantV2';
export { FinanceAssistantChat } from './components/FinanceAssistantChat';
export { ActionProposalCard } from './components/ActionProposalCard';
export { BookingSuggestionCard } from './components/BookingSuggestionCard';
export { InsightCard, InsightsList } from './components/InsightCard';
export { InsightsWidget } from './components/InsightsWidget';
// Conversation Persistence Components (Vision 2.0 Phase 1)
export { ConversationHistory } from './components/ConversationHistory';
export { FeedbackDialog, QuickFeedback } from './components/FeedbackDialog';

// Hooks - Page Context
export { usePageContext, getContextSuggestions, getContextPlaceholder } from './hooks/use-page-context';

// Hooks - AI Actions (Legacy)
export {
    useAvailableActions,
    useAIContextInfo,
    useExecuteAction,
    useConfirmAction,
    useCanExecuteAction,
    useContextAwareAction,
    useActionSuggestions,
    aiActionKeys,
    AIActionType,
    AIActionStatus,
    AIActionAutonomyLevel,
    ACTION_METADATA,
} from './hooks/use-ai-actions';
export type {
    AIActionRequest,
    AIActionConfirmRequest,
    AIActionResult,
    AIActionListResponse,
    AIContextInfo,
    AIActionSuggestion,
} from './hooks/use-ai-actions';

// Hooks - Finance Assistant (Vision 2.0)
export {
    useFinanceAssistant,
    useFinanceAssistantChat,
    useExecuteAction as useExecuteFinanceAction,
    useInsights,
    useAssistantHelp,
    financeAssistantKeys,
    // Conversation Persistence Hooks (Vision 2.0 Phase 1)
    useConversations,
    usePersistentConversation,
    useConversationMessages,
    useConversationActionsQuery,
    useMessageFeedback,
    useConversationStats,
} from './hooks/use-finance-assistant';
export type {
    ChatMessage,
    UseFinanceAssistantOptions,
    UseFinanceAssistantChatOptions,
    UseExecuteActionOptions,
    UseInsightsOptions,
    // Conversation Persistence Types
    UseConversationsOptions,
    UsePersistentConversationOptions,
    UseConversationMessagesOptions,
    UseConversationActionsOptions,
    ConversationSummary,
    ConversationDetail,
    ConversationMessage,
    ConversationAction,
    ActionStatus,
    FeedbackType,
} from './hooks/use-finance-assistant';

// Store
export { useAIAssistantStore } from './stores/ai-assistant-store';
export type { PageContext, PageContextType, AIAssistantView, AIAssistantState } from './stores/ai-assistant-store';

// API Service Types
export {
    AssistantIntent,
    ActionExecutionStatus,
    InsightCategory,
    InsightSeverity,
    INTENT_METADATA,
    SEVERITY_METADATA,
    CATEGORY_METADATA,
    getActionTypeLabel,
    // Conversation Persistence API (Vision 2.0 Phase 1)
    createConversation,
    listConversations,
    getConversation,
    getConversationBySession,
    updateConversation,
    deleteConversation,
    getConversationMessages,
    getConversationActions,
    confirmConversationAction,
    cancelConversationAction,
    addMessageFeedback,
    getConversationStats,
} from '@/lib/api/services/finance-assistant';
export type {
    ChatRequest,
    ChatResponse,
    ActionData,
    BookingSuggestionData,
    InsightData,
    ExecuteActionRequest,
    ExecuteActionResponse,
    InsightResponse,
    InsightsListResponse,
    AssistantHelpResponse,
    // Conversation Persistence Types
    ConversationListResponse,
    ConversationMessagesResponse,
    ConversationActionsResponse,
    ConversationFeedback,
    CreateConversationRequest,
    UpdateConversationRequest,
    AddFeedbackRequest,
    ConversationStatsResponse,
} from '@/lib/api/services/finance-assistant';
