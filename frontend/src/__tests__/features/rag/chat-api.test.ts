import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendMessage, listSessions } from '@/features/rag/api/chat-api';

/**
 * G03: Diese Suite prueft das NEUE Cookie-/CSRF-Auth-Verhalten von fetchWithAuth
 * (Umstellung von Bearer-Token auf httpOnly-Cookie):
 *  - fetch wird mit credentials:'include' aufgerufen (Auth-Cookie automatisch)
 *  - es wird KEIN Authorization: Bearer-Header mehr gesetzt
 *  - sessionStorage wird NICHT mehr fuer auth_token gelesen
 *  - bei state-changing Requests (POST) wird das X-CSRF-Token aus dem
 *    csrf_token-Cookie gespiegelt; bei GET hingegen nicht
 */
describe('RAG Chat API - Cookie/CSRF Auth Integration', () => {
  const mockFetch = vi.fn();

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
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ session_id: 's1', message: 'ok', sources: [] }),
    });

    await sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0]);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.credentials).toBe('include');
  });

  it('sollte KEINEN Authorization-Header setzen', async () => {
    // Selbst ein veraltetes Token im sessionStorage darf nicht verwendet werden
    sessionStorage.setItem('auth_token', 'veraltetes-token');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ session_id: 's1', message: 'ok', sources: [] }),
    });

    await sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0]);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
  });

  it('sollte sessionStorage NICHT fuer auth_token lesen', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ sessions: [] }),
    });

    await listSessions();

    const keys = sessionSpy.mock.calls.map((c) => c[0]);
    expect(keys).not.toContain('auth_token');

    sessionSpy.mockRestore();
  });

  it('sollte bei POST das X-CSRF-Token aus dem csrf_token-Cookie senden', async () => {
    document.cookie = 'csrf_token=csrf-chat-789';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ session_id: 's1', message: 'ok', sources: [] }),
    });

    await sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0]);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).toEqual(
      expect.objectContaining({ 'X-CSRF-Token': 'csrf-chat-789' })
    );
  });

  it('sollte ohne csrf_token-Cookie keinen X-CSRF-Token-Header senden (POST)', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ session_id: 's1', message: 'ok', sources: [] }),
    });

    await sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0]);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('X-CSRF-Token');
  });

  it('sollte bei GET (listSessions) keinen X-CSRF-Token-Header senden', async () => {
    // Auch mit gesetztem Cookie: GET ist nicht state-changing -> kein CSRF-Header
    document.cookie = 'csrf_token=csrf-chat-789';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ sessions: [] }),
    });

    await listSessions();

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty('X-CSRF-Token');
  });

  it('sollte Fehlerresponse korrekt verarbeiten', async () => {
    // Nicht auth-bezogen: detail-Fehlermeldung wird als Error geworfen
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Zugriff verweigert' }),
    });

    await expect(
      sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0])
    ).rejects.toThrow('Zugriff verweigert');
  });
});
