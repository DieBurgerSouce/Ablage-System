/**
 * InvoiceStatsCards Unit Tests
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { InvoiceStatsCards } from '../components/InvoiceStatsCards';
import type { InvoiceStatisticsResponse } from '../types/invoice-types';

describe('InvoiceStatsCards', () => {
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

  it('zeigt Ladezustand mit Skeletons', () => {
    render(<InvoiceStatsCards statistics={undefined} isLoading={true} />);

    // Should render 4 skeleton cards
    const cards = document.querySelectorAll('.animate-pulse');
    expect(cards.length).toBeGreaterThan(0);
  });

  it('zeigt nichts wenn keine Statistiken und nicht ladend', () => {
    const { container } = render(<InvoiceStatsCards statistics={undefined} isLoading={false} />);

    expect(container.firstChild).toBeNull();
  });

  it('zeigt offene Forderungen korrekt', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    // open (20000) + dunning (5000) = 25000
    expect(screen.getByText('Offene Forderungen')).toBeInTheDocument();
    expect(screen.getByText('25.000 €')).toBeInTheDocument();
  });

  it('zeigt überfällige Forderungen korrekt', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('Überfällige Forderungen')).toBeInTheDocument();
    expect(screen.getByText('8.000 €')).toBeInTheDocument();
  });

  it('zeigt aktive Mahnungen korrekt', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('Aktive Mahnungen')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('zeigt Gesamtanzahl der Rechnungen', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('25 Rechnungen gesamt')).toBeInTheDocument();
  });

  it('zeigt Anzahl überfälliger Rechnungen', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    expect(screen.getByText('5 überfällig')).toBeInTheDocument();
  });

  it('hebt überfällige Werte rot hervor wenn > 0', () => {
    const { container } = render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    // Should have red text for overdue amount
    const redText = container.querySelector('.text-red-600');
    expect(redText).toBeInTheDocument();
  });

  it('hebt Mahnungen orange hervor wenn > 0', () => {
    const { container } = render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    // Should have orange text for active dunnings
    const orangeText = container.querySelector('.text-orange-600');
    expect(orangeText).toBeInTheDocument();
  });

  it('zeigt keine Farbhervorhebung bei 0 Mahnungen', () => {
    const statsWithNoDunnings: InvoiceStatisticsResponse = {
      ...mockStatistics,
      statusDistribution: {
        ...mockStatistics.statusDistribution,
        dunning: { count: 0, amount: 0 },
      },
    };

    const { container } = render(<InvoiceStatsCards statistics={statsWithNoDunnings} isLoading={false} />);

    // Active dunnings value should not be orange
    const dunningCard = screen.getByText('Aktive Mahnungen').closest('.grid > div');
    const dunningValue = dunningCard?.querySelector('.text-orange-600');
    expect(dunningValue).toBeNull();
  });

  it('rendert 4 KPI-Cards', () => {
    render(<InvoiceStatsCards statistics={mockStatistics} isLoading={false} />);

    // Should have 4 cards in grid
    expect(screen.getByText('Offene Forderungen')).toBeInTheDocument();
    expect(screen.getByText('Überfällige Forderungen')).toBeInTheDocument();
    expect(screen.getByText('Ø Zahlungsziel')).toBeInTheDocument();
    expect(screen.getByText('Aktive Mahnungen')).toBeInTheDocument();
  });
});
