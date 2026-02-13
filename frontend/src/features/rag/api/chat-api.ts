/**
 * RAG Chat API
 *
 * REST API client for chat operations.
 */

import type {
    SendMessageRequest,
    SendMessageResponse,
    SessionListResponse,
    SessionHistory,
    ChatSession,
    ChatServiceStatus,
} from '../types/chat-types';

const API_BASE = '/api/v1/rag/chat';

/**
 * Get authentication token from storage.
 */
function getAuthToken(): string | null {
    return sessionStorage.getItem('auth_token');
}

/**
 * Make authenticated API request.
 */
async function fetchWithAuth<T>(
    url: string,
    options: RequestInit = {}
): Promise<T> {
    const token = getAuthToken();
    if (!token) {
        throw new Error('Nicht authentifiziert');
    }

    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `Request failed: ${response.status}`);
    }

    // Handle 204 No Content
    if (response.status === 204) {
        return undefined as T;
    }

    return response.json();
}

// ==================== Message API ====================

/**
 * Send a chat message and receive a response.
 */
export async function sendMessage(
    request: SendMessageRequest
): Promise<SendMessageResponse> {
    return fetchWithAuth<SendMessageResponse>(`${API_BASE}/message`, {
        method: 'POST',
        body: JSON.stringify(request),
    });
}

/**
 * Send a chat message with streaming response.
 * Returns an async generator that yields SSE events.
 */
export async function* sendMessageStream(
    request: SendMessageRequest
): AsyncGenerator<{
    type: string;
    content?: string;
    count?: number;
    session_id?: string;
    message_id?: string;
    message?: string;
    tool_action_count?: number;
    action_id?: string;
    tool_name?: string;
    parameters?: Record<string, unknown>;
    action_type?: string;
    status?: string;
    data?: Record<string, unknown>;
    requires_confirmation?: boolean;
    execution_time_ms?: number;
}> {
    const token = getAuthToken();
    if (!token) {
        throw new Error('Nicht authentifiziert');
    }

    const response = await fetch(`${API_BASE}/message/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `Request failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
        throw new Error('Response body not readable');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        yield data;
                    } catch {
                        // Skip invalid JSON
                    }
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}

// ==================== Session API ====================

/**
 * List all chat sessions for the current user.
 */
export async function listSessions(): Promise<SessionListResponse> {
    return fetchWithAuth<SessionListResponse>(`${API_BASE}/sessions`);
}

/**
 * Create a new chat session.
 */
export async function createSession(): Promise<ChatSession> {
    return fetchWithAuth<ChatSession>(`${API_BASE}/sessions`, {
        method: 'POST',
    });
}

/**
 * Get chat history for a session.
 */
export async function getSessionHistory(
    sessionId: string
): Promise<SessionHistory> {
    return fetchWithAuth<SessionHistory>(`${API_BASE}/sessions/${sessionId}`);
}

/**
 * Delete a chat session.
 */
export async function deleteSession(sessionId: string): Promise<void> {
    return fetchWithAuth<void>(`${API_BASE}/sessions/${sessionId}`, {
        method: 'DELETE',
    });
}

/**
 * Clear chat history for a session.
 */
export async function clearSessionHistory(sessionId: string): Promise<void> {
    return fetchWithAuth<void>(`${API_BASE}/sessions/${sessionId}/clear`, {
        method: 'POST',
    });
}

/**
 * Get chat service status.
 */
export async function getChatStatus(): Promise<ChatServiceStatus> {
    return fetchWithAuth<ChatServiceStatus>(`${API_BASE}/status`);
}

// ==================== Action API ====================

/**
 * Bestätigt eine ausstehende Chat-Aktion.
 */
export async function confirmAction(
    actionId: string
): Promise<{ success: boolean; result?: Record<string, unknown> }> {
    return fetchWithAuth(`${API_BASE}/actions/${actionId}/confirm`, {
        method: 'POST',
    });
}

/**
 * Lehnt eine ausstehende Chat-Aktion ab.
 */
export async function rejectAction(
    actionId: string
): Promise<{ success: boolean }> {
    return fetchWithAuth(`${API_BASE}/actions/${actionId}/reject`, {
        method: 'POST',
    });
}

// ==================== React Query Keys ====================

export const chatKeys = {
    all: ['chat'] as const,
    sessions: () => [...chatKeys.all, 'sessions'] as const,
    session: (id: string) => [...chatKeys.sessions(), id] as const,
    history: (id: string) => [...chatKeys.session(id), 'history'] as const,
    status: () => [...chatKeys.all, 'status'] as const,
    actions: () => [...chatKeys.all, 'actions'] as const,
    action: (id: string) => [...chatKeys.actions(), id] as const,
};
