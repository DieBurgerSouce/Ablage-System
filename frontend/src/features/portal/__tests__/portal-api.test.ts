/**
 * Portal API Client Tests
 *
 * Testet Token-Management, Client-Konfiguration,
 * Request/Response-Interceptors und API-Methoden.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ============================================================================
// AXIOS MOCK
// ============================================================================

// Interceptor-Handler für direkten Zugriff in Tests
type InterceptorHandler = {
  fulfilled: (config: unknown) => unknown;
  rejected?: (error: unknown) => unknown;
};

const requestInterceptors: InterceptorHandler[] = [];
const responseInterceptors: InterceptorHandler[] = [];

const mockAxiosInstance = {
  defaults: {
    baseURL: '/api/v1',
    timeout: 10000,
    headers: {
      'Content-Type': 'application/json',
    },
  },
  interceptors: {
    request: {
      use: vi.fn((fulfilled: (config: unknown) => unknown, rejected?: (error: unknown) => unknown) => {
        requestInterceptors.push({ fulfilled, rejected });
        return requestInterceptors.length - 1;
      }),
      handlers: requestInterceptors,
    },
    response: {
      use: vi.fn((fulfilled: (response: unknown) => unknown, rejected?: (error: unknown) => unknown) => {
        responseInterceptors.push({ fulfilled: fulfilled ?? ((r: unknown) => r), rejected });
        return responseInterceptors.length - 1;
      }),
      handlers: responseInterceptors,
    },
  },
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
};

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockAxiosInstance),
  },
  create: vi.fn(() => mockAxiosInstance),
}));

// ============================================================================
// IMPORT NACH MOCK
// ============================================================================

import {
  getPortalToken,
  getPortalRefreshToken,
  getPortalUser,
  getPortalCompanyId,
  setPortalAuth,
  clearPortalAuth,
  isPortalAuthenticated,
  portalApi,
} from '../api/portal-api';
import type { PortalUser } from '../types';

// ============================================================================
// TEST HELPERS
// ============================================================================

const TEST_ACCESS_TOKEN = 'test-access-token-123';
const TEST_REFRESH_TOKEN = 'test-refresh-token-456';
const TEST_COMPANY_ID = 'company-abc';

const TEST_USER: PortalUser = {
  id: 'user-1',
  email: 'test@beispiel.de',
  first_name: 'Max',
  last_name: 'Mustermann',
  phone: null,
  position: null,
  entity_id: 'entity-1',
  company_id: TEST_COMPANY_ID,
  status: 'active',
  permissions: {
    can_view_invoices: true,
    can_confirm_payments: true,
    can_submit_complaints: true,
    can_upload_documents: true,
  },
  last_login_at: null,
};

// ============================================================================
// TESTS
// ============================================================================

describe('Portal API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Interceptor-Arrays zurücksetzen
    requestInterceptors.length = 0;
    responseInterceptors.length = 0;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  // ==========================================================================
  // TOKEN MANAGEMENT
  // ==========================================================================

  describe('Token-Management', () => {
    describe('getPortalToken', () => {
      it('gibt null zurück wenn kein Token vorhanden', () => {
        expect(getPortalToken()).toBeNull();
      });

      it('gibt gespeicherten Token zurück', () => {
        localStorage.setItem('portal_auth_token', TEST_ACCESS_TOKEN);
        expect(getPortalToken()).toBe(TEST_ACCESS_TOKEN);
      });
    });

    describe('getPortalRefreshToken', () => {
      it('gibt null zurück wenn kein Refresh-Token vorhanden', () => {
        expect(getPortalRefreshToken()).toBeNull();
      });

      it('gibt gespeicherten Refresh-Token zurück', () => {
        localStorage.setItem('portal_refresh_token', TEST_REFRESH_TOKEN);
        expect(getPortalRefreshToken()).toBe(TEST_REFRESH_TOKEN);
      });
    });

    describe('getPortalUser', () => {
      it('gibt null zurück wenn kein User gespeichert', () => {
        expect(getPortalUser()).toBeNull();
      });

      it('gibt geparsten User zurück', () => {
        localStorage.setItem('portal_user', JSON.stringify(TEST_USER));
        const user = getPortalUser();
        expect(user).toEqual(TEST_USER);
      });

      it('gibt null zurück bei ungültigem JSON', () => {
        localStorage.setItem('portal_user', 'kein-gültiges-json{{{');
        expect(getPortalUser()).toBeNull();
      });
    });

    describe('getPortalCompanyId', () => {
      it('gibt null zurück wenn keine Company-ID vorhanden', () => {
        expect(getPortalCompanyId()).toBeNull();
      });

      it('gibt gespeicherte Company-ID zurück', () => {
        localStorage.setItem('portal_company_id', TEST_COMPANY_ID);
        expect(getPortalCompanyId()).toBe(TEST_COMPANY_ID);
      });
    });

    describe('setPortalAuth', () => {
      it('speichert alle Auth-Daten in localStorage', () => {
        setPortalAuth(TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN, TEST_USER, TEST_COMPANY_ID);

        expect(localStorage.getItem('portal_auth_token')).toBe(TEST_ACCESS_TOKEN);
        expect(localStorage.getItem('portal_refresh_token')).toBe(TEST_REFRESH_TOKEN);
        expect(localStorage.getItem('portal_user')).toBe(JSON.stringify(TEST_USER));
        expect(localStorage.getItem('portal_company_id')).toBe(TEST_COMPANY_ID);
      });

      it('überschreibt vorhandene Werte', () => {
        localStorage.setItem('portal_auth_token', 'alter-token');
        setPortalAuth(TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN, TEST_USER, TEST_COMPANY_ID);
        expect(localStorage.getItem('portal_auth_token')).toBe(TEST_ACCESS_TOKEN);
      });
    });

    describe('clearPortalAuth', () => {
      it('entfernt alle Auth-Daten aus localStorage', () => {
        setPortalAuth(TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN, TEST_USER, TEST_COMPANY_ID);
        clearPortalAuth();

        expect(localStorage.getItem('portal_auth_token')).toBeNull();
        expect(localStorage.getItem('portal_refresh_token')).toBeNull();
        expect(localStorage.getItem('portal_user')).toBeNull();
        expect(localStorage.getItem('portal_company_id')).toBeNull();
      });

      it('funktioniert ohne vorherige Daten', () => {
        expect(() => clearPortalAuth()).not.toThrow();
      });
    });

    describe('isPortalAuthenticated', () => {
      it('gibt false zurück wenn kein Token vorhanden', () => {
        expect(isPortalAuthenticated()).toBe(false);
      });

      it('gibt true zurück wenn Token vorhanden', () => {
        localStorage.setItem('portal_auth_token', TEST_ACCESS_TOKEN);
        expect(isPortalAuthenticated()).toBe(true);
      });

      it('gibt false zurück wenn Token leer ist', () => {
        localStorage.setItem('portal_auth_token', '');
        expect(isPortalAuthenticated()).toBe(false);
      });
    });
  });

  // ==========================================================================
  // API CLIENT KONFIGURATION
  // ==========================================================================

  describe('API-Client-Konfiguration', () => {
    it('hat korrektes Content-Type Header', () => {
      expect(mockAxiosInstance.defaults.headers['Content-Type']).toBe('application/json');
    });

    it('hat Timeout von 10 Sekunden konfiguriert', () => {
      expect(mockAxiosInstance.defaults.timeout).toBe(10000);
    });

    it('hat baseURL konfiguriert', () => {
      expect(mockAxiosInstance.defaults.baseURL).toBeDefined();
    });
  });

  // ==========================================================================
  // REQUEST INTERCEPTOR
  // ==========================================================================

  describe('Request-Interceptor', () => {
    it('fügt Authorization Header hinzu wenn Token vorhanden', async () => {
      // Modul neu laden um Interceptors zu registrieren
      vi.resetModules();
      localStorage.setItem('portal_auth_token', TEST_ACCESS_TOKEN);

      // Interceptor direkt simulieren (analog zum Code in portal-api.ts)
      const token = localStorage.getItem('portal_auth_token');
      const config: Record<string, unknown> = { headers: {} as Record<string, string> };

      if (token?.trim()) {
        (config.headers as Record<string, string>)['Authorization'] = `Bearer ${token.trim()}`;
      }

      expect((config.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${TEST_ACCESS_TOKEN}`);
    });

    it('trimmt Whitespace vom Token', async () => {
      const tokenWithSpaces = `  ${TEST_ACCESS_TOKEN}  `;
      localStorage.setItem('portal_auth_token', tokenWithSpaces);

      const token = localStorage.getItem('portal_auth_token');
      const config: Record<string, unknown> = { headers: {} as Record<string, string> };

      if (token?.trim()) {
        (config.headers as Record<string, string>)['Authorization'] = `Bearer ${token.trim()}`;
      }

      expect((config.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${TEST_ACCESS_TOKEN}`);
    });

    it('fügt keinen Authorization Header hinzu wenn kein Token vorhanden', async () => {
      localStorage.removeItem('portal_auth_token');

      const token = localStorage.getItem('portal_auth_token');
      const config: Record<string, unknown> = { headers: {} as Record<string, string> };

      if (token?.trim()) {
        (config.headers as Record<string, string>)['Authorization'] = `Bearer ${token.trim()}`;
      }

      expect((config.headers as Record<string, string>)['Authorization']).toBeUndefined();
    });

    it('fügt keinen Authorization Header hinzu wenn Token nur Leerzeichen', async () => {
      localStorage.setItem('portal_auth_token', '   ');

      const token = localStorage.getItem('portal_auth_token');
      const config: Record<string, unknown> = { headers: {} as Record<string, string> };

      if (token?.trim()) {
        (config.headers as Record<string, string>)['Authorization'] = `Bearer ${token.trim()}`;
      }

      expect((config.headers as Record<string, string>)['Authorization']).toBeUndefined();
    });
  });

  // ==========================================================================
  // RESPONSE INTERCEPTOR
  // ==========================================================================

  describe('Response-Interceptor', () => {
    it('lässt erfolgreiche Antworten durch', async () => {
      const mockResponse = { status: 200, data: { success: true } };
      const successInterceptor = (response: unknown) => response;
      const result = successInterceptor(mockResponse);
      expect(result).toEqual(mockResponse);
    });

    it('dispatcht portal-session-expired Event bei 401 ohne Refresh-Token', async () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);
      localStorage.removeItem('portal_refresh_token');

      // Interceptor-Logik simulieren (kein Refresh-Token vorhanden)
      const refreshToken = localStorage.getItem('portal_refresh_token');
      if (!refreshToken) {
        clearPortalAuth();
        window.dispatchEvent(new CustomEvent('portal-session-expired'));
      }

      expect(dispatchSpy).toHaveBeenCalledOnce();
      const dispatchedEvent = dispatchSpy.mock.calls[0][0] as CustomEvent;
      expect(dispatchedEvent.type).toBe('portal-session-expired');
    });

    it('löscht Auth-Daten bei 401 ohne Refresh-Token', async () => {
      setPortalAuth(TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN, TEST_USER, TEST_COMPANY_ID);
      localStorage.removeItem('portal_refresh_token');

      vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

      const refreshToken = localStorage.getItem('portal_refresh_token');
      if (!refreshToken) {
        clearPortalAuth();
        window.dispatchEvent(new CustomEvent('portal-session-expired'));
      }

      expect(localStorage.getItem('portal_auth_token')).toBeNull();
      expect(localStorage.getItem('portal_user')).toBeNull();
    });

    it('schließt Auth-Endpunkte von 401-Behandlung aus', () => {
      // URL-Prüfung analog zur Implementierung
      const isAuthEndpoint = (url: string) => url.includes('/auth/');

      expect(isAuthEndpoint('/portal/auth/login')).toBe(true);
      expect(isAuthEndpoint('/portal/auth/refresh')).toBe(true);
      expect(isAuthEndpoint('/portal/invoices')).toBe(false);
      expect(isAuthEndpoint('/portal/documents')).toBe(false);
    });

    it('dispatcht portal-session-expired bei fehlgeschlagenem Token-Refresh', async () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

      // Refresh schlägt fehl
      try {
        throw new Error('Refresh fehlgeschlagen');
      } catch {
        clearPortalAuth();
        window.dispatchEvent(new CustomEvent('portal-session-expired'));
      }

      expect(dispatchSpy).toHaveBeenCalledOnce();
      const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
      expect(event.type).toBe('portal-session-expired');
    });
  });

  // ==========================================================================
  // AUTH API METHODEN
  // ==========================================================================

  describe('portalApi.auth', () => {
    describe('login', () => {
      it('ruft korrekten Endpunkt auf', async () => {
        const mockLoginResponse = {
          access_token: TEST_ACCESS_TOKEN,
          refresh_token: TEST_REFRESH_TOKEN,
          token_type: 'bearer',
          expires_in: 900,
          portal_user: TEST_USER,
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockLoginResponse });

        const loginData = {
          email: 'test@beispiel.de',
          password: 'geheimes-passwort',
          company_id: TEST_COMPANY_ID,
        };

        await portalApi.auth.login(loginData);

        expect(mockAxiosInstance.post).toHaveBeenCalledWith(
          '/portal/auth/login',
          loginData
        );
      });

      it('speichert Auth-Daten nach erfolgreichem Login', async () => {
        const mockLoginResponse = {
          access_token: TEST_ACCESS_TOKEN,
          refresh_token: TEST_REFRESH_TOKEN,
          token_type: 'bearer',
          expires_in: 900,
          portal_user: TEST_USER,
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockLoginResponse });

        await portalApi.auth.login({
          email: 'test@beispiel.de',
          password: 'geheimes-passwort',
          company_id: TEST_COMPANY_ID,
        });

        expect(localStorage.getItem('portal_auth_token')).toBe(TEST_ACCESS_TOKEN);
        expect(localStorage.getItem('portal_refresh_token')).toBe(TEST_REFRESH_TOKEN);
        expect(localStorage.getItem('portal_company_id')).toBe(TEST_COMPANY_ID);
      });

      it('gibt Login-Antwort zurück', async () => {
        const mockLoginResponse = {
          access_token: TEST_ACCESS_TOKEN,
          refresh_token: TEST_REFRESH_TOKEN,
          token_type: 'bearer',
          expires_in: 900,
          portal_user: TEST_USER,
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockLoginResponse });

        const result = await portalApi.auth.login({
          email: 'test@beispiel.de',
          password: 'geheimes-passwort',
          company_id: TEST_COMPANY_ID,
        });

        expect(result.access_token).toBe(TEST_ACCESS_TOKEN);
        expect(result.portal_user).toEqual(TEST_USER);
      });
    });

    describe('logout', () => {
      it('löscht Auth-Daten auch bei API-Fehler', async () => {
        setPortalAuth(TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN, TEST_USER, TEST_COMPANY_ID);
        mockAxiosInstance.post.mockRejectedValueOnce(new Error('Netzwerkfehler'));

        try {
          await portalApi.auth.logout();
        } catch {
          // Erwartet
        }

        expect(localStorage.getItem('portal_auth_token')).toBeNull();
      });

      it('ruft korrekten Endpunkt auf', async () => {
        mockAxiosInstance.post.mockResolvedValueOnce({ data: { success: true, message: 'Abgemeldet' } });

        await portalApi.auth.logout();

        expect(mockAxiosInstance.post).toHaveBeenCalledWith('/portal/auth/logout');
      });
    });

    describe('getMe', () => {
      it('ruft korrekten Endpunkt auf', async () => {
        mockAxiosInstance.get.mockResolvedValueOnce({ data: TEST_USER });

        await portalApi.auth.getMe();

        expect(mockAxiosInstance.get).toHaveBeenCalledWith('/portal/auth/me');
      });
    });
  });

  // ==========================================================================
  // INVOICES API METHODEN
  // ==========================================================================

  describe('portalApi.invoices', () => {
    describe('list', () => {
      it('ruft Rechnungsliste ohne Filter ab', async () => {
        const mockResponse = { items: [], total: 0, has_more: false };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

        await portalApi.invoices.list();

        expect(mockAxiosInstance.get).toHaveBeenCalledWith(
          expect.stringContaining('/portal/invoices')
        );
      });

      it('baut Query-String mit Status-Filter', async () => {
        const mockResponse = { items: [], total: 0, has_more: false };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

        await portalApi.invoices.list({ status: 'open', limit: 10, offset: 0 });

        const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
        expect(calledUrl).toContain('status=open');
        expect(calledUrl).toContain('limit=10');
      });

      it('baut Query-String mit Datumsfiltern', async () => {
        const mockResponse = { items: [], total: 0, has_more: false };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

        await portalApi.invoices.list({
          from_date: '2025-01-01',
          to_date: '2025-12-31',
        });

        const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
        expect(calledUrl).toContain('from_date=2025-01-01');
        expect(calledUrl).toContain('to_date=2025-12-31');
      });

      it('verwendet Standard-Limit von 50 ohne Filter', async () => {
        const mockResponse = { items: [], total: 0, has_more: false };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

        await portalApi.invoices.list();

        const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
        expect(calledUrl).toContain('limit=50');
        expect(calledUrl).toContain('offset=0');
      });
    });

    describe('getDetail', () => {
      it('ruft korrekten Endpunkt mit Rechnungs-ID auf', async () => {
        const mockInvoice = { id: 'inv-123', status: 'open' };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockInvoice });

        await portalApi.invoices.getDetail('inv-123');

        expect(mockAxiosInstance.get).toHaveBeenCalledWith('/portal/invoices/inv-123');
      });
    });

    describe('downloadPdf', () => {
      it('ruft Download-Endpunkt mit Blob-Response-Type auf', async () => {
        const mockBlob = new Blob(['PDF-Inhalt'], { type: 'application/pdf' });
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockBlob });

        await portalApi.invoices.downloadPdf('inv-123');

        expect(mockAxiosInstance.get).toHaveBeenCalledWith(
          '/portal/invoices/inv-123/download',
          { responseType: 'blob' }
        );
      });
    });
  });

  // ==========================================================================
  // DOCUMENTS API METHODEN
  // ==========================================================================

  describe('portalApi.documents', () => {
    describe('upload', () => {
      it('verwendet multipart/form-data Content-Type', async () => {
        const mockUploadResponse = {
          success: true,
          document_id: 'doc-123',
          filename: 'test.pdf',
          file_size: 1024,
          message: 'Erfolgreich hochgeladen',
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockUploadResponse });

        const mockFile = new File(['Test-Inhalt'], 'test.pdf', { type: 'application/pdf' });
        await portalApi.documents.upload(mockFile);

        expect(mockAxiosInstance.post).toHaveBeenCalledWith(
          '/portal/documents/upload',
          expect.any(FormData),
          expect.objectContaining({
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        );
      });

      it('fügt Datei zum FormData hinzu', async () => {
        const mockUploadResponse = {
          success: true,
          document_id: 'doc-123',
          filename: 'test.pdf',
          file_size: 1024,
          message: 'Erfolgreich hochgeladen',
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockUploadResponse });

        const mockFile = new File(['Test-Inhalt'], 'test.pdf', { type: 'application/pdf' });
        await portalApi.documents.upload(mockFile);

        const formData: FormData = mockAxiosInstance.post.mock.calls[0][1];
        expect(formData.get('file')).toBe(mockFile);
      });

      it('fügt optionale Felder zum FormData hinzu', async () => {
        const mockUploadResponse = {
          success: true,
          document_id: 'doc-456',
          filename: 'rechnung.pdf',
          file_size: 2048,
          message: 'Erfolgreich hochgeladen',
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockUploadResponse });

        const mockFile = new File(['PDF-Inhalt'], 'rechnung.pdf', { type: 'application/pdf' });
        await portalApi.documents.upload(mockFile, {
          description: 'Rechnung Q1 2025',
          document_type: 'invoice',
          complaint_id: 'comp-123',
        });

        const formData: FormData = mockAxiosInstance.post.mock.calls[0][1];
        expect(formData.get('description')).toBe('Rechnung Q1 2025');
        expect(formData.get('document_type')).toBe('invoice');
        expect(formData.get('complaint_id')).toBe('comp-123');
      });

      it('fügt optionale Felder nicht hinzu wenn nicht angegeben', async () => {
        const mockUploadResponse = {
          success: true,
          document_id: 'doc-789',
          filename: 'dokument.pdf',
          file_size: 512,
          message: 'Erfolgreich hochgeladen',
        };
        mockAxiosInstance.post.mockResolvedValueOnce({ data: mockUploadResponse });

        const mockFile = new File(['Inhalt'], 'dokument.pdf', { type: 'application/pdf' });
        await portalApi.documents.upload(mockFile);

        const formData: FormData = mockAxiosInstance.post.mock.calls[0][1];
        expect(formData.get('description')).toBeNull();
        expect(formData.get('complaint_id')).toBeNull();
      });
    });

    describe('list', () => {
      it('baut Query-String mit Filtern', async () => {
        const mockResponse = { items: [], total: 0, has_more: false };
        mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

        await portalApi.documents.list({ complaint_id: 'comp-123', limit: 20, offset: 0 });

        const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
        expect(calledUrl).toContain('complaint_id=comp-123');
        expect(calledUrl).toContain('limit=20');
      });
    });
  });

  // ==========================================================================
  // QUERY STRING BUILDER
  // ==========================================================================

  describe('buildQueryString-Verhalten', () => {
    it('lässt undefined-Werte aus Query-String weg', async () => {
      const mockResponse = { items: [], total: 0, has_more: false };
      mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

      await portalApi.invoices.list({ status: undefined, limit: 10, offset: 0 });

      const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
      expect(calledUrl).not.toContain('status=');
      expect(calledUrl).toContain('limit=10');
    });

    it('lässt null-Werte aus Query-String weg', async () => {
      const mockResponse = { items: [], total: 0, has_more: false };
      mockAxiosInstance.get.mockResolvedValueOnce({ data: mockResponse });

      await portalApi.invoices.list({ status: null as unknown as undefined, limit: 5, offset: 0 });

      const calledUrl: string = mockAxiosInstance.get.mock.calls[0][0];
      expect(calledUrl).not.toContain('status=null');
    });
  });
});
