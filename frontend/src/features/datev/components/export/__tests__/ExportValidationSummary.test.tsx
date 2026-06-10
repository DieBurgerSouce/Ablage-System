/**
 * ExportValidationSummary Unit Tests (W3-F4)
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { ExportValidationSummary } from '../ExportValidationSummary';
import type { DATEVValidationItem } from '@/lib/api/services/datev';

const ok = (filename: string): DATEVValidationItem => ({
    document_id: crypto.randomUUID(),
    filename,
    status: 'ok',
    reason: null,
});

const err = (filename: string, reason: string): DATEVValidationItem => ({
    document_id: crypto.randomUUID(),
    filename,
    status: 'error',
    reason,
});

describe('ExportValidationSummary', () => {
    it('zeigt OK- und Fehler-Zahl', () => {
        render(
            <ExportValidationSummary
                results={[ok('a.pdf'), ok('b.pdf'), err('c.pdf', 'Keine USt-IdNr')]}
            />
        );
        expect(screen.getByText('2 Belege OK')).toBeInTheDocument();
        expect(screen.getByText('1 Fehler')).toBeInTheDocument();
    });

    it('blendet Fehlerdetails erst auf Klick ein', () => {
        render(
            <ExportValidationSummary
                results={[ok('a.pdf'), err('c.pdf', 'Keine USt-IdNr')]}
            />
        );
        // Grund initial nicht sichtbar
        expect(screen.queryByText('Keine USt-IdNr')).not.toBeInTheDocument();
        fireEvent.click(screen.getByText('1 Belege werden übersprungen'));
        expect(screen.getByText('Keine USt-IdNr')).toBeInTheDocument();
        expect(screen.getByText('c.pdf')).toBeInTheDocument();
    });

    it('meldet bei null Fehlern alles sauber', () => {
        render(<ExportValidationSummary results={[ok('a.pdf'), ok('b.pdf')]} />);
        expect(screen.getByText('2 Belege OK')).toBeInTheDocument();
        expect(
            screen.getByText('Alle Belege sind kontiert und exportierbar.')
        ).toBeInTheDocument();
        expect(screen.queryByText(/Fehler/)).not.toBeInTheDocument();
    });

    it('rendert nichts ohne Ergebnisse', () => {
        const { container } = render(<ExportValidationSummary results={[]} />);
        expect(container.firstChild).toBeNull();
    });
});
