import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock logger before importing the module
vi.mock('@/lib/logger', () => ({
  logger: {
    withLabels: () => ({
      debug: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
    }),
  },
}));

// Mock React hooks (module uses them at top-level)
vi.mock('react', () => ({
  useEffect: vi.fn(),
  useCallback: vi.fn((fn: unknown) => fn),
  useRef: vi.fn((val: unknown) => ({ current: val })),
  useState: vi.fn((val: unknown) => [val, vi.fn()]),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: vi.fn(() => ({
    invalidateQueries: vi.fn(),
  })),
}));

import RealtimeWebSocketClient from '@/lib/websocket';

describe('RealtimeWebSocketClient - Token Handling', () => {
  let capturedUrls: string[];

  // Use a proper class mock so `new WebSocket(url)` works correctly
  class MockWebSocket {
    static OPEN = 1;
    static CLOSED = 3;
    static CONNECTING = 0;
    static CLOSING = 2;

    onopen: ((ev: Event) => void) | null = null;
    onclose: ((ev: CloseEvent) => void) | null = null;
    onerror: ((ev: Event) => void) | null = null;
    onmessage: ((ev: MessageEvent) => void) | null = null;
    readyState = 1;
    close = vi.fn();
    send = vi.fn();

    constructor(url: string) {
      capturedUrls.push(url);
    }
  }

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    capturedUrls = [];

    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('sollte Token mit Sonderzeichen via encodeURIComponent in URL kodieren', () => {
    const specialToken = 'token+with=special&chars#hash';
    sessionStorage.setItem('auth_token', specialToken);

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect(specialToken);

    expect(capturedUrls).toHaveLength(1);
    expect(capturedUrls[0]).toContain(`token=${encodeURIComponent(specialToken)}`);
    // Raw special characters must NOT appear unencoded in the query string
    expect(capturedUrls[0]).not.toContain('token+with=special&chars#hash');
  });

  it('sollte frischen Token aus sessionStorage bei Verbindungsaufbau holen', () => {
    const initialToken = 'initial-token';
    const freshToken = 'fresh-session-token';

    // Fresh token in sessionStorage overrides the connect() parameter
    sessionStorage.setItem('auth_token', freshToken);

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect(initialToken);

    expect(capturedUrls[0]).toContain(`token=${encodeURIComponent(freshToken)}`);
  });

  it('sollte sessionStorage verwenden, nicht localStorage', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'session-token');
    localStorage.setItem('auth_token', 'local-token');

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('test-token');

    expect(sessionSpy).toHaveBeenCalledWith('auth_token');
    expect(localSpy).not.toHaveBeenCalled();

    sessionSpy.mockRestore();
    localSpy.mockRestore();
  });

  it('sollte Key auth_token verwenden', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'correct-token');

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('test-token');

    const calledKeys = sessionSpy.mock.calls.map((c) => c[0]);
    expect(calledKeys).toContain('auth_token');

    sessionSpy.mockRestore();
  });

  it('sollte connect-Token als Fallback verwenden wenn kein sessionStorage-Token', () => {
    // sessionStorage is empty - no auth_token set
    const connectToken = 'connect-fallback-token';

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect(connectToken);

    expect(capturedUrls[0]).toContain(`token=${encodeURIComponent(connectToken)}`);
  });

  it('sollte Unicode-Token korrekt kodieren', () => {
    const unicodeToken = 'tökén-with-ümlautß';
    sessionStorage.setItem('auth_token', unicodeToken);

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect(unicodeToken);

    expect(capturedUrls[0]).toContain(`token=${encodeURIComponent(unicodeToken)}`);
    // Verify encoding actually happened (ö -> %C3%B6)
    expect(capturedUrls[0]).toContain('%C3');
  });
});
