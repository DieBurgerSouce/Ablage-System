import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { chatApi } from '@/lib/api/chat-api';

// Mock apiClient - sendMessageStream uses raw fetch, not apiClient
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    defaults: { baseURL: '/api/v1' },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('Chat API (lib) - Token Storage Integration', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.stubGlobal('fetch', mockFetch);
    mockFetch.mockReset();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('sollte Token aus sessionStorage als Bearer-Header in sendMessageStream senden', async () => {
    sessionStorage.setItem('auth_token', 'test-stream-token-789');

    // Mock SSE response with ReadableStream
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"done","session_id":"s1","message_id":"m1"}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
    });

    const onDone = vi.fn();
    await chatApi.sendMessageStream('Hallo', 'session-1', { onDone });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer test-stream-token-789',
      })
    );
  });

  it('sollte ohne Token keinen Authorization-Header setzen', async () => {
    // lib/chat-api sendMessageStream setzt Token optional (kein throw)
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"done","session_id":"s1"}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
    });

    await chatApi.sendMessageStream('Hallo');

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
  });

  it('sollte sessionStorage verwenden, nicht localStorage', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'test-token');
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"done","session_id":"s1"}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
    });

    await chatApi.sendMessageStream('Test');

    expect(sessionSpy).toHaveBeenCalledWith('auth_token');
    expect(localSpy).not.toHaveBeenCalled();

    sessionSpy.mockRestore();
    localSpy.mockRestore();
  });

  it('sollte Key auth_token verwenden, nicht access_token', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'correct-token');
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"done","session_id":"s1"}\n\n'));
        controller.close();
      },
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: stream,
    });

    await chatApi.sendMessageStream('Test');

    const calls = sessionSpy.mock.calls.map((c) => c[0]);
    expect(calls).toContain('auth_token');
    expect(calls).not.toContain('access_token');

    sessionSpy.mockRestore();
  });

  it('sollte Fehlerresponse korrekt an onError weiterleiten', async () => {
    sessionStorage.setItem('auth_token', 'test-token');

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    const onError = vi.fn();
    await chatApi.sendMessageStream('Hallo', undefined, { onError });

    expect(onError).toHaveBeenCalledWith('HTTP 500: Internal Server Error');
  });
});
