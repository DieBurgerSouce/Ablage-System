import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendMessage, listSessions } from '@/features/rag/api/chat-api';

describe('RAG Chat API - Token Storage Integration', () => {
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

  it('sollte Token aus sessionStorage als Bearer-Header senden', async () => {
    sessionStorage.setItem('auth_token', 'test-chat-token-456');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ session_id: 's1', message: 'ok', sources: [] }),
    });

    await sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0]);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer test-chat-token-456',
      })
    );
  });

  it('sollte Fehler werfen wenn kein Token vorhanden', async () => {
    await expect(
      sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0])
    ).rejects.toThrow('Nicht authentifiziert');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('sollte Whitespace-Token als nicht authentifiziert behandeln', async () => {
    sessionStorage.setItem('auth_token', '   ');
    await expect(
      sendMessage({ message: 'Hallo' } as Parameters<typeof sendMessage>[0])
    ).rejects.toThrow('Nicht authentifiziert');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('sollte sessionStorage verwenden, nicht localStorage', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'test-token');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ sessions: [] }),
    });

    await listSessions();

    expect(sessionSpy).toHaveBeenCalledWith('auth_token');
    expect(localSpy).not.toHaveBeenCalled();

    sessionSpy.mockRestore();
    localSpy.mockRestore();
  });

  it('sollte Key auth_token verwenden, nicht access_token', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'correct-token');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ sessions: [] }),
    });

    await listSessions();

    const calls = sessionSpy.mock.calls.map((c) => c[0]);
    expect(calls).toContain('auth_token');
    expect(calls).not.toContain('access_token');

    sessionSpy.mockRestore();
  });

  it('sollte Fehlerresponse korrekt verarbeiten', async () => {
    sessionStorage.setItem('auth_token', 'test-token');
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
