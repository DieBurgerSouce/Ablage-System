/**
 * Document Graph API Tests
 *
 * Testet Transform-Funktionen und API-Aufrufe.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { documentGraphApi } from '../api/document-graph-api';

// Mock apiClient
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api/client';

const mockGet = vi.mocked(apiClient.get);

describe('documentGraphApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getChain', () => {
    it('transformiert Backend-Daten korrekt nach camelCase', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          chain_id: 'CHAIN-2026-00001',
          document_count: 3,
          chain_started_at: '2026-01-15T10:00:00Z',
          chain_updated_at: '2026-02-20T14:30:00Z',
          has_quote: true,
          has_order: true,
          has_delivery_note: false,
          has_invoice: true,
          has_credit_note: false,
          open_discrepancies: 1,
          is_complete: false,
          documents: [
            {
              id: 'doc-1',
              document_type: 'quote',
              chain_position: 1,
              filename: 'Angebot-001.pdf',
              document_date: '2026-01-15',
              amount: 1500.0,
              reference_numbers: { order_nr: 'A-001' },
              created_at: '2026-01-15T10:00:00Z',
            },
          ],
        },
      });

      const result = await documentGraphApi.getChain('CHAIN-2026-00001');

      expect(result.chainId).toBe('CHAIN-2026-00001');
      expect(result.documentCount).toBe(3);
      expect(result.hasQuote).toBe(true);
      expect(result.hasOrder).toBe(true);
      expect(result.hasDeliveryNote).toBe(false);
      expect(result.isComplete).toBe(false);
      expect(result.openDiscrepancies).toBe(1);
      expect(result.documents).toHaveLength(1);
      expect(result.documents[0].documentType).toBe('quote');
      expect(result.documents[0].chainPosition).toBe(1);
      expect(result.documents[0].amount).toBe(1500.0);

      expect(mockGet).toHaveBeenCalledWith('/document-chains/CHAIN-2026-00001');
    });
  });

  describe('getChainByDocument', () => {
    it('gibt chainId null zurueck wenn Dokument keiner Kette zugeordnet', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          document_id: 'doc-99',
          chain_id: null,
          message: 'Dokument ist keiner Auftragskette zugeordnet',
        },
      });

      const result = await documentGraphApi.getChainByDocument('doc-99');

      expect(result.chainId).toBeNull();
      expect(result.documentId).toBe('doc-99');
    });

    it('gibt Ketten-Info zurueck wenn zugeordnet', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          document_id: 'doc-1',
          chain_id: 'CHAIN-2026-00001',
          document_count: 3,
          is_complete: true,
          open_discrepancies: 0,
        },
      });

      const result = await documentGraphApi.getChainByDocument('doc-1');

      expect(result.chainId).toBe('CHAIN-2026-00001');
      expect(result.documentCount).toBe(3);
      expect(result.isComplete).toBe(true);
    });
  });

  describe('getChainsByEntity', () => {
    it('gibt leeres Array zurueck wenn keine Ketten', async () => {
      mockGet.mockResolvedValueOnce({
        data: { chains: [], total: 0 },
      });

      const result = await documentGraphApi.getChainsByEntity({
        entityId: 'entity-1',
      });

      expect(result.chains).toEqual([]);
      expect(result.total).toBe(0);
    });
  });
});
