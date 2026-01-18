/**
 * AI Assistant Feature Module
 *
 * Global AI assistant widget with context-aware suggestions.
 * Supports role-based AI actions (Viewer/Editor/Admin autonomy levels).
 */

// Components
export { GlobalAIAssistant } from './components/GlobalAIAssistant';

// Hooks - Page Context
export { usePageContext, getContextSuggestions, getContextPlaceholder } from './hooks/use-page-context';

// Hooks - AI Actions
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

// Store
export { useAIAssistantStore } from './stores/ai-assistant-store';
export type { PageContext, PageContextType, AIAssistantView, AIAssistantState } from './stores/ai-assistant-store';
