/**
 * RAG Chat Feature
 *
 * Document-aware chat with semantic search and LLM integration.
 * Extended with Business Intelligence capabilities for data analysis.
 */

// Types
export * from './types/chat-types';

// API
export * from './api/chat-api';
export * from './api/bi-api';

// Hooks
export { useChatWebSocket } from './hooks/use-chat-websocket';
export {
    useChatSessions,
    useSessionHistory,
    useCreateSession,
    useDeleteSession,
    useClearSessionHistory,
    useChatStatus,
    useSendMessage,
} from './hooks/use-chat';

// Components
export { ChatMessage } from './components/ChatMessage';
export { ChatInput } from './components/ChatInput';
export { ChatInterface } from './components/ChatInterface';
export { ChatSessionList } from './components/ChatSessionList';

// Business Intelligence Components
export { BIInsights } from './components/BIInsights';
export { BIChatInterface } from './components/BIChatInterface';
