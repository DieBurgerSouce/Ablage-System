/**
 * RAG Chat API Service
 *
 * Verbindet das Frontend mit dem RAG Intelligence Layer Backend.
 * Endpoints: /api/v1/rag/chat/*
 */

import { apiClient } from './client';

// ============================================================================
// TYPES - Basierend auf Backend Schemas (app/api/schemas/rag.py)
// ============================================================================

export interface SourceChunk {
    chunk_id: string;
    document_id: string;
    document_name?: string; // Optional, wird ggf. separat geladen
    chunk_text: string;
    chunk_index: number;
    page_number: number | null;
    section_type: string | null;
    similarity: number;
    rerank_score: number | null;
}

export interface AttachedDocument {
    id: string;
    name: string;
}

export interface ChatMessage {
    id: string;
    session_id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    thinking_content?: string | null;
    confidence_score?: number | null;
    model_used?: string | null;
    tokens_input?: number | null;
    tokens_output?: number | null;
    generation_time_ms?: number | null;
    created_at: string;
    sources?: SourceChunk[];
    is_thinking?: boolean; // UI state for streaming/processing
    attached_document?: AttachedDocument | null; // Dokument das an User-Nachricht angehaengt wurde
}

export interface ChatSession {
    id: string;
    user_id: string;
    session_token: string;
    title: string | null;
    context_type: string | null;
    context_id: string | null;
    status: string;
    message_count: number;
    created_at: string;
    updated_at: string;
    last_message_at: string | null;
    // Frontend convenience fields
    preview?: string;
}

export interface ChatSessionWithMessages extends ChatSession {
    messages: ChatMessage[];
}

// Request/Response types
export interface ChatRequest {
    message: string;
    session_id?: string;
    context_type?: 'general' | 'customer' | 'document' | 'report';
    context_id?: string;
    realtime?: boolean;
    stream?: boolean;
}

export interface ChatResponse {
    session_id: string;
    message: string;
    thinking_content?: string | null;
    sources: SourceChunk[];
    model_used: string;
    generation_time_ms: number;
}

// Streaming event types
export interface StreamEvent {
    type: 'chunk' | 'source' | 'thinking' | 'done' | 'error';
    content?: string;
    source?: SourceChunk;
    session_id?: string;
    message_id?: string;
    error?: string;
}

// ============================================================================
// API SERVICE
// ============================================================================

