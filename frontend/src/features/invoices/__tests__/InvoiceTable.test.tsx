/**
 * InvoiceTable Unit Tests
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { InvoiceTable } from '../components/InvoiceTable';
import type { InvoiceTrackingResponse } from '../types/invoice-types';

// Mock-Daten für Tests
const createMockInvoice = (overrides: Partial<InvoiceTrackingResponse> = {}): InvoiceTrackingResponse => ({
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
  ...overrides,
});

describe('InvoiceTable', () => {
  const mockInvoices: InvoiceTrackingResponse[] = [
    createMockInvoice({ id: 'inv-1', invoiceNumber: 'RE-2025-001', status: 'open' }),
    createMockInvoice({ id: 'inv-2', invoiceNumber: 'RE-2025-002', status: 'paid' }),
    createMockInvoice({
      id: 'inv-3',
      invoiceNumber: 'RE-2025-003',
      status: 'dunning',
      dunningLevel: 2,
      isOverdue: true,
      daysOverdue: 15,
    }),
  ];

  it('rendert alle Rechnungen', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    expect(screen.getByText('RE-2025-001')).toBeInTheDocument();
    expect(screen.getByText('RE-2025-002')).toBeInTheDocument();
    expect(screen.getByText('RE-2025-003')).toBeInTheDocument();
  });

  it('zeigt Ladezustand korrekt an', () => {
    render(<InvoiceTable invoices={[]} isLoading={true} />);

    // Should show skeleton loaders (5 rows)
    const rows = screen.getAllByRole('row');
    // Header + 5 skeleton rows
    expect(rows.length).toBeGreaterThanOrEqual(5);
  });

  it('zeigt leeren Zustand wenn keine Daten vorhanden', () => {
    render(<InvoiceTable invoices={[]} isLoading={false} />);

    expect(screen.getByText('Keine Rechnungen gefunden')).toBeInTheDocument();
  });

  it('ruft onRowClick beim Klick auf eine Zeile auf', () => {
    const onRowClick = vi.fn();
    render(<InvoiceTable invoices={mockInvoices} onRowClick={onRowClick} />);

    fireEvent.click(screen.getByText('RE-2025-001'));
    expect(onRowClick).toHaveBeenCalledWith(
      expect.objectContaining({
        invoiceNumber: 'RE-2025-001',
      })
    );
  });

  it('zeigt Status-Badges korrekt an', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    expect(screen.getByText('Offen')).toBeInTheDocument();
    expect(screen.getByText('Bezahlt')).toBeInTheDocument();
    expect(screen.getByText('In Mahnung')).toBeInTheDocument();
  });

  it('zeigt Mahnstufe-Badges korrekt an', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    // Level 2 should show "1. Mahnung"
    expect(screen.getByText('1. Mahnung')).toBeInTheDocument();
  });

  it('zeigt überfällige Tage für überfällige Rechnungen', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    expect(screen.getByText('15 Tage')).toBeInTheDocument();
  });

  it('hebt überfällige Rechnungen visuell hervor', () => {
    const { container } = render(<InvoiceTable invoices={mockInvoices} />);

    // Should have a row with red background class (Tailwind opacity classes use escaped slashes in CSS)
    // Use attribute selector instead which is more reliable
    const rows = container.querySelectorAll('tr');
    const overdueRow = Array.from(rows).find((row) =>
      row.className.includes('bg-red-50')
    );
    expect(overdueRow).toBeTruthy();
  });

  it('formatiert Beträge korrekt in EUR', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    // 1500.00 EUR should be formatted
    expect(screen.getAllByText(/1\.500,00\s*€/)).toBeTruthy();
  });

  it('formatiert Datum im deutschen Format', () => {
    render(<InvoiceTable invoices={mockInvoices} />);

    // 2025-01-15 should be formatted as 15.01.2025
    // Multiple invoices share the same date, so use getAllByText
    const formattedDates = screen.getAllByText('15.01.2025');
    expect(formattedDates.length).toBeGreaterThan(0);
  });

  it('zeigt Aktionen-Dropdown für jede Zeile', () => {
    const onMarkPaid = vi.fn();
    render(<InvoiceTable invoices={mockInvoices} onMarkPaid={onMarkPaid} />);

    // Should have action buttons (MoreHorizontal icons)
    const actionButtons = screen.getAllByRole('button');
    expect(actionButtons.length).toBeGreaterThan(0);
  });

  it('stoppt Event-Propagation bei Aktionen-Klick', () => {
    const onRowClick = vi.fn();
    const onMarkPaid = vi.fn();
    render(
      <InvoiceTable invoices={mockInvoices} onRowClick={onRowClick} onMarkPaid={onMarkPaid} />
    );

    // Click on actions button should not trigger row click
    const actionButtons = screen.getAllByRole('button');
    fireEvent.click(actionButtons[0]);

    // Row click should not have been called
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
