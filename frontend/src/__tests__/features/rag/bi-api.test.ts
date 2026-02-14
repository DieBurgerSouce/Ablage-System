import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { queryBI } from '@/features/rag/api/bi-api';

describe('RAG BI API - Token Storage Integration', () => {
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
    sessionStorage.setItem('auth_token', 'test-bi-token-123');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ query_type: 'summary', summary: 'ok', data: null, suggestions: [], query_time_ms: 10 }),
    });

    await queryBI({ query: 'Umsatz' });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer test-bi-token-123',
      })
    );
  });

  it('sollte Fehler werfen wenn kein Token vorhanden', async () => {
    await expect(queryBI({ query: 'Umsatz' })).rejects.toThrow('Nicht authentifiziert');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('sollte sessionStorage verwenden, nicht localStorage', async () => {
    const sessionSpy = vi.spyOn(sessionStorage, 'getItem');
    const localSpy = vi.spyOn(localStorage, 'getItem');

    sessionStorage.setItem('auth_token', 'test-token');
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ query_type: 'summary', summary: '', data: null, suggestions: [], query_time_ms: 0 }),
    });

    await queryBI({ query: 'Test' });

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
      json: () => Promise.resolve({ query_type: 'summary', summary: '', data: null, suggestions: [], query_time_ms: 0 }),
    });

    await queryBI({ query: 'Test' });

    const calls = sessionSpy.mock.calls.map((c) => c[0]);
    expect(calls).toContain('auth_token');
    expect(calls).not.toContain('access_token');

    sessionSpy.mockRestore();
  });

  it('sollte Fehlerresponse korrekt verarbeiten', async () => {
    sessionStorage.setItem('auth_token', 'test-token');
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Interner Serverfehler' }),
    });

    await expect(queryBI({ query: 'Umsatz' })).rejects.toThrow('Interner Serverfehler');
  });
});
