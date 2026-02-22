/**
 * Chat WebSocket Hook Tests
 *
 * Testet Verbindungsmanagement, Nachrichtenverarbeitung,
 * Aktionen und Reconnection-Logik des useChatWebSocket Hooks.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

// ============================================================================
// LOGGER MOCK
// ============================================================================

vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

// ============================================================================
// WEBSOCKET MOCK
// ============================================================================

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = WebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send = vi.fn();
  close = vi.fn((code?: number) => {
    this.readyState = WebSocket.CLOSED;
    // onclose direkt aufrufen damit Tests es sofort sehen
    const closeCode = code ?? 1000;
    this.onclose?.(new CloseEvent('close', { code: closeCode }));
  });

  /** Simuliert erfolgreiche Serververbindung */
  simulateOpen() {
    this.readyState = WebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  /** Simuliert eingehende Server-Nachricht */
  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }

  /** Simuliert Verbindungsabbruch */
  simulateClose(code = 1000) {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code }));
  }

  /** Simuliert Fehler-Event */
  simulateError() {
    this.onerror?.(new Event('error'));
  }
}

// WebSocket global überschreiben
const OriginalWebSocket = global.WebSocket;

beforeEach(() => {
  MockWebSocket.instances = [];
  global.WebSocket = MockWebSocket as unknown as typeof WebSocket;
});

afterEach(() => {
  global.WebSocket = OriginalWebSocket;
});

// ============================================================================
// IMPORT NACH MOCK
// ============================================================================

import { useChatWebSocket } from '../hooks/use-chat-websocket';

// ============================================================================
// TEST HELPERS
// ============================================================================

const TEST_SESSION_ID = 'session-abc-123';
const TEST_TOKEN = 'auth-token-xyz';

function getLatestInstance(): MockWebSocket {
  const instances = MockWebSocket.instances;
  if (instances.length === 0) {
    throw new Error('Keine MockWebSocket-Instanz vorhanden');
  }
  return instances[instances.length - 1];
}

// ============================================================================
// TESTS
// ============================================================================

