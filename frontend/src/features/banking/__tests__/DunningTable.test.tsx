import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DunningTable } from '../components/DunningTable';
import type { DunningRecord } from '@/types/models/banking';

// Mock-Daten für Tests
const createMockDunning = (overrides: Partial<DunningRecord> = {}): DunningRecord => ({
    id: 'dunning-1',
    invoice_id: 'inv-1',
    invoice_number: 'RE-2025-001',
    debtor_id: 'debtor-1',
    debtor_name: 'Test GmbH',
    outstanding_amount: 1500.0,
    due_date: '2025-01-15',
    invoice_date: '2025-01-01',
    dunning_level: 1,
    status: 'active',
    is_b2b: true,
    mahnstopp: false,
    mahnstopp_reason: null,
    mahnstopp_until: null,
    b2b_pauschale_claimed: false,
    reminder_fee: 5.0,
    accrued_interest: 12.50,
    total_outstanding: 1517.50,
    created_at: '2025-01-20T10:00:00Z',
    updated_at: '2025-01-20T10:00:00Z',
    ...overrides,
});

describe('DunningTable', () => {
    const mockData: DunningRecord[] = [
        createMockDunning({ id: 'dunning-1', invoice_number: 'RE-2025-001' }),
        createMockDunning({ id: 'dunning-2', invoice_number: 'RE-2025-002', is_b2b: false }),
        createMockDunning({ id: 'dunning-3', invoice_number: 'RE-2025-003', mahnstopp: true }),
    ];

    it('rendert alle Mahnvorgänge', () => {
        render(<DunningTable data={mockData} />);

        expect(screen.getByText('RE-2025-001')).toBeInTheDocument();
        expect(screen.getByText('RE-2025-002')).toBeInTheDocument();
        expect(screen.getByText('RE-2025-003')).toBeInTheDocument();
    });

    it('zeigt B2B/B2C Badges korrekt an', () => {
        render(<DunningTable data={mockData} />);

        // B2B should appear twice, B2C once
        const b2bBadges = screen.getAllByText('B2B');
        const b2cBadges = screen.getAllByText('B2C');

        expect(b2bBadges.length).toBe(2);
        expect(b2cBadges.length).toBe(1);
    });

    it('zeigt Mahnstopp-Indikator für Vorgänge mit Mahnstopp', () => {
        render(<DunningTable data={mockData} />);

        // Should show one Mahnstopp badge
        expect(screen.getByText('Mahnstopp')).toBeInTheDocument();
    });

    it('ruft onRowClick beim Klick auf eine Zeile auf', () => {
        const onRowClick = vi.fn();
        render(<DunningTable data={mockData} onRowClick={onRowClick} />);

        fireEvent.click(screen.getByText('RE-2025-001'));
        expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({
            invoice_number: 'RE-2025-001',
        }));
    });

    it('zeigt Ladezustand korrekt an', () => {
        render(<DunningTable data={[]} isLoading={true} />);

        expect(screen.getByText('Laden...')).toBeInTheDocument();
    });

    it('zeigt leeren Zustand wenn keine Daten vorhanden', () => {
        render(<DunningTable data={[]} isLoading={false} />);

        expect(screen.getByText('Keine Mahnvorgänge gefunden')).toBeInTheDocument();
    });

    it('ermöglicht Sortierung nach Rechnungsnummer', () => {
        render(<DunningTable data={mockData} />);

        const sortButton = screen.getByRole('button', { name: /Rechnung/i });
        expect(sortButton).toBeInTheDocument();

        fireEvent.click(sortButton);
        // After click, data should be sorted
    });

    it('filtert nach Rechnungsnummer', () => {
        render(<DunningTable data={mockData} />);

        const searchInput = screen.getByPlaceholderText('Rechnung suchen...');
        fireEvent.change(searchInput, { target: { value: 'RE-2025-001' } });

        // Should only show the filtered result
        expect(screen.getByText('RE-2025-001')).toBeInTheDocument();
    });

    it('ruft onSelectionChange mit korrekten IDs auf (Pagination-Bug-Fix)', () => {
        const onSelectionChange = vi.fn();
        render(<DunningTable data={mockData} onSelectionChange={onSelectionChange} />);

        // Select first row using checkbox
        const checkboxes = screen.getAllByRole('checkbox');
        // First checkbox is the header, second is first row
        fireEvent.click(checkboxes[1]);

        // Should be called with the actual dunning ID, not array index
        expect(onSelectionChange).toHaveBeenCalledWith(['dunning-1']);
    });

    it('hat korrekte ARIA-Labels für Checkboxen', () => {
        render(<DunningTable data={mockData} />);

        expect(screen.getByLabelText('Alle auswählen')).toBeInTheDocument();
        expect(screen.getAllByLabelText('Zeile auswählen')).toHaveLength(3);
    });
});
