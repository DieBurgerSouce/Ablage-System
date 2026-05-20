/**
 * KI-Chat Feature - RAG Chat-Assistent (Slide-out Panel)
 *
 * Leichtgewichtiges Chat-Panel das als Sheet von rechts eingeblendet wird.
 * Nutzt den bestehenden RAG-Chat-Backend unter /api/v1/rag/chat.
 */

// Components
export { ChatPanel } from './components/ChatPanel';
export { ChatMessage } from './components/ChatMessage';
export { ChatInput } from './components/ChatInput';

// Hooks
export {
  useChatSessions,
  useCreateChatSession,
  useChatMessages,
  useSendMessage,
  kiChatKeys,
} from './hooks/use-chat';

// Types
export type {
  ChatSession,
  ChatMessage as ChatMessageType,
  ChatSource,
  ChatSendPayload,
  ChatSessionCreate,
  StreamEvent,
  StreamChunkEvent,
  StreamSourceEvent,
  StreamDoneEvent,
  StreamErrorEvent,
} from './types/chat-types';
