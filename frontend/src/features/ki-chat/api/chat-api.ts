/**
 * KI-Chat API Client
 *
 * API-Funktionen fuer den RAG Chat-Assistenten mit Streaming-Support.
 * Nutzt native fetch fuer SSE-Streaming und apiClient fuer REST-Aufrufe.
 *
 * Backend-Endpunkte:
 * - POST /api/v1/rag/chat           - Nachricht senden (non-streaming)
 * - POST /api/v1/rag/chat/stream    - Nachricht senden (SSE streaming)
 * - POST /api/v1/rag/chat/sessions  - Session erstellen
 * - GET  /api/v1/rag/chat/sessions  - Sessions auflisten
 * - GET  /api/v1/rag/chat/sessions/:id - Session mit Nachrichten laden
 */

import { apiClient } from '@/lib/api/client';
import type {
  ChatSession,
  ChatMessage,
  ChatSendPayload,
  ChatSessionCreate,
  StreamEvent,
} from '../types/chat-types';

const BASE_PATH = '/rag/chat';

// ==================== Session API ====================

export async function getChatSessions(): Promise<ChatSession[]> {
  const response = await apiClient.get<ChatSession[]>(`${BASE_PATH}/sessions`);
  return response.data;
}

export async function createChatSession(
  payload: ChatSessionCreate
): Promise<ChatSession> {
  const response = await apiClient.post<ChatSession>(
    `${BASE_PATH}/sessions`,
    payload
  );
  return response.data;
}

export async function getChatMessages(
  sessionId: string
): Promise<ChatMessage[]> {
  const response = await apiClient.get<{
    messages: ChatMessage[];
  }>(`${BASE_PATH}/sessions/${sessionId}`);
  return response.data.messages;
}

// ==================== Non-Streaming Chat ====================

export async function sendChatMessage(
  payload: ChatSendPayload
): Promise<{ session_id: string; message: string; sources: ChatMessage['sources'] }> {
  const response = await apiClient.post(BASE_PATH, {
    ...payload,
    stream: false,
  });
  return response.data;
}

// ==================== Streaming Chat ====================

/**
 * Streaming Chat-Nachricht senden via fetch + ReadableStream.
 * Nutzt den /rag/chat/stream Endpoint mit SSE (Server-Sent Events).
 *
 * Event-Typen vom Backend:
 * - chunk:  Text-Fragment der Antwort { type: "chunk", content: "..." }
 * - source: Quellen-Referenz { type: "source", source: {...} }
 * - done:   Abschluss { type: "done", session_id: "...", message_id: "..." }
 * - error:  Fehler { type: "error", error: "..." }
 */
export async function sendChatMessageStream(
  payload: ChatSendPayload,
  onEvent: (event: StreamEvent) => void,
  onError: (error: string) => void
): Promise<void> {
  const token = sessionStorage.getItem('auth_token');
  if (!token?.trim()) {
    onError('Nicht authentifiziert');
    return;
  }

  const baseURL = apiClient.defaults.baseURL || '';

  let response: Response;
  try {
    response = await fetch(`${baseURL}${BASE_PATH}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token.trim()}`,
      },
      body: JSON.stringify({
        ...payload,
        stream: true,
      }),
    });
  } catch (networkError) {
    onError('Netzwerkfehler: Server nicht erreichbar');
    return;
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    onError(
      (errorBody as Record<string, string>).detail ||
        `Fehler: ${response.status} ${response.statusText}`
    );
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError('Streaming nicht verfuegbar');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Letzte (moeglicherweise unvollstaendige) Zeile behalten
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (!data) continue;

          try {
            const parsed = JSON.parse(data) as StreamEvent;
            onEvent(parsed);

            if (parsed.type === 'error') {
              return;
            }
          } catch {
            // Ungueltige JSON-Zeile ueberspringen
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