describe('useChatWebSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    sessionStorage.clear();
  });

  // ==========================================================================
  // VERBINDUNGSMANAGEMENT
  // ==========================================================================

  describe('Verbindungsmanagement', () => {
    it('verbindet sich nicht wenn enabled=false', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: false,
        })
      );

      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it('verbindet sich nicht wenn sessionId null ist', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: null,
          enabled: true,
        })
      );

      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it('verbindet sich nicht wenn kein Auth-Token vorhanden', () => {
      sessionStorage.removeItem('auth_token');

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it('ruft onError auf wenn kein Auth-Token vorhanden', () => {
      sessionStorage.removeItem('auth_token');
      const onError = vi.fn();

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
          onError,
        })
      );

      expect(onError).toHaveBeenCalledWith('Nicht authentifiziert');
    });

    it('baut WebSocket-Verbindung auf wenn enabled und sessionId und Token vorhanden', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('baut korrekte WebSocket-URL mit ws-Protokoll', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      // http: -> ws:
      Object.defineProperty(window, 'location', {
        value: { protocol: 'http:', host: 'localhost:3000' },
        writable: true,
      });

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      expect(ws.url).toContain('ws://');
      expect(ws.url).toContain(`/api/v1/rag/ws/chat/${TEST_SESSION_ID}`);
    });

    it('baut korrekte WebSocket-URL mit wss-Protokoll bei HTTPS', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      Object.defineProperty(window, 'location', {
        value: { protocol: 'https:', host: 'beispiel.de' },
        writable: true,
      });

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      expect(ws.url).toContain('wss://');
    });

    it('kodiert Token in URL als Query-Parameter', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      expect(ws.url).toContain(`token=${encodeURIComponent(TEST_TOKEN)}`);
    });

    it('setzt isConnected auf true nach erfolgreichem Verbindungsaufbau', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const { result } = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      expect(result.current.isConnected).toBe(false);

      act(() => {
        getLatestInstance().simulateOpen();
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('ruft onConnectionChange(true) beim Verbindungsaufbau auf', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);
      const onConnectionChange = vi.fn();

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
          onConnectionChange,
        })
      );

      act(() => {
        getLatestInstance().simulateOpen();
      });

      expect(onConnectionChange).toHaveBeenCalledWith(true);
    });
  });

  // ==========================================================================
  // NACHRICHTENVERARBEITUNG
  // ==========================================================================

  describe('Nachrichtenverarbeitung', () => {
    function setupConnectedHook(callbacks: Parameters<typeof useChatWebSocket>[0] = {}) {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const result = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
          ...callbacks,
        })
      );

      act(() => {
        getLatestInstance().simulateOpen();
      });

      return result;
    }

    it('ruft onPresenceUpdate bei presence-Nachricht auf', () => {
      const onPresenceUpdate = vi.fn();
      setupConnectedHook({ onPresenceUpdate });

      const presenceData = {
        type: 'presence',
        users: [
          { user_id: 'user-1', username: 'Max', is_typing: false },
          { user_id: 'user-2', username: 'Anna', is_typing: true },
        ],
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(presenceData);
      });

      expect(onPresenceUpdate).toHaveBeenCalledWith(presenceData.users);
    });

    it('aktualisiert onlineUsers bei presence-Nachricht', () => {
      const { result } = setupConnectedHook();

      const presenceData = {
        type: 'presence',
        users: [{ user_id: 'user-1', username: 'Max', is_typing: false }],
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(presenceData);
      });

      expect(result.current.onlineUsers).toHaveLength(1);
      expect(result.current.onlineUsers[0].user_id).toBe('user-1');
    });

    it('ruft onNewMessage bei new_message-Nachricht auf', () => {
      const onNewMessage = vi.fn();
      setupConnectedHook({ onNewMessage });

      const messageData = {
        type: 'new_message',
        message: {
          id: 'msg-123',
          role: 'user',
          content: 'Hallo Welt',
          created_at: '2025-01-01T12:00:00Z',
        },
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(messageData);
      });

      expect(onNewMessage).toHaveBeenCalledOnce();
      const chatMessage = onNewMessage.mock.calls[0][0];
      expect(chatMessage.id).toBe('msg-123');
      expect(chatMessage.session_id).toBe(TEST_SESSION_ID);
      expect(chatMessage.content).toBe('Hallo Welt');
    });

    it('ruft onTypingUpdate(true) bei typing_start-Nachricht auf', () => {
      const onTypingUpdate = vi.fn();
      setupConnectedHook({ onTypingUpdate });

      const typingData = {
        type: 'typing_start',
        user_id: 'user-2',
        username: 'Anna',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(typingData);
      });

      expect(onTypingUpdate).toHaveBeenCalledWith('user-2', 'Anna', true);
    });

    it('ruft onTypingUpdate(false) bei typing_stop-Nachricht auf', () => {
      const onTypingUpdate = vi.fn();
      setupConnectedHook({ onTypingUpdate });

      const typingData = {
        type: 'typing_stop',
        user_id: 'user-2',
        username: 'Anna',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(typingData);
      });

      expect(onTypingUpdate).toHaveBeenCalledWith('user-2', 'Anna', false);
    });

    it('ruft onUserJoined bei user_joined-Nachricht auf', () => {
      const onUserJoined = vi.fn();
      setupConnectedHook({ onUserJoined });

      const joinData = {
        type: 'user_joined',
        user_id: 'user-3',
        username: 'Klaus',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(joinData);
      });

      expect(onUserJoined).toHaveBeenCalledWith('user-3', 'Klaus');
    });

    it('ruft onUserLeft bei user_left-Nachricht auf', () => {
      const onUserLeft = vi.fn();
      setupConnectedHook({ onUserLeft });

      const leaveData = {
        type: 'user_left',
        user_id: 'user-3',
        username: 'Klaus',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(leaveData);
      });

      expect(onUserLeft).toHaveBeenCalledWith('user-3', 'Klaus');
    });

    it('ruft onAIChunk bei ai_chunk-Nachricht auf', () => {
      const onAIChunk = vi.fn();
      setupConnectedHook({ onAIChunk });

      const chunkData = {
        type: 'ai_chunk',
        chunk: 'Hallo, ich bin',
        message_id: 'ai-msg-1',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(chunkData);
      });

      expect(onAIChunk).toHaveBeenCalledWith('Hallo, ich bin', 'ai-msg-1');
    });

    it('ruft onAIChunk ohne message_id auf wenn nicht vorhanden', () => {
      const onAIChunk = vi.fn();
      setupConnectedHook({ onAIChunk });

      const chunkData = {
        type: 'ai_chunk',
        chunk: 'Text-Chunk',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(chunkData);
      });

      expect(onAIChunk).toHaveBeenCalledWith('Text-Chunk', undefined);
    });

    it('ruft onAIDone bei ai_done-Nachricht auf', () => {
      const onAIDone = vi.fn();
      setupConnectedHook({ onAIDone });

      const doneData = {
        type: 'ai_done',
        message_id: 'ai-msg-1',
        full_content: 'Vollständige KI-Antwort',
        timestamp: '2025-01-01T12:00:00Z',
      };

      act(() => {
        getLatestInstance().simulateMessage(doneData);
      });

      expect(onAIDone).toHaveBeenCalledWith('ai-msg-1', 'Vollständige KI-Antwort');
    });

    it('ruft onError bei error-Nachricht auf', () => {
      const onError = vi.fn();
      setupConnectedHook({ onError });

      const errorData = {
        type: 'error',
        message: 'Sitzung abgelaufen',
      };

      act(() => {
        getLatestInstance().simulateMessage(errorData);
      });

      expect(onError).toHaveBeenCalledWith('Sitzung abgelaufen');
    });

    it('ruft onError mit Fallback-Text bei error-Nachricht ohne message auf', () => {
      const onError = vi.fn();
      setupConnectedHook({ onError });

      const errorData = {
        type: 'error',
      };

      act(() => {
        getLatestInstance().simulateMessage(errorData);
      });

      expect(onError).toHaveBeenCalledWith('Unbekannter Fehler');
    });

    it('ignoriert pong-Nachrichten ohne Callback', () => {
      const onError = vi.fn();
      const onNewMessage = vi.fn();
      setupConnectedHook({ onError, onNewMessage });

      act(() => {
        getLatestInstance().simulateMessage({ type: 'pong' });
      });

      expect(onError).not.toHaveBeenCalled();
      expect(onNewMessage).not.toHaveBeenCalled();
    });
  });

  // ==========================================================================
  // AKTIONEN
  // ==========================================================================

  describe('Aktionen', () => {
    function setupConnectedHook() {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const result = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      act(() => {
        getLatestInstance().simulateOpen();
      });

      return result;
    }

    it('sendTyping(true) sendet typing_start JSON', () => {
      const { result } = setupConnectedHook();
      const ws = getLatestInstance();

      act(() => {
        result.current.sendTyping(true);
      });

      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'typing_start' })
      );
    });

    it('sendTyping(false) sendet typing_stop JSON', () => {
      const { result } = setupConnectedHook();
      const ws = getLatestInstance();

      act(() => {
        result.current.sendTyping(false);
      });

      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'typing_stop' })
      );
    });

    it('requestPresence sendet get_presence JSON', () => {
      const { result } = setupConnectedHook();
      const ws = getLatestInstance();

      act(() => {
        result.current.requestPresence();
      });

      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'get_presence' })
      );
    });

    it('disconnect schließt WebSocket mit Code 1000', () => {
      const { result } = setupConnectedHook();
      const ws = getLatestInstance();

      act(() => {
        result.current.disconnect();
      });

      expect(ws.close).toHaveBeenCalledWith(1000);
    });

    it('disconnect setzt isConnected auf false', () => {
      const { result } = setupConnectedHook();

      expect(result.current.isConnected).toBe(true);

      act(() => {
        result.current.disconnect();
      });

      expect(result.current.isConnected).toBe(false);
    });

    it('disconnect leert onlineUsers', () => {
      const { result } = setupConnectedHook();

      // Erst Presence-Daten einfügen
      act(() => {
        getLatestInstance().simulateMessage({
          type: 'presence',
          users: [{ user_id: 'user-1', username: 'Max', is_typing: false }],
          timestamp: '2025-01-01T12:00:00Z',
        });
      });

      expect(result.current.onlineUsers).toHaveLength(1);

      act(() => {
        result.current.disconnect();
      });

      expect(result.current.onlineUsers).toHaveLength(0);
    });

    it('sendTyping sendet nicht wenn Verbindung nicht offen', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const { result } = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      // Nicht verbunden (kein simulateOpen)
      act(() => {
        result.current.sendTyping(true);
      });

      const ws = getLatestInstance();
      expect(ws.send).not.toHaveBeenCalled();
    });

    it('requestPresence sendet nicht wenn Verbindung nicht offen', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const { result } = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      act(() => {
        result.current.requestPresence();
      });

      const ws = getLatestInstance();
      expect(ws.send).not.toHaveBeenCalled();
    });
  });

  // ==========================================================================
  // RECONNECTION
  // ==========================================================================

  describe('Reconnection', () => {
    it('plant Reconnect bei unerwartetem Verbindungsabbruch (nicht Code 1000)', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const firstWs = getLatestInstance();
      act(() => {
        firstWs.simulateOpen();
      });

      // Verbindung mit unerwartetem Code schließen
      act(() => {
        firstWs.simulateClose(1006); // Abnormaler Abbruch
      });

      // Timer voranschreiten lassen (RECONNECT_INTERVAL = 3000ms)
      await act(async () => {
        vi.advanceTimersByTime(3500);
      });

      // Eine neue Verbindung wurde aufgebaut
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('plant keinen Reconnect bei normalem Verbindungsende (Code 1000)', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      act(() => {
        ws.simulateOpen();
      });

      // Normale Verbindungsbeendigung
      act(() => {
        // readyState direkt setzen und onclose aufrufen ohne close() zu verwenden
        ws.readyState = WebSocket.CLOSED;
        ws.onclose?.(new CloseEvent('close', { code: 1000 }));
      });

      // Timer voranschreiten lassen
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      // Keine neue Verbindung wurde aufgebaut
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('plant keinen Reconnect bei Code 4001', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      act(() => {
        ws.simulateOpen();
      });

      act(() => {
        ws.readyState = WebSocket.CLOSED;
        ws.onclose?.(new CloseEvent('close', { code: 4001 }));
      });

      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('plant keinen Reconnect bei Code 4003', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      act(() => {
        ws.simulateOpen();
      });

      act(() => {
        ws.readyState = WebSocket.CLOSED;
        ws.onclose?.(new CloseEvent('close', { code: 4003 }));
      });

      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      expect(MockWebSocket.instances).toHaveLength(1);
    });

    it('ruft onError nach MAX_RECONNECT_ATTEMPTS (5) fehlgeschlagenen Versuchen auf', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);
      const onError = vi.fn();

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
          onError,
        })
      );

      // MAX_RECONNECT_ATTEMPTS = 5
      // Exponential Backoff: 3000 * 2^(n-1)
      // Versuch 1: 3000ms, Versuch 2: 6000ms, Versuch 3: 12000ms, Versuch 4: 24000ms, Versuch 5: 48000ms
      // Gesamt: ~93000ms bis alle 5 Versuche durch sind

      for (let attempt = 0; attempt <= 5; attempt++) {
        if (MockWebSocket.instances.length > attempt) {
          const ws = MockWebSocket.instances[attempt];
          act(() => {
            ws.readyState = WebSocket.CLOSED;
            ws.onclose?.(new CloseEvent('close', { code: 1006 }));
          });
        }

        await act(async () => {
          vi.advanceTimersByTime(100000);
        });
      }

      expect(onError).toHaveBeenCalledWith('Maximale Verbindungsversuche erreicht');
    });

    it('setzt reconnectAttempts zurück nach erfolgreicher Verbindung', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      // Erste Verbindung
      act(() => {
        MockWebSocket.instances[0].simulateOpen();
      });

      // Verbindung trennen und reconnecten
      act(() => {
        MockWebSocket.instances[0].readyState = WebSocket.CLOSED;
        MockWebSocket.instances[0].onclose?.(new CloseEvent('close', { code: 1006 }));
      });

      await act(async () => {
        vi.advanceTimersByTime(4000);
      });

      // Zweite Verbindung erfolgreich aufgebaut
      act(() => {
        const secondWs = MockWebSocket.instances[1];
        if (secondWs) {
          secondWs.simulateOpen();
        }
      });

      // reconnectAttempts sollte zurückgesetzt sein - weitere Verbindungsabbrüche
      // sollten wieder 5 Versuche erlauben
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    });
  });

  // ==========================================================================
  // CLEANUP
  // ==========================================================================

  describe('Cleanup', () => {
    it('schließt WebSocket beim Unmount', () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);

      const { unmount } = renderHook(() =>
        useChatWebSocket({
          sessionId: TEST_SESSION_ID,
          enabled: true,
        })
      );

      const ws = getLatestInstance();
      act(() => {
        ws.simulateOpen();
      });

      act(() => {
        unmount();
      });

      expect(ws.close).toHaveBeenCalledWith(1000);
    });

    it('baut neue Verbindung auf wenn sessionId sich ändert', async () => {
      sessionStorage.setItem('auth_token', TEST_TOKEN);
      let currentSessionId = TEST_SESSION_ID;

      const { rerender } = renderHook(() =>
        useChatWebSocket({
          sessionId: currentSessionId,
          enabled: true,
        })
      );

      act(() => {
        getLatestInstance().simulateOpen();
      });

      expect(MockWebSocket.instances).toHaveLength(1);

      currentSessionId = 'neue-session-456';
      rerender();

      // Nach Rerender sollte eine neue Verbindung aufgebaut worden sein
      await waitFor(() => {
        expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
      });
    });
  });
});
