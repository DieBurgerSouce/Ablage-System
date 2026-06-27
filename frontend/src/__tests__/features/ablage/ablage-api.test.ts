import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadDocument, processDocumentOCR } from '@/features/ablage/api/ablage-api';

// Mock apiClient (wird von anderen Funktionen in ablage-api benoetigt)
vi.mock('@/lib/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

/**
 * Mock-XMLHttpRequest: haelt die abgesendete Anfrage fest (Methode, URL,
 * withCredentials, Header) und loest den load-Handler mit einer Erfolgs-
 * antwort aus, damit das Promise resolved. So koennen wir das Cookie-Auth-
 * Verhalten pruefen, ohne einen echten Netzwerk-Request abzusetzen.
 */
class MockXHR {
  static instances: MockXHR[] = [];

  upload = { addEventListener: vi.fn() };
  withCredentials = false;
  status = 0;
  responseText = '';
  method = '';
  url = '';
  requestHeaders: Record<string, string> = {};

  private listeners: Record<string, Array<() => void>> = {};

  constructor() {
    MockXHR.instances.push(this);
  }

  addEventListener(event: string, cb: () => void) {
    (this.listeners[event] ||= []).push(cb);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.requestHeaders[name] = value;
  }

  send() {
    // Erfolgreiche Server-Antwort simulieren -> load-Handler ausloesen.
    this.status = 200;
    this.responseText = JSON.stringify({ success: true });
    (this.listeners['load'] || []).forEach((cb) => cb());
  }
}

function clearCsrfCookie() {
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
}

const makeFile = () => new File(['test'], 'test.pdf', { type: 'application/pdf' });

/**
 * Hintergrund: ablage-api wurde auf httpOnly-Cookie-Auth umgestellt. Es gibt
 * KEINEN clientseitigen Token-Guard mehr (kein sessionStorage 'auth_token',
 * kein "Nicht authentifiziert"-Throw, kein Bearer-Header). Stattdessen sendet
 * der XHR mit withCredentials=true (httpOnly-Auth-Cookie) plus CSRF-Header
 * aus dem nicht-httpOnly csrf_token-Cookie. Der Server erzwingt Auth via 401.
 */
describe('ablage-api - Cookie-Auth (XHR mit withCredentials, kein Bearer)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    clearCsrfCookie();
    MockXHR.instances = [];
    vi.stubGlobal('XMLHttpRequest', MockXHR as unknown as typeof XMLHttpRequest);
  });

  afterEach(() => {
    sessionStorage.clear();
    clearCsrfCookie();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uploadDocument sendet die Anfrage mit withCredentials=true (Cookie-Auth)', async () => {
    await uploadDocument(makeFile(), { ocr_backend: 'deepseek' });

    const xhr = MockXHR.instances.at(-1)!;
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe('/ocr/process');
  });

  it('uploadDocument setzt KEINEN Authorization-Header und liest sessionStorage nicht fuer auth_token', async () => {
    const getItemSpy = vi.spyOn(sessionStorage, 'getItem');

    await uploadDocument(makeFile(), { ocr_backend: 'deepseek' });

    const xhr = MockXHR.instances.at(-1)!;
    // Kein Bearer/Authorization-Header mehr (httpOnly-Cookie ist clientseitig nicht lesbar).
    expect(xhr.requestHeaders).not.toHaveProperty('Authorization');
    // Es darf kein 'auth_token' aus sessionStorage gelesen werden.
    expect(getItemSpy).not.toHaveBeenCalledWith('auth_token');
  });

  it('uploadDocument spiegelt das csrf_token-Cookie in den X-CSRF-Token-Header', async () => {
    document.cookie = 'csrf_token=abc123';

    await uploadDocument(makeFile(), { ocr_backend: 'deepseek' });

    const xhr = MockXHR.instances.at(-1)!;
    expect(xhr.requestHeaders['X-CSRF-Token']).toBe('abc123');
  });

  it('processDocumentOCR sendet die Anfrage mit withCredentials=true (Cookie-Auth)', async () => {
    await processDocumentOCR(makeFile());

    const xhr = MockXHR.instances.at(-1)!;
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.method).toBe('POST');
    expect(xhr.url).toBe('/ocr/process');
  });

  it('processDocumentOCR setzt KEINEN Authorization-Header und liest sessionStorage nicht fuer auth_token', async () => {
    const getItemSpy = vi.spyOn(sessionStorage, 'getItem');

    await processDocumentOCR(makeFile());

    const xhr = MockXHR.instances.at(-1)!;
    expect(xhr.requestHeaders).not.toHaveProperty('Authorization');
    expect(getItemSpy).not.toHaveBeenCalledWith('auth_token');
  });
});
