/**
 * InvoiceStatusChart Unit Tests
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { InvoiceStatusChart } from '../components/InvoiceStatusChart';
import type { InvoiceStatisticsResponse } from '../types/invoice-types';

describe('InvoiceStatusChart', () => {
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

  it('zeigt Ladezustand mit Skeleton', () => {
    render(<InvoiceStatusChart isLoading={true} />);

    expect(screen.getByText('Status-Verteilung')).toBeInTheDocument();
    // Skeleton should be visible
    const card = document.querySelector('.animate-pulse');
    expect(card).toBeInTheDocument();
  });

  it('zeigt "Keine Daten verfügbar" wenn keine Statistiken', () => {
    render(<InvoiceStatusChart statistics={undefined} isLoading={false} />);

    expect(screen.getByText('Keine Daten verfügbar')).toBeInTheDocument();
  });

  it('zeigt "Keine Daten verfügbar" bei leerer Distribution', () => {
    const emptyStats: InvoiceStatisticsResponse = {
      ...mockStatistics,
      statusDistribution: {},
    };
    render(<InvoiceStatusChart statistics={emptyStats} isLoading={false} />);

    expect(screen.getByText('Keine Daten verfügbar')).toBeInTheDocument();
  });

  it('zeigt Titel "Status-Verteilung"', () => {
    render(<InvoiceStatusChart statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('Status-Verteilung')).toBeInTheDocument();
  });

  it('zeigt alle Status mit Count und Prozent', () => {
    render(<InvoiceStatusChart statistics={mockStatistics} isLoading={false} />);

    // Open: 10 of 25 = 40%
    expect(screen.getByText('Offen')).toBeInTheDocument();
    expect(screen.getByText('10 (40%)')).toBeInTheDocument();

    // Paid: 12 of 25 = 48%
    expect(screen.getByText('Bezahlt')).toBeInTheDocument();
    expect(screen.getByText('12 (48%)')).toBeInTheDocument();

    // Dunning: 3 of 25 = 12%
    expect(screen.getByText('In Mahnung')).toBeInTheDocument();
    expect(screen.getByText('3 (12%)')).toBeInTheDocument();
  });

  it('zeigt Gesamtzahl der Rechnungen', () => {
    render(<InvoiceStatusChart statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('Gesamt')).toBeInTheDocument();
    expect(screen.getByText('25 Rechnungen')).toBeInTheDocument();
  });

  it('sortiert Status nach Anzahl absteigend', () => {
    render(<InvoiceStatusChart statistics={mockStatistics} isLoading={false} />);

    const statusElements = screen.getAllByText(/^\d+ \(\d+%\)$/);

    // Paid (12) should be first, then Open (10), then Dunning (3)
    expect(statusElements[0]).toHaveTextContent('12 (48%)');
    expect(statusElements[1]).toHaveTextContent('10 (40%)');
    expect(statusElements[2]).toHaveTextContent('3 (12%)');
  });

  it('zeigt Status mit 0 Count nicht an', () => {
    const statsWithZero: InvoiceStatisticsResponse = {
      ...mockStatistics,
      statusDistribution: {
        open: { count: 10, amount: 20000 },
        paid: { count: 0, amount: 0 },
        dunning: { count: 3, amount: 5000 },
      },
    };
    render(<InvoiceStatusChart statistics={statsWithZero} isLoading={false} />);

    // Paid should not be shown since count is 0
    expect(screen.queryByText('0 (0%)')).not.toBeInTheDocument();
  });

  it('rendert Fortschrittsbalken für jeden Status', () => {
    const { container } = render(
      <InvoiceStatusChart statistics={mockStatistics} isLoading={false} />
    );

    // Should have progress bars (bg-muted rounded-full)
    const progressBars = container.querySelectorAll('.bg-muted.rounded-full');
    expect(progressBars.length).toBeGreaterThan(0);
  });
});
