import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { listEmployees } from '@/features/personal/api/personal-api';

/**
 * Hintergrund: personal-api (apiRequest) wurde auf httpOnly-Cookie-Auth
 * umgestellt. Es gibt KEINEN clientseitigen Token-Guard mehr (kein
 * sessionStorage 'auth_token', kein "Nicht authentifiziert"-Throw, kein
 * Bearer-Header). Stattdessen sendet fetch() mit credentials:'include'
 * (httpOnly-Auth-Cookie); CSRF wird nur bei state-changing Requests
 * gespiegelt. Der Server erzwingt Auth via 401.
 */
describe('personal-api - Cookie-Auth (fetch mit credentials:include, kein Bearer)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [], total: 0, page: 1, per_page: 20 }),
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('apiRequest sendet die Anfrage mit credentials:"include" (Cookie-Auth)', async () => {
    await listEmployees();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe('include');
  });

  it('apiRequest setzt KEINEN Authorization-Header (kein Bearer mehr)', async () => {
    await listEmployees();

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers).not.toHaveProperty('Authorization');
    expect(options.headers['Content-Type']).toBe('application/json');
  });

  it('apiRequest liest sessionStorage NICHT fuer auth_token', async () => {
    const getItemSpy = vi.spyOn(sessionStorage, 'getItem');

    await listEmployees();

    // current_company_id darf gelesen werden, 'auth_token' aber niemals.
    expect(getItemSpy).not.toHaveBeenCalledWith('auth_token');
  });

  it('apiRequest sendet bei GET keinen X-CSRF-Token-Header (nur bei state-changing Requests)', async () => {
    await listEmployees();

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers).not.toHaveProperty('X-CSRF-Token');
  });
});
