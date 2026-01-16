/**
 * InvoiceListPage Integration Tests
 *
 * Tests für die vollständige Rechnungsliste (Route: /admin/rechnungen/liste)
 * Die InvoiceListPage zeigt:
 * - Stats Cards
 * - Filter Bar
 * - Invoice Table mit Pagination
 * - Detail Sheet
 *
 * Note: Übersichts-Features (Chart, Quick Actions) sind in InvoiceOverviewPage.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InvoiceListPage } from '../components/InvoiceListPage';
import * as invoiceQueries from '../hooks/use-invoice-queries';
import type { InvoiceTrackingResponse, InvoiceStatisticsResponse } from '../types/invoice-types';

// Mock the hooks
vi.mock('../hooks/use-invoice-queries', () => ({
  useInvoicePage: vi.fn(),
  useMarkInvoicePaid: vi.fn(),
  useIncreaseDunning: vi.fn(),
}));

// Mock useToast
vi.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockInvoices: InvoiceTrackingResponse[] = [
  {
    id: 'inv-1',
    documentId: 'doc-1',
    invoiceNumber: 'RE-2025-001',
    invoiceDate: '2025-01-01T00:00:00Z',
    dueDate: '2025-01-15T00:00:00Z',
    amount: 1500.0,
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
  },
  {
    id: 'inv-2',
    documentId: 'doc-2',
    invoiceNumber: 'RE-2025-002',
    invoiceDate: '2025-01-02T00:00:00Z',
    dueDate: '2025-01-16T00:00:00Z',
    amount: 2500.0,
    currency: 'EUR',
    status: 'paid',
    dunningLevel: 0,
    paidAt: '2025-01-10T00:00:00Z',
    paidAmount: 2500.0,
    lastDunningAt: null,
    notes: null,
    createdAt: '2025-01-02T00:00:00Z',
    updatedAt: '2025-01-10T00:00:00Z',
    isOverdue: false,
    daysOverdue: 0,
  },
];

const mockStatistics: InvoiceStatisticsResponse = {
  totalInvoices: 25,
  totalAmount: 50000,
  statusDistribution: {
    open: { count: 10, amount: 20000 },
    paid: { count: 12, amount: 25000 },
    dunning: { count: 3, amount: 5000 },
  },
  overdueInvoices: { count: 5, amount: 8000 },
  generatedAt: '2025-01-20T00:00:00Z',
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  );
}

describe('InvoiceListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default mock implementations
    vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
      invoices: mockInvoices,
      statistics: mockStatistics,
      isLoading: false,
      isLoadingInvoices: false,
      isLoadingStatistics: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    vi.mocked(invoiceQueries.useMarkInvoicePaid).mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
    } as ReturnType<typeof invoiceQueries.useMarkInvoicePaid>);

    vi.mocked(invoiceQueries.useIncreaseDunning).mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
    } as ReturnType<typeof invoiceQueries.useIncreaseDunning>);
  });

  // Note: Seitentitel und Beschreibung werden im Layout (admin.rechnungen.tsx) gerendert,
  // nicht in der InvoiceListPage selbst - daher keine Tests dafür hier.

  describe('Grundlegendes Rendering', () => {
    it('zeigt Aktualisieren-Button', () => {
      renderWithProviders(<InvoiceListPage />);

      expect(screen.getByText('Aktualisieren')).toBeInTheDocument();
    });

    it('zeigt Stats Cards', () => {
      renderWithProviders(<InvoiceListPage />);

      expect(screen.getByText('Offene Forderungen')).toBeInTheDocument();
    });

    it('zeigt Rechnungstabelle', () => {
      renderWithProviders(<InvoiceListPage />);

      // Table should show invoice numbers
      expect(screen.getByText('RE-2025-001')).toBeInTheDocument();
      expect(screen.getByText('RE-2025-002')).toBeInTheDocument();
    });

    it('zeigt Pagination', () => {
      renderWithProviders(<InvoiceListPage />);

      expect(screen.getByText('Pro Seite:')).toBeInTheDocument();
      expect(screen.getByLabelText('Erste Seite')).toBeInTheDocument();
    });

    it('zeigt InvoiceFilterBar', async () => {
      renderWithProviders(<InvoiceListPage />);

      // FilterBar shows Status label
      await waitFor(() => {
        expect(screen.getByLabelText(/status/i)).toBeInTheDocument();
      });
    });
  });

  describe('Aktualisieren-Button', () => {
    it('ruft refetch bei Klick auf', () => {
      const refetch = vi.fn();
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: mockInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch,
      });

      renderWithProviders(<InvoiceListPage />);

      fireEvent.click(screen.getByText('Aktualisieren'));

      expect(refetch).toHaveBeenCalled();
    });

    it('ist deaktiviert während Fetching', () => {
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: mockInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceListPage />);

      expect(screen.getByText('Aktualisieren').closest('button')).toBeDisabled();
    });

    it('zeigt Spinner-Animation während Fetching', () => {
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: mockInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceListPage />);

      const button = screen.getByText('Aktualisieren').closest('button');
      const icon = button?.querySelector('svg');
      expect(icon).toHaveClass('animate-spin');
    });
  });

  describe('Fehlerbehandlung', () => {
    it('zeigt Fehlermeldung bei Error', () => {
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: [],
        statistics: undefined,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: true,
        error: new Error('Laden fehlgeschlagen'),
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceListPage />);

      expect(screen.getByText('Fehler beim Laden')).toBeInTheDocument();
      expect(screen.getByText('Die Rechnungsdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.')).toBeInTheDocument();
      expect(screen.getByText('Erneut versuchen')).toBeInTheDocument();
    });

    it('ruft refetch bei Erneut versuchen auf', () => {
      const refetch = vi.fn();
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: [],
        statistics: undefined,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: true,
        error: new Error('Laden fehlgeschlagen'),
        refetch,
      });

      renderWithProviders(<InvoiceListPage />);

      fireEvent.click(screen.getByText('Erneut versuchen'));

      expect(refetch).toHaveBeenCalled();
    });
  });

  // Note: Confirmation Dialog Tests werden in E2E-Tests getestet, da sie
  // komplexe Interaktionen mit Dropdown-Menüs und Dialogen erfordern.
  // Die einzelnen Komponenten (InvoiceActions, AlertDialog) haben eigene Unit-Tests.

  describe('Leere Zustände', () => {
    it('zeigt leere Tabelle bei keinen Rechnungen', () => {
      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: [],
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceListPage />);

      // Stats Cards should still be visible
      expect(screen.getByText('Offene Forderungen')).toBeInTheDocument();

      // Table should show empty state or no rows
      expect(screen.queryByText('RE-2025-001')).not.toBeInTheDocument();
    });
  });
});