export const chatApi = {
    /**
     * Lädt alle Chat-Sessions des aktuellen Users
     */
    getSessions: async (limit = 20, offset = 0): Promise<ChatSession[]> => {
        const response = await apiClient.get<ChatSession[]>('/rag/chat/sessions', {
            params: { limit, offset },
        });

        // Add preview from title or generate placeholder
        return response.data.map((session) => ({
            ...session,
            preview: session.title || 'Neue Unterhaltung',
        }));
    },

    /**
     * Lädt eine einzelne Session mit allen Messages
     */
    getSession: async (sessionId: string): Promise<ChatSessionWithMessages> => {
        const response = await apiClient.get<ChatSessionWithMessages>(
            `/rag/chat/sessions/${sessionId}`
        );
        return response.data;
    },

    /**
     * Lädt nur die Messages einer Session (für Pagination)
     */
    getMessages: async (sessionId: string): Promise<ChatMessage[]> => {
        const response = await apiClient.get<ChatSessionWithMessages>(
            `/rag/chat/sessions/${sessionId}`
        );
        return response.data.messages || [];
    },

    /**
     * Sendet eine Nachricht und erstellt ggf. eine neue Session
     *
     * @param content - Die Nachricht
     * @param sessionId - Optional: Bestehende Session ID
     * @param options - Weitere Optionen (context_type, realtime, etc.)
     */
    sendMessage: async (
        content: string,
        sessionId?: string,
        options?: {
            contextType?: 'general' | 'customer' | 'document' | 'report';
            contextId?: string;
            realtime?: boolean;
        }
    ): Promise<{ session_id: string; response: ChatMessage }> => {
        const request: ChatRequest = {
            message: content,
            session_id: sessionId,
            context_type: options?.contextType || 'general',
            context_id: options?.contextId,
            realtime: options?.realtime ?? false,
            stream: false,
        };

        const response = await apiClient.post<ChatResponse>('/rag/chat', request);

        // Convert ChatResponse to ChatMessage format for UI
        const assistantMessage: ChatMessage = {
            id: crypto.randomUUID(), // Temporary ID until we reload
            session_id: response.data.session_id,
            role: 'assistant',
            content: response.data.message,
            thinking_content: response.data.thinking_content,
            model_used: response.data.model_used,
            generation_time_ms: response.data.generation_time_ms,
            created_at: new Date().toISOString(),
            sources: response.data.sources,
        };

        return {
            session_id: response.data.session_id,
            response: assistantMessage,
        };
    },

    /**
     * Sendet eine Nachricht mit Streaming-Response
     *
     * @param content - Die Nachricht
     * @param sessionId - Optional: Bestehende Session ID
     * @param onChunk - Callback für jeden Text-Chunk
     * @param onSource - Callback für Quellen
     * @param onDone - Callback wenn fertig
     * @param onError - Callback bei Fehler
     * @param signal - Optional: AbortSignal zum Abbrechen des Streams
     */
    sendMessageStream: async (
        content: string,
        sessionId?: string,
        callbacks?: {
            onChunk?: (text: string) => void;
            onThinking?: (text: string) => void;
            onSource?: (source: SourceChunk) => void;
            onDone?: (sessionId: string, messageId?: string) => void;
            onError?: (error: string) => void;
            onAbort?: () => void;
            contextType?: 'general' | 'customer' | 'document' | 'report';
            contextId?: string;
            signal?: AbortSignal;
        }
    ): Promise<void> => {
        const request: ChatRequest = {
            message: content,
            session_id: sessionId,
            stream: true,
            context_type: callbacks?.contextType,
            context_id: callbacks?.contextId,
        };

        try {
            // Hole Token aus apiClient Interceptor-Logik (konsistent mit anderen API-Calls)
            const token = localStorage.getItem('auth_token');
            const headers: HeadersInit = {
                'Content-Type': 'application/json',
                Accept: 'text/event-stream',
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            // Fetch with streaming (SSE)
            // Verwende vollständige URL mit korrektem baseURL (relativ für nginx proxy)
            const baseUrl = apiClient.defaults.baseURL || '/api/v1';
            const response = await fetch(
                `${baseUrl}/rag/chat/stream`,
                {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(request),
                    credentials: 'include', // Für CORS mit Credentials (cross-origin)
                    signal: callbacks?.signal, // AbortSignal für Abbruch
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error('No response body for streaming');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event: StreamEvent = JSON.parse(line.slice(6));

                            switch (event.type) {
                                case 'chunk':
                                    callbacks?.onChunk?.(event.content || '');
                                    break;
                                case 'thinking':
                                    callbacks?.onThinking?.(event.content || '');
                                    break;
                                case 'source':
                                    if (event.source) {
                                        callbacks?.onSource?.(event.source);
                                    }
                                    break;
                                case 'done':
                                    callbacks?.onDone?.(
                                        event.session_id || '',
                                        event.message_id
                                    );
                                    break;
                                case 'error':
                                    callbacks?.onError?.(
                                        event.error || 'Unbekannter Fehler'
                                    );
                                    break;
                            }
                        } catch {
                            // Ignore parse errors for incomplete JSON
                        }
                    }
                }
            }
        } catch (error) {
            // AbortError separat behandeln (kein Fehler, sondern gewollter Abbruch)
            if (error instanceof Error && error.name === 'AbortError') {
                callbacks?.onAbort?.();
                return;
            }
            const errorMessage =
                error instanceof Error ? error.message : 'Verbindungsfehler';
            callbacks?.onError?.(errorMessage);
        }
    },

    /**
     * Löscht eine Session (soft delete)
     */
    deleteSession: async (sessionId: string): Promise<void> => {
        await apiClient.delete(`/rag/chat/sessions/${sessionId}`);
    },

    /**
     * Aktualisiert den Titel einer Session
     */
    updateSessionTitle: async (
        sessionId: string,
        title: string
    ): Promise<ChatSession> => {
        const response = await apiClient.put<ChatSession>(
            `/rag/chat/sessions/${sessionId}`,
            null,
            { params: { title } }
        );
        return response.data;
    },

    /**
     * Erstellt eine neue leere Session
     */
    createSession: async (options?: {
        title?: string;
        contextType?: 'general' | 'customer' | 'document' | 'report';
        contextId?: string;
    }): Promise<ChatSession> => {
        const response = await apiClient.post<ChatSession>('/rag/chat/sessions', {
            title: options?.title,
            context_type: options?.contextType,
            context_id: options?.contextId,
        });
        return response.data;
    },

    /**
     * Health Check für RAG Service
     */
    healthCheck: async (): Promise<{
        status: string;
        components: Record<string, unknown>;
    }> => {
        const response = await apiClient.get('/rag/health');
        return response.data;
    },
};

// Default export for convenience
export default chatApi;
