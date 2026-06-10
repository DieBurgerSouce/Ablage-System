/**
 * FilingSuggestionCard Unit Tests (W3-F1)
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { FilingSuggestionCard } from '../FilingSuggestionCard';
import type { FilingSuggestion } from '@/lib/api/services/automation';

const useFilingSuggestionsMock = vi.fn();
const acceptMutateMock = vi.fn();
const useAcceptFilingMock = vi.fn();

vi.mock('../../hooks/use-filing-queries', () => ({
    useFilingSuggestions: (...args: unknown[]) => useFilingSuggestionsMock(...args),
    useAcceptFiling: () => useAcceptFilingMock(),
}));

function suggestion(overrides: Partial<FilingSuggestion> = {}): FilingSuggestion {
    return {
        rule_id: 'r1',
        rule_name: 'Lieferanten-Regel',
        target_folder_id: null,
        target_category: 'rechnungen',
        confidence: 0.92,
        model_type: 'rule',
        auto_file: true,
        ...overrides,
    };
}

describe('FilingSuggestionCard', () => {
    beforeEach(() => {
        useFilingSuggestionsMock.mockReset();
        acceptMutateMock.mockReset();
        useAcceptFilingMock.mockReturnValue({
            mutate: acceptMutateMock,
            isPending: false,
            isError: false,
        });
    });

    it('zeigt den Vorschlag mit Kategorie und Konfidenz', () => {
        useFilingSuggestionsMock.mockReturnValue({
            data: [suggestion()],
            isLoading: false,
        });

        render(<FilingSuggestionCard documentId="doc-1" filename="rechnung.pdf" />);

        expect(screen.getByText('rechnung.pdf')).toBeInTheDocument();
        expect(screen.getByText('Rechnungen')).toBeInTheDocument();
        expect(screen.getByText(/92 %/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Annehmen/ })).toBeInTheDocument();
    });

    it('ruft accept mit der vorgeschlagenen Kategorie beim Annehmen', () => {
        useFilingSuggestionsMock.mockReturnValue({
            data: [suggestion()],
            isLoading: false,
        });

        render(<FilingSuggestionCard documentId="doc-1" filename="rechnung.pdf" />);
        fireEvent.click(screen.getByRole('button', { name: /Annehmen/ }));

        expect(acceptMutateMock).toHaveBeenCalledWith(
            { documentId: 'doc-1', targetCategory: 'rechnungen' },
            expect.any(Object)
        );
    });

    it('blendet die Ordner-Auswahl ein bei "Anderer Ordner"', () => {
        useFilingSuggestionsMock.mockReturnValue({
            data: [suggestion()],
            isLoading: false,
        });

        render(<FilingSuggestionCard documentId="doc-1" filename="rechnung.pdf" />);
        fireEvent.click(screen.getByRole('button', { name: /Anderer Ordner/ }));

        expect(
            screen.getByRole('combobox', { name: /Ordner wählen/ })
        ).toBeInTheDocument();
    });

    it('zeigt Ladezustand', () => {
        useFilingSuggestionsMock.mockReturnValue({ data: undefined, isLoading: true });

        render(<FilingSuggestionCard documentId="doc-1" filename="rechnung.pdf" />);
        expect(screen.getByText(/wird ermittelt/)).toBeInTheDocument();
    });

    it('bietet bei fehlendem Vorschlag direkt die Ordnerwahl', () => {
        useFilingSuggestionsMock.mockReturnValue({ data: [], isLoading: false });

        render(<FilingSuggestionCard documentId="doc-1" filename="unklar.pdf" />);
        expect(screen.getByText(/bitte Ordner wählen/i)).toBeInTheDocument();
        expect(
            screen.getByRole('combobox', { name: /Ordner wählen/ })
        ).toBeInTheDocument();
    });
});
