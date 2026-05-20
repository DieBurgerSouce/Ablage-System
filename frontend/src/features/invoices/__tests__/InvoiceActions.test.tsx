/**
 * InvoiceActions Unit Tests
 *
 * Note: Radix UI DropdownMenu uses portals - tests focus on
 * trigger rendering and basic structure.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { InvoiceActions } from '../components/InvoiceActions';
import type { InvoiceTrackingResponse } from '../types/invoice-types';

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

describe('InvoiceActions', () => {
  it('rendert Aktionen-Button', () => {
    render(<InvoiceActions invoice={createMockInvoice()} />);

    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });

  it('hat korrektes Accessibility-Label', () => {
    render(<InvoiceActions invoice={createMockInvoice()} />);

    expect(screen.getByText('Aktionen öffnen')).toBeInTheDocument();
  });

  it('zeigt Dropdown-Menü bei Klick', async () => {
    const user = userEvent.setup();
    const onViewDetails = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice()}
        onViewDetails={onViewDetails}
      />
    );

    await user.click(screen.getByRole('button'));

    // Menu should be open (role="menu" appears)
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('zeigt "Details anzeigen" bei Klick', async () => {
    const user = userEvent.setup();
    const onViewDetails = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice()}
        onViewDetails={onViewDetails}
      />
    );

    await user.click(screen.getByRole('button'));

    // Menu content rendered in portal
    expect(screen.getByRole('menuitem', { name: /Details anzeigen/i })).toBeInTheDocument();
  });

  it('zeigt "Als bezahlt markieren" für offene Rechnungen', async () => {
    const user = userEvent.setup();
    const onMarkPaid = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'open' })}
        onMarkPaid={onMarkPaid}
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.getByRole('menuitem', { name: /Als bezahlt markieren/i })).toBeInTheDocument();
  });

  it('zeigt "Mahnstufe erhöhen" für Rechnungen unter Level 4', async () => {
    const user = userEvent.setup();
    const onIncreaseDunning = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 2 })}
        onIncreaseDunning={onIncreaseDunning}
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.getByRole('menuitem', { name: /Mahnstufe erhöhen/i })).toBeInTheDocument();
  });

  it('zeigt "Bereits bezahlt" für bezahlte Rechnungen', async () => {
    const user = userEvent.setup();
    const onMarkPaid = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'paid' })}
        onMarkPaid={onMarkPaid}
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.getByRole('menuitem', { name: /Bereits bezahlt/i })).toBeInTheDocument();
  });

  it('zeigt "Max. Mahnstufe erreicht" bei Level 4', async () => {
    const user = userEvent.setup();
    const onIncreaseDunning = vi.fn();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 4 })}
        onIncreaseDunning={onIncreaseDunning}
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.getByRole('menuitem', { name: /Max. Mahnstufe erreicht/i })).toBeInTheDocument();
  });

  it('zeigt "Storniert" für stornierte Rechnungen', async () => {
    const user = userEvent.setup();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'cancelled' })}
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.getByRole('menuitem', { name: /Storniert/i })).toBeInTheDocument();
  });

  it('ruft onMarkPaid Callback auf bei Klick', async () => {
    const user = userEvent.setup();
    const onMarkPaid = vi.fn();
    const invoice = createMockInvoice();
    render(<InvoiceActions invoice={invoice} onMarkPaid={onMarkPaid} />);

    await user.click(screen.getByRole('button'));
    await user.click(screen.getByRole('menuitem', { name: /Als bezahlt markieren/i }));

    expect(onMarkPaid).toHaveBeenCalledWith(invoice);
  });

  it('ruft onIncreaseDunning Callback auf bei Klick', async () => {
    const user = userEvent.setup();
    const onIncreaseDunning = vi.fn();
    const invoice = createMockInvoice({ status: 'dunning', dunningLevel: 1 });
    render(<InvoiceActions invoice={invoice} onIncreaseDunning={onIncreaseDunning} />);

    await user.click(screen.getByRole('button'));
    await user.click(screen.getByRole('menuitem', { name: /Mahnstufe erhöhen/i }));

    expect(onIncreaseDunning).toHaveBeenCalledWith(invoice);
  });

  it('ruft onViewDetails Callback auf bei Klick', async () => {
    const user = userEvent.setup();
    const onViewDetails = vi.fn();
    const invoice = createMockInvoice();
    render(<InvoiceActions invoice={invoice} onViewDetails={onViewDetails} />);

    await user.click(screen.getByRole('button'));
    await user.click(screen.getByRole('menuitem', { name: /Details anzeigen/i }));

    expect(onViewDetails).toHaveBeenCalledWith(invoice);
  });

  it('versteckt "Als bezahlt markieren" wenn onMarkPaid nicht übergeben', async () => {
    const user = userEvent.setup();
    render(
      <InvoiceActions
        invoice={createMockInvoice({ status: 'open' })}
        // No onMarkPaid callback
      />
    );

    await user.click(screen.getByRole('button'));

    expect(screen.queryByRole('menuitem', { name: /Als bezahlt markieren/i })).not.toBeInTheDocument();
  });
});
