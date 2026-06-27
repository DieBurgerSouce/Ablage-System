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

  // Cookie-Auth (G03): Der Auth-Token wird nicht mehr als Query-Parameter
  // uebergeben oder aus sessionStorage gelesen. Same-Origin-WebSocket-
  // Handshakes senden das httpOnly-Cookie automatisch mit; fehlt das Cookie,
  // schliesst der Server die Verbindung selbst (Code 4001).

  it('sollte WebSocket-URL ohne token-Query-Parameter aufbauen (Cookie-Auth)', () => {
    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('beliebiger-wert');

    expect(capturedUrls).toHaveLength(1);
    // Kein Token mehr in der URL
    expect(capturedUrls[0]).not.toContain('token=');
    expect(capturedUrls[0]).not.toContain('auth_token');
    // Der Realtime-Endpoint wird korrekt angesteuert
    expect(capturedUrls[0]).toContain('/api/v1/ws/realtime');
  });

  it('sollte Verbindung auch ohne sessionStorage-Token aufbauen (kein Token-Guard mehr)', () => {
    // sessionStorage ist leer — bei Cookie-Auth darf das die Verbindung NICHT verhindern
    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('');

    // Das httpOnly-Cookie wird beim Handshake automatisch mitgesendet;
    // einen clientseitigen "kein Token"-Abbruch-Guard gibt es nicht mehr.
    expect(capturedUrls).toHaveLength(1);
    expect(capturedUrls[0]).not.toContain('token=');
  });

  it('sollte sessionStorage NICHT fuer auth_token lesen', () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('test-token');

    // Cookie-Auth: Der Client liest keinen Token mehr aus sessionStorage
    expect(sessionSpy).not.toHaveBeenCalledWith('auth_token');

    sessionSpy.mockRestore();
  });

  it('sollte localStorage NICHT fuer auth_token lesen', () => {
    const localSpy = vi.spyOn(localStorage, 'getItem');

    const client = new RealtimeWebSocketClient('localhost:8000');
    client.connect('test-token');

    expect(localSpy).not.toHaveBeenCalledWith('auth_token');

    localSpy.mockRestore();
  });
});
