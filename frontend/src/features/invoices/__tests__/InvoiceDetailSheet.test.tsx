/**
 * InvoiceDetailSheet Unit Tests
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { InvoiceDetailSheet } from '../components/InvoiceDetailSheet';
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

describe('InvoiceDetailSheet', () => {
  it('rendert nichts ohne Invoice', () => {
    const { container } = render(
      <InvoiceDetailSheet
        invoice={null}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('zeigt Rechnungsnummer als Titel', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice()}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    // Multiple elements may contain invoice number - check heading specifically
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toHaveTextContent('RE-2025-001');
  });

  it('zeigt Fallback-Titel bei fehlender Rechnungsnummer', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ invoiceNumber: null })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Rechnungsverfolgung')).toBeInTheDocument();
  });

  it('zeigt Status-Badge', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'paid' })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Bezahlt')).toBeInTheDocument();
  });

  it('zeigt Mahnstufen-Badge', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 2 })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('1. Mahnung')).toBeInTheDocument();
  });

  it('zeigt Überfällig-Badge wenn isOverdue', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ isOverdue: true, daysOverdue: 5 })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('5 Tage überfällig')).toBeInTheDocument();
  });

  it('zeigt Betrag formatiert', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ amount: 1500.0 })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    // German currency format: 1.500,00 €
    expect(screen.getByText(/1\.500,00\s*€/)).toBeInTheDocument();
  });

  it('zeigt Notizen wenn vorhanden', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ notes: 'Wichtige Anmerkung' })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Notizen')).toBeInTheDocument();
    expect(screen.getByText('Wichtige Anmerkung')).toBeInTheDocument();
  });

  it('versteckt Notizen-Sektion wenn keine Notizen', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ notes: null })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.queryByText('Notizen')).not.toBeInTheDocument();
  });

  it('zeigt "Als bezahlt markieren" Button für offene Rechnungen', () => {
    const onMarkPaid = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'open' })}
        open={true}
        onOpenChange={vi.fn()}
        onMarkPaid={onMarkPaid}
      />
    );

    expect(screen.getByText('Als bezahlt markieren')).toBeInTheDocument();
  });

  it('versteckt "Als bezahlt markieren" für bezahlte Rechnungen', () => {
    const onMarkPaid = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'paid' })}
        open={true}
        onOpenChange={vi.fn()}
        onMarkPaid={onMarkPaid}
      />
    );

    expect(screen.queryByText('Als bezahlt markieren')).not.toBeInTheDocument();
  });

  it('versteckt "Als bezahlt markieren" für stornierte Rechnungen', () => {
    const onMarkPaid = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'cancelled' })}
        open={true}
        onOpenChange={vi.fn()}
        onMarkPaid={onMarkPaid}
      />
    );

    expect(screen.queryByText('Als bezahlt markieren')).not.toBeInTheDocument();
  });

  it('zeigt "Mahnstufe erhöhen" Button wenn Level < 4', () => {
    const onIncreaseDunning = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 2 })}
        open={true}
        onOpenChange={vi.fn()}
        onIncreaseDunning={onIncreaseDunning}
      />
    );

    expect(screen.getByText('Mahnstufe erhöhen')).toBeInTheDocument();
  });

  it('versteckt "Mahnstufe erhöhen" bei Level 4', () => {
    const onIncreaseDunning = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 4 })}
        open={true}
        onOpenChange={vi.fn()}
        onIncreaseDunning={onIncreaseDunning}
      />
    );

    expect(screen.queryByText('Mahnstufe erhöhen')).not.toBeInTheDocument();
  });

  it('ruft onMarkPaid Callback auf', () => {
    const onMarkPaid = vi.fn();
    const invoice = createMockInvoice();
    render(
      <InvoiceDetailSheet
        invoice={invoice}
        open={true}
        onOpenChange={vi.fn()}
        onMarkPaid={onMarkPaid}
      />
    );

    fireEvent.click(screen.getByText('Als bezahlt markieren'));

    expect(onMarkPaid).toHaveBeenCalledWith(invoice);
  });

  it('ruft onIncreaseDunning Callback auf', () => {
    const onIncreaseDunning = vi.fn();
    const invoice = createMockInvoice({ status: 'dunning', dunningLevel: 1 });
    render(
      <InvoiceDetailSheet
        invoice={invoice}
        open={true}
        onOpenChange={vi.fn()}
        onIncreaseDunning={onIncreaseDunning}
      />
    );

    fireEvent.click(screen.getByText('Mahnstufe erhöhen'));

    expect(onIncreaseDunning).toHaveBeenCalledWith(invoice);
  });

  it('deaktiviert Buttons während Laden', () => {
    const onMarkPaid = vi.fn();
    const onIncreaseDunning = vi.fn();
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ status: 'dunning', dunningLevel: 1 })}
        open={true}
        onOpenChange={vi.fn()}
        onMarkPaid={onMarkPaid}
        onIncreaseDunning={onIncreaseDunning}
        isLoading={true}
      />
    );

    expect(screen.getByText('Als bezahlt markieren').closest('button')).toBeDisabled();
    expect(screen.getByText('Mahnstufe erhöhen').closest('button')).toBeDisabled();
  });

  it('zeigt Rechnungsinformationen-Sektion', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice()}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Rechnungsinformationen')).toBeInTheDocument();
    expect(screen.getByText('Rechnungsnummer')).toBeInTheDocument();
    expect(screen.getByText('Rechnungsdatum')).toBeInTheDocument();
    expect(screen.getByText('Fälligkeitsdatum')).toBeInTheDocument();
    expect(screen.getByText('Betrag')).toBeInTheDocument();
  });

  it('zeigt Zahlungsinformationen-Sektion', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice()}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Zahlungsinformationen')).toBeInTheDocument();
    expect(screen.getByText('Bezahlt am')).toBeInTheDocument();
    expect(screen.getByText('Gezahlter Betrag')).toBeInTheDocument();
    expect(screen.getByText('Letzte Mahnung')).toBeInTheDocument();
  });

  it('zeigt Invoice-ID in Metadaten', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({ id: 'inv-test-123' })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('ID: inv-test-123')).toBeInTheDocument();
  });

  it('zeigt Zahlungsdaten wenn bezahlt', () => {
    render(
      <InvoiceDetailSheet
        invoice={createMockInvoice({
          status: 'paid',
          paidAt: '2025-01-10T14:30:00Z',
          paidAmount: 1500.0,
        })}
        open={true}
        onOpenChange={vi.fn()}
      />
    );

    // Should show formatted paid date
    expect(screen.getByText(/10\.01\.2025/)).toBeInTheDocument();
  });
});
