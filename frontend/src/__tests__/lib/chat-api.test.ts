import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { chatApi } from '@/lib/api/chat-api';

// Mock apiClient - sendMessageStream nutzt rohes fetch, nicht apiClient
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    defaults: { baseURL: '/api/v1' },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

/**
 * G03: Diese Suite prueft das NEUE Cookie-/CSRF-Auth-Verhalten von
 * chatApi.sendMessageStream (Umstellung von Bearer-Token auf httpOnly-Cookie):
 *  - fetch wird mit credentials:'include' aufgerufen (Auth-Cookie wird
 *    automatisch mitgesendet)
 *  - es wird KEIN Authorization: Bearer-Header mehr gesetzt
 *  - sessionStorage wird NICHT mehr fuer auth_token gelesen
 *  - bei dem state-changing POST-Stream wird das X-CSRF-Token aus dem
 *    csrf_token-Cookie gespiegelt (Double-Submit), sofern ein Cookie vorliegt
 *  - es gibt KEINEN clientseitigen "kein Token -> Fehler"-Guard mehr;
 *    fehlt das Cookie, antwortet der Server mit 401
 */
describe('Chat API (lib) - Cookie/CSRF Auth Integration', () => {
  const mockFetch = vi.fn();

  // Erzeugt eine SSE-Stream-Response, die ein einzelnes done-Event liefert
  function makeStreamResponse() {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'data: {"type":"done","session_id":"s1","message_id":"m1"}\n\n'
          )
        );
        controller.close();
      },
    });
    return { ok: true, status: 200, body: stream };
  }

  // Loescht das csrf_token-Cookie (happy-dom: via Ablaufdatum in der Vergangenheit)
  function clearCsrfCookie() {
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  }

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    clearCsrfCookie();
    vi.stubGlobal('fetch', mockFetch);
    mockFetch.mockReset();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    clearCsrfCookie();
    vi.unstubAllGlobals();
  });

  it('sollte fetch mit credentials:"include" aufrufen (Cookie-Auth)', async () => {
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    const onDone = vi.fn();
    await chatApi.sendMessageStream('Hallo', 'session-1', { onDone });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.credentials).toBe('include');
    // Stream wurde verarbeitet -> done-Callback ausgeloest
    expect(onDone).toHaveBeenCalledWith('s1', 'm1');
  });

  it('sollte KEINEN Authorization-Header setzen', async () => {
    // Selbst ein veraltetes Token im sessionStorage darf nicht verwendet werden
    sessionStorage.setItem('auth_token', 'veraltetes-token');
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    await chatApi.sendMessageStream('Hallo', 'session-1', {});

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
  });

  it('sollte sessionStorage NICHT fuer auth_token lesen', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    await chatApi.sendMessageStream('Test');

    const keys = sessionSpy.mock.calls.map((c) => c[0]);
    expect(keys).not.toContain('auth_token');

    sessionSpy.mockRestore();
  });

  it('sollte fetch auch ohne Token aufrufen (kein Client-Guard mehr)', async () => {
    // Kein Token gesetzt -> der Request wird trotzdem abgesetzt; ein fehlendes
    // Cookie beantwortet der Server mit 401, es gibt keinen Client-seitigen Guard.
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    const onError = vi.fn();
    await chatApi.sendMessageStream('Hallo', undefined, { onError });

    expect(mockFetch).toHaveBeenCalledOnce();
    expect(onError).not.toHaveBeenCalled();
  });

  it('sollte bei gesetztem csrf_token-Cookie den X-CSRF-Token-Header senden (POST)', async () => {
    document.cookie = 'csrf_token=csrf-abc-123';
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    await chatApi.sendMessageStream('Hallo', 'session-1', {});

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).toEqual(
      expect.objectContaining({ 'X-CSRF-Token': 'csrf-abc-123' })
    );
  });

  it('sollte ohne csrf_token-Cookie keinen X-CSRF-Token-Header senden', async () => {
    mockFetch.mockResolvedValueOnce(makeStreamResponse());

    await chatApi.sendMessageStream('Hallo', 'session-1', {});

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('X-CSRF-Token');
  });

  it('sollte Fehlerresponse korrekt an onError weiterleiten', async () => {
    // Nicht auth-bezogen: HTTP-Fehler werden weiterhin an onError gereicht
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
