/**
 * B9-Regression: Kategorie-Dokumentliste - Pagination-Vertrag
 *
 * ECHTER Backend-Vertrag (app/api/v1/documents.py::get_category_documents):
 *   GET /documents/category?...&page=N  mit  page: int = Query(1, ge=1)
 *   -> 1-BASIERT. page=0 liefert 422 Unprocessable Entity.
 *
 * Vorher sendete das Frontend page=0 (DEFAULT_CATEGORY_FILTER.page = 0)
 * -> JEDER Aufruf der Kategorie-Dokumentliste (kunden/lieferanten
 * $folderId/$category) schlug mit 422 fehl.
 *
 * Hinweis (Befund): GET /finance/years/.../documents ist dagegen
 * 0-basiert (page Query(0, ge=0)) - die beiden Kategorie-Endpoints sind
 * im Backend inkonsistent; finance.ts bleibt deshalb 0-basiert.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '@/lib/api/client';
import { ablageService } from '@/lib/api/services/ablage';
import { DEFAULT_CATEGORY_FILTER } from '../types';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}));

const mockedGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

const emptyBackendResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  filters_applied: {}
};

const baseFilter = {
  businessEntityId: 'c0ffee00-0000-4000-8000-000000000001',
  folderId: 'messer',
  category: 'rechnungen',
  entityType: 'customer' as const
};

beforeEach(() => {
  vi.clearAllMocks();
  mockedGet.mockResolvedValue({ data: emptyBackendResponse });
});

describe('Kategorie-Pagination ist 1-basiert (B9)', () => {
  it('DEFAULT_CATEGORY_FILTER startet auf Seite 1', () => {
    expect(DEFAULT_CATEGORY_FILTER.page).toBe(1);
  });

  it('sendet page=1 wenn keine Seite gesetzt ist', async () => {
    await ablageService.getCategoryDocuments(baseFilter);

    const [url, config] = mockedGet.mock.calls[0];
    expect(url).toBe('/documents/category');
    expect(config.params.page).toBe(1);
  });

  it('klemmt page=0 defensiv auf 1 (verhindert 422)', async () => {
    await ablageService.getCategoryDocuments({ ...baseFilter, page: 0 });

    const [, config] = mockedGet.mock.calls[0];
    expect(config.params.page).toBe(1);
  });

  it('reicht gueltige Seiten unveraendert durch', async () => {
    await ablageService.getCategoryDocuments({ ...baseFilter, page: 3 });

    const [, config] = mockedGet.mock.calls[0];
    expect(config.params.page).toBe(3);
  });

  it('sendet das Ordner-Kuerzel und die uebrigen Pflichtparameter', async () => {
    await ablageService.getCategoryDocuments(baseFilter);

    const [, config] = mockedGet.mock.calls[0];
    expect(config.params.business_entity_id).toBe(baseFilter.businessEntityId);
    expect(config.params.folder_id).toBe('messer');
    expect(config.params.category).toBe('rechnungen');
    expect(config.params.entity_type).toBe('customer');
    expect(config.params.page_size).toBe(25);
  });
});
