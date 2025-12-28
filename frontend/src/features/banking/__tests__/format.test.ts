import { describe, it, expect } from 'vitest';
import {
    formatCurrency,
    formatDate,
    formatDateShort,
    formatDateTime,
    formatPercent,
    formatNumber,
} from '../utils/format';

describe('Banking Format Utilities', () => {
    describe('formatCurrency', () => {
        it('formatiert positive Beträge korrekt', () => {
            const result = formatCurrency(1234.56);
            // German format with EUR
            expect(result).toMatch(/1\.234,56/);
            expect(result).toContain('€');
        });

        it('formatiert null-Werte korrekt', () => {
            const result = formatCurrency(0);
            expect(result).toMatch(/0,00/);
        });

        it('formatiert negative Beträge korrekt', () => {
            const result = formatCurrency(-500);
            expect(result).toContain('500');
            expect(result).toContain('€');
        });

        it('respektiert benutzerdefinierte Dezimalstellen', () => {
            const result = formatCurrency(100.5, { decimals: 0 });
            expect(result).toMatch(/101|100/); // Gerundet
        });

        it('unterstützt andere Währungen', () => {
            const result = formatCurrency(100, { currency: 'USD' });
            expect(result).toContain('$');
        });
    });

    describe('formatDate', () => {
        it('formatiert ISO-Datumstring korrekt', () => {
            const result = formatDate('2025-01-15T10:00:00Z');
            expect(result).toBe('15.1.2025');
        });

        it('gibt "-" für null zurück', () => {
            expect(formatDate(null)).toBe('-');
        });

        it('gibt "-" für undefined zurück', () => {
            expect(formatDate(undefined)).toBe('-');
        });
    });

    describe('formatDateShort', () => {
        it('formatiert nur Tag und Monat', () => {
            const result = formatDateShort('2025-01-15T10:00:00Z');
            expect(result).toBe('15.01.');
        });
    });

    describe('formatDateTime', () => {
        it('formatiert Datum mit Uhrzeit', () => {
            const result = formatDateTime('2025-01-15T14:30:00Z');
            // Should include date and time
            expect(result).toMatch(/15.*01.*2025/);
            expect(result).toMatch(/\d{1,2}:\d{2}/);
        });

        it('gibt "-" für null zurück', () => {
            expect(formatDateTime(null)).toBe('-');
        });
    });

    describe('formatPercent', () => {
        it('formatiert Rohwerte korrekt (0-100 Skala)', () => {
            const result = formatPercent(85);
            expect(result).toMatch(/85,0.*%/);
        });

        it('formatiert Dezimalwerte korrekt', () => {
            const result = formatPercent(0.85, { isRawValue: false });
            expect(result).toMatch(/85,0.*%/);
        });

        it('respektiert Dezimalstellen', () => {
            const result = formatPercent(85.567, { decimals: 2 });
            expect(result).toMatch(/85,57.*%/);
        });

        it('formatiert 0% korrekt', () => {
            const result = formatPercent(0);
            expect(result).toMatch(/0,0.*%/);
        });

        it('formatiert 100% korrekt', () => {
            const result = formatPercent(100);
            expect(result).toMatch(/100,0.*%/);
        });
    });

    describe('formatNumber', () => {
        it('formatiert ganze Zahlen mit Tausendertrennzeichen', () => {
            const result = formatNumber(1234567);
            expect(result).toBe('1.234.567');
        });

        it('respektiert Dezimalstellen', () => {
            const result = formatNumber(1234.567, 2);
            expect(result).toBe('1.234,57');
        });

        it('formatiert 0 korrekt', () => {
            expect(formatNumber(0)).toBe('0');
        });
    });
});
