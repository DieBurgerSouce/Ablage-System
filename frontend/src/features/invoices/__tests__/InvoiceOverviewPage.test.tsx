/**
 * InvoiceOverviewPage Integration Tests
 *
 * Tests für die Dashboard/Übersicht-Seite (Route: /admin/rechnungen)
 * Die InvoiceOverviewPage zeigt:
 * - Stats Cards (KPIs)
 * - Status Chart
 * - Quick Actions (Navigation zu gefilterten Listen)
 * - Recent Invoices Preview (max 5)
 *
 * Note: Vollständige Liste mit Filter/Pagination ist in InvoiceListPage.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InvoiceOverviewPage } from '../components/InvoiceOverviewPage';
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

// Mock TanStack Router
const mockNavigate = vi.fn();
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
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

describe('InvoiceOverviewPage', () => {
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

  describe('Grundlegendes Rendering', () => {
    it('zeigt Aktualisieren-Button', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Aktualisieren')).toBeInTheDocument();
    });

    it('zeigt Stats Cards', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Offene Forderungen')).toBeInTheDocument();
    });

    it('zeigt Status-Verteilung Chart', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Status-Verteilung')).toBeInTheDocument();
    });

    it('zeigt Schnellzugriff-Karte', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Schnellzugriff')).toBeInTheDocument();
    });

    it('zeigt Neueste Rechnungen', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Neueste Rechnungen')).toBeInTheDocument();
    });
  });

  describe('Quick Actions', () => {
    it('zeigt Überfällige Rechnungen Button', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Überfällige Rechnungen anzeigen')).toBeInTheDocument();
    });

    it('zeigt Rechnungen in Mahnung Button', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Rechnungen in Mahnung anzeigen')).toBeInTheDocument();
    });

    it('zeigt Anzahl überfälliger Rechnungen in Klammern', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      // Should show count from statistics: overdueInvoices.count = 5
      expect(screen.getByText('(5)')).toBeInTheDocument();
    });

    it('navigiert zu überfälligen Rechnungen bei Klick', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      fireEvent.click(screen.getByText('Überfällige Rechnungen anzeigen'));

      expect(mockNavigate).toHaveBeenCalledWith({
        to: '/admin/rechnungen/liste',
        search: { overdueOnly: 'true' },
      });
    });

    it('navigiert zu Mahnungs-Rechnungen bei Klick', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      fireEvent.click(screen.getByText('Rechnungen in Mahnung anzeigen'));

      expect(mockNavigate).toHaveBeenCalledWith({
        to: '/admin/rechnungen/liste',
        search: { status: 'dunning' },
      });
    });
  });

  describe('Neueste Rechnungen Preview', () => {
    it('zeigt maximal 5 Rechnungen', () => {
      // Create 10 invoices
      const manyInvoices = Array.from({ length: 10 }, (_, i) => ({
        ...mockInvoices[0],
        id: `inv-${i}`,
        invoiceNumber: `RE-2025-${String(i).padStart(3, '0')}`,
      }));

      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: manyInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceOverviewPage />);

      // Should only show first 5
      expect(screen.getByText('RE-2025-000')).toBeInTheDocument();
      expect(screen.getByText('RE-2025-004')).toBeInTheDocument();
      expect(screen.queryByText('RE-2025-005')).not.toBeInTheDocument();
    });

    it('zeigt "Alle anzeigen" Link wenn mehr als 5', () => {
      const manyInvoices = Array.from({ length: 10 }, (_, i) => ({
        ...mockInvoices[0],
        id: `inv-${i}`,
        invoiceNumber: `RE-2025-${String(i).padStart(3, '0')}`,
      }));

      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: manyInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Alle 10 Rechnungen anzeigen')).toBeInTheDocument();
    });

    it('versteckt "Alle anzeigen" Link bei 5 oder weniger', () => {
      renderWithProviders(<InvoiceOverviewPage />);

      // With 2 invoices, should not show the link
      expect(screen.queryByText(/Alle \d+ Rechnungen anzeigen/)).not.toBeInTheDocument();
    });

    it('navigiert zu Liste bei Klick auf "Alle anzeigen"', () => {
      const manyInvoices = Array.from({ length: 10 }, (_, i) => ({
        ...mockInvoices[0],
        id: `inv-${i}`,
        invoiceNumber: `RE-2025-${String(i).padStart(3, '0')}`,
      }));

      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: manyInvoices,
        statistics: mockStatistics,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceOverviewPage />);

      fireEvent.click(screen.getByText('Alle 10 Rechnungen anzeigen'));

      expect(mockNavigate).toHaveBeenCalledWith({ to: '/admin/rechnungen/liste' });
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

      renderWithProviders(<InvoiceOverviewPage />);

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

      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Aktualisieren').closest('button')).toBeDisabled();
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

      renderWithProviders(<InvoiceOverviewPage />);

      expect(screen.getByText('Fehler beim Laden')).toBeInTheDocument();
      expect(screen.getByText('Die Rechnungsdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.')).toBeInTheDocument();
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

      renderWithProviders(<InvoiceOverviewPage />);

      fireEvent.click(screen.getByText('Erneut versuchen'));

      expect(refetch).toHaveBeenCalled();
    });
  });

  // Note: Confirmation Dialog Tests werden in E2E-Tests getestet, da sie
  // komplexe Interaktionen mit Dropdown-Menüs und Dialogen erfordern.
  // Die einzelnen Komponenten (InvoiceActions, AlertDialog) haben eigene Unit-Tests.

  describe('Leere Zustände', () => {
    it('versteckt Überfällige-Count wenn keine überfälligen', () => {
      const statsNoOverdue = {
        ...mockStatistics,
        overdueInvoices: { count: 0, amount: 0 },
      };

      vi.mocked(invoiceQueries.useInvoicePage).mockReturnValue({
        invoices: mockInvoices,
        statistics: statsNoOverdue,
        isLoading: false,
        isLoadingInvoices: false,
        isLoadingStatistics: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      });

      renderWithProviders(<InvoiceOverviewPage />);

      // Should not show (0) next to button
      expect(screen.queryByText('(0)')).not.toBeInTheDocument();
    });
  });
});
