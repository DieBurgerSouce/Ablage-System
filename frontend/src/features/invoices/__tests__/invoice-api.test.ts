/**
 * Invoice API Service Unit Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { invoiceService, InvoiceApiError, computeKPIs } from '../api/invoice-api';
import { apiClient } from '@/lib/api/client';
import type { InvoiceStatisticsResponse } from '../types/invoice-types';

// Mock the API client
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('invoiceService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listInvoices', () => {
    it('transformiert Backend-Response korrekt', async () => {
      const mockBackendResponse = [
        {
          id: 'inv-1',
          document_id: 'doc-1',
          invoice_number: 'RE-001',
          invoice_date: '2025-01-01',
          due_date: '2025-01-15',
          amount: 1500,
          currency: 'EUR',
          status: 'open',
          dunning_level: 0,
          paid_at: null,
          paid_amount: null,
          last_dunning_at: null,
          notes: null,
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          is_overdue: false,
          days_overdue: 0,
        },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockBackendResponse });

      const result = await invoiceService.listInvoices();

      expect(result[0]).toEqual({
        id: 'inv-1',
        documentId: 'doc-1',
        invoiceNumber: 'RE-001',
        invoiceDate: '2025-01-01',
        dueDate: '2025-01-15',
        amount: 1500,
        currency: 'EUR',
        status: 'open',
        dunningLevel: 0,
        paidAt: null,
        paidAmount: null,
        lastDunningAt: null,
        notes: null,
        createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
        isOverdue: false,
        daysOverdue: 0,
      });
    });

    it('sendet korrekte Query-Parameter', async () => {
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [] });

      await invoiceService.listInvoices({
        page: 2,
        perPage: 50,
        status: 'paid',
        overdueOnly: true,
      });

      expect(apiClient.get).toHaveBeenCalledWith('/invoices', {
        params: {
          page: 2,
          per_page: 50,
          status: 'paid',
          overdue_only: true,
        },
      });
    });

    it('gibt leeres Array bei 404 zurück', async () => {
      // Create a proper AxiosError instance
      const axiosError = new AxiosError(
        'Not Found',
        'ERR_BAD_REQUEST',
        undefined,
        undefined,
        {
          status: 404,
          statusText: 'Not Found',
          headers: {},
          config: { headers: new AxiosHeaders() },
          data: null,
        }
      );

      vi.mocked(apiClient.get).mockRejectedValueOnce(axiosError);

      const result = await invoiceService.listInvoices();

      expect(result).toEqual([]);
    });
  });

  describe('markPaid', () => {
    it('sendet korrekte Request-Parameter', async () => {
      const mockResponse = {
        id: 'inv-1',
        document_id: 'doc-1',
        invoice_number: 'RE-001',
        invoice_date: null,
        due_date: null,
        amount: 1500,
        currency: 'EUR',
        status: 'paid',
        dunning_level: 0,
        paid_at: '2025-01-20T00:00:00Z',
        paid_amount: 1500,
        last_dunning_at: null,
        notes: null,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-20T00:00:00Z',
      };

      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockResponse });

      await invoiceService.markPaid('inv-1', {
        paidAmount: 1500,
        paidAt: '2025-01-20T00:00:00Z',
      });

      expect(apiClient.post).toHaveBeenCalledWith(
        '/invoices/inv-1/mark-paid',
        null,
        {
          params: {
            paid_amount: 1500,
            paid_at: '2025-01-20T00:00:00Z',
          },
        }
      );
    });
  });

  describe('increaseDunning', () => {
    it('ruft korrekten Endpoint auf', async () => {
      const mockResponse = {
        id: 'inv-1',
        document_id: 'doc-1',
        invoice_number: 'RE-001',
        invoice_date: null,
        due_date: null,
        amount: 1500,
        currency: 'EUR',
        status: 'dunning',
        dunning_level: 1,
        paid_at: null,
        paid_amount: null,
        last_dunning_at: '2025-01-20T00:00:00Z',
        notes: null,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-20T00:00:00Z',
      };

      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockResponse });

      const result = await invoiceService.increaseDunning('inv-1');

      expect(apiClient.post).toHaveBeenCalledWith('/invoices/inv-1/increase-dunning');
      expect(result.dunningLevel).toBe(1);
    });
  });
});

describe('InvoiceApiError', () => {
  it('enthält statusCode', () => {
    const error = new InvoiceApiError('Test Fehler', 404);

    expect(error.message).toBe('Test Fehler');
    expect(error.statusCode).toBe(404);
    expect(error.name).toBe('InvoiceApiError');
  });

  it('enthält originalError', () => {
    const originalError = new Error('Original');
    const error = new InvoiceApiError('Wrapped', 500, originalError);

    expect(error.originalError).toBe(originalError);
  });
});

describe('computeKPIs', () => {
  const mockStatistics: InvoiceStatisticsResponse = {
    totalInvoices: 10,
    totalAmount: 15000,
    statusDistribution: {
      open: { count: 3, amount: 5000 },
      paid: { count: 4, amount: 6000 },
      dunning: { count: 2, amount: 3000 },
      cancelled: { count: 1, amount: 1000 },
    },
    overdueInvoices: { count: 3, amount: 4000 },
    generatedAt: '2025-01-20T00:00:00Z',
  };

  it('berechnet offene Forderungen korrekt (ohne paid & cancelled)', () => {
    const kpis = computeKPIs(mockStatistics);

    // open (5000) + dunning (3000) = 8000
    expect(kpis.openAmount).toBe(8000);
  });

  it('berechnet überfällige Forderungen korrekt', () => {
    const kpis = computeKPIs(mockStatistics);

    expect(kpis.overdueAmount).toBe(4000);
  });

  it('berechnet aktive Mahnungen korrekt', () => {
    const kpis = computeKPIs(mockStatistics);

    expect(kpis.activeDunnings).toBe(2);
  });

  it('berechnet bezahlte Beträge korrekt', () => {
    const kpis = computeKPIs(mockStatistics);

    expect(kpis.paidAmount).toBe(6000);
  });

  it('behandelt leere statusDistribution korrekt', () => {
    const emptyStats: InvoiceStatisticsResponse = {
      totalInvoices: 0,
      totalAmount: 0,
      statusDistribution: {},
      overdueInvoices: { count: 0, amount: 0 },
      generatedAt: '2025-01-20T00:00:00Z',
    };

    const kpis = computeKPIs(emptyStats);

    expect(kpis.openAmount).toBe(0);
    expect(kpis.paidAmount).toBe(0);
    expect(kpis.activeDunnings).toBe(0);
  });
});
