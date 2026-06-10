/**
 * ImportConflictPreview Unit Tests (W3-F3)
 *
 * Sichert die Konflikt-Detailanzeige ab, die F3 im Erfolgs-Report
 * nutzbar macht (Nutzer sieht WELCHE Datensätze übersprungen wurden).
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { ImportConflictPreview } from '../ImportConflictPreview';
import type { ConflictInfo } from '../../api/lexware-admin-api';

const conflict = (overrides: Partial<ConflictInfo> = {}): ConflictInfo => ({
    identifier: '10234 Müller',
    conflict_type: 'critical',
    reason: 'IBAN unterscheidet sich zwischen Folie und Messer',
    folie_value: 'DE11...',
    messer_value: 'DE22...',
    ...overrides,
});

describe('ImportConflictPreview', () => {
    it('zeigt Leerzustand ohne Konflikte', () => {
        render(<ImportConflictPreview conflicts={[]} />);
        expect(screen.getByText('Keine Konflikte gefunden')).toBeInTheDocument();
    });

    it('zeigt Konflikt-Identifier und Typ-Zählung', () => {
        render(
            <ImportConflictPreview
                conflicts={[
                    conflict(),
                    conflict({ identifier: '99 Meyer', conflict_type: 'harmless' }),
                ]}
            />
        );
        expect(screen.getByText('10234 Müller')).toBeInTheDocument();
        expect(screen.getByText('1 kritisch')).toBeInTheDocument();
        expect(screen.getByText('1 harmlos')).toBeInTheDocument();
    });

    it('klappt Konfliktdetails (Grund + Werte) auf Klick auf', () => {
        render(<ImportConflictPreview conflicts={[conflict()]} />);
        // Grund initial eingeklappt
        expect(
            screen.queryByText(/IBAN unterscheidet sich/)
        ).not.toBeInTheDocument();
        fireEvent.click(screen.getByText('10234 Müller'));
        expect(screen.getByText(/IBAN unterscheidet sich/)).toBeInTheDocument();
        expect(screen.getByText('DE11...')).toBeInTheDocument();
        expect(screen.getByText('DE22...')).toBeInTheDocument();
    });
});
