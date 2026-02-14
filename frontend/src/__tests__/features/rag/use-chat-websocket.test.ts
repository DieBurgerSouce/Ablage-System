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

  it('sollte Token in WebSocket-URL einbetten bei connect()', () => {
    sessionStorage.setItem('auth_token', 'token+with=special&chars');

    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect('session-456');
    });

    expect(wsConstructorCalls).toHaveLength(1);
    expect(wsConstructorCalls[0]).toContain('token=token%2Bwith%3Dspecial%26chars');
  });

  it('sollte Fehler-Status setzen wenn kein Token vorhanden', () => {
    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect();
    });

    // Kein WebSocket erstellt
    expect(wsConstructorCalls).toHaveLength(0);
    // Error-State gesetzt
    expect(result.current.error).toBe('Nicht authentifiziert');
    expect(result.current.status).toBe('error');
  });

  it('sollte sessionStorage verwenden', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'test-token');

    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect('session-1');
    });

    expect(sessionSpy).toHaveBeenCalledWith('auth_token');
    expect(localSpy).not.toHaveBeenCalled();

    sessionSpy.mockRestore();
    localSpy.mockRestore();
  });

  it('sollte Key auth_token verwenden', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'test-token');

    const { result } = renderHook(() =>
      useChatWebSocket({ autoConnect: false })
    );

    act(() => {
      result.current.connect('session-1');
    });

    const calls = sessionSpy.mock.calls.map((c) => c[0]);
    expect(calls).toContain('auth_token');
    expect(calls).not.toContain('access_token');

    sessionSpy.mockRestore();
  });
});
