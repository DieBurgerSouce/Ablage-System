/**
 * KI-Chat Types - Typen fuer den RAG Chat-Assistenten (Slide-out Panel)
 *
 * Typen basieren auf den Backend-Schemas:
 * - RAGChatSessionResponse
 * - RAGChatMessageResponse
 * - RAGChatRequest
 * - RAGChunkSearchResult (Quellen)
 */

export interface ChatSession {
  id: string;
  title: string | null;
  status: string;
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface ChatSource {
  chunk_id: string;
  document_id: string;
  chunk_text: string;
  chunk_index: number;
  page_number: number | null;
  section_type: string | null;
  similarity: number;
  rerank_score: number | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinking_content?: string | null;
  model_used?: string | null;
  sources?: ChatSource[];
  created_at: string;
}

export interface ChatSendPayload {
  message: string;
  session_id?: string;
  context_type?: 'general' | 'document' | 'entity';
  context_id?: string;
  stream?: boolean;
}

export interface ChatSessionCreate {
  title?: string;
  context_type?: 'general' | 'document' | 'entity';
  context_id?: string;
}

/**
 * SSE Event-Typen vom Streaming-Endpoint.
 */
export type StreamEventType = 'chunk' | 'source' | 'thinking' | 'done' | 'error';

export interface StreamChunkEvent {
  type: 'chunk';
  content: string;
}

export interface StreamSourceEvent {
  type: 'source';
  source: ChatSource;
}

export interface StreamDoneEvent {
  type: 'done';
  session_id: string;
  message_id: string;
}

export interface StreamErrorEvent {
  type: 'error';
  error: string;
}

export type StreamEvent =
  | StreamChunkEvent
  | StreamSourceEvent
  | StreamDoneEvent
  | StreamErrorEvent;
