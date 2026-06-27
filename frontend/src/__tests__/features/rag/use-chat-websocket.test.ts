import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatWebSocket } from '@/features/rag/hooks/use-chat-websocket';

// Mock logger to prevent console noise
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

describe('useChatWebSocket (features/rag) - Token Storage Integration', () => {
  let wsConstructorCalls: string[];

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    wsConstructorCalls = [];

    // Use a real class so `new WebSocket(url)` works
    const MockWS = class {
      close = vi.fn();
      send = vi.fn();
      onopen: ((ev: Event) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      readyState = 0;
      static OPEN = 1;
      static CLOSED = 3;
      static CONNECTING = 0;
      static CLOSING = 2;

      constructor(url: string) {
        wsConstructorCalls.push(url);
      }
    };
    vi.stubGlobal('WebSocket', MockWS);
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // Cookie-Auth (G03): Kein JS-Token mehr — das httpOnly-Auth-Cookie wird beim
  // Same-Origin-WebSocket-Handshake automatisch mitgesendet. connect() baut die
  // Verbindung ohne token-Query-Parameter auf und liest keinen sessionStorage-Token.

  it('sollte WebSocket bei connect() mit Cookie-Auth aufbauen (URL ohne token-Query-Parameter)', () => {
    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect('session-456');
    });

    expect(wsConstructorCalls).toHaveLength(1);
    // Kein Token in der URL
    expect(wsConstructorCalls[0]).not.toContain('token=');
    expect(wsConstructorCalls[0]).not.toContain('auth_token');
    // Die Session-ID steht im Pfad
    expect(wsConstructorCalls[0]).toContain('session-456');
  });

  it('sollte Verbindung auch ohne sessionStorage-Token aufbauen (kein Fehler-Status)', () => {
    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect();
    });

    // Same-Origin-Handshake sendet das Auth-Cookie automatisch — Verbindung wird aufgebaut
    expect(wsConstructorCalls).toHaveLength(1);
    // Kein clientseitiger "kein Token"-Fehler mehr
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBe('connecting');
  });

  it('sollte sessionStorage NICHT fuer auth_token lesen', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect('session-1');
    });

    // Cookie-Auth: Der Hook liest keinen Token mehr aus Storage
    expect(sessionSpy).not.toHaveBeenCalledWith('auth_token');
    expect(localSpy).not.toHaveBeenCalledWith('auth_token');

    sessionSpy.mockRestore();
    localSpy.mockRestore();
  });
});
