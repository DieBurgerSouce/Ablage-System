/**
 * Anlage EUeR Query Hooks
 *
 * TanStack Query Hooks für EUeR Report und Anlage EUeR Export.
 */

import { useQuery } from '@tanstack/react-query';
import {
    getEurReport,
    getAnlageEuer,
    getEurYtd,
} from '../api/euer-api';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const euerQueryKeys = {
    all: ['euer'] as const,
    report: (companyId: string, year: number) =>
        [...euerQueryKeys.all, 'report', companyId, year] as const,
    anlage: (companyId: string, year: number) =>
        [...euerQueryKeys.all, 'anlage', companyId, year] as const,
    ytd: (companyId: string, year: number) =>
        [...euerQueryKeys.all, 'ytd', companyId, year] as const,
};

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Jahres-EUeR Report abrufen
 */
export function useEurReport(
    companyId: string,
    fiscalYear: number,
    enabled = true,
) {
    return useQuery({
        queryKey: euerQueryKeys.report(companyId, fiscalYear),
        queryFn: () => getEurReport(companyId, fiscalYear),
        staleTime: 60 * 1000,
        enabled: enabled && !!companyId && fiscalYear > 0,
    });
}

/**
 * Anlage EUeR (Steuerformular) abrufen
 */
export function useAnlageEuer(
    companyId: string,
    fiscalYear: number,
    enabled = true,
) {
    return useQuery({
        queryKey: euerQueryKeys.anlage(companyId, fiscalYear),
        queryFn: () => getAnlageEuer(companyId, fiscalYear),
        staleTime: 60 * 1000,
        enabled: enabled && !!companyId && fiscalYear > 0,
    });
}

/**
 * Year-to-Date EUeR Zusammenfassung
 */
export function useEurYtd(
    companyId: string,
    year: number,
    enabled = true,
) {
    return useQuery({
        queryKey: euerQueryKeys.ytd(companyId, year),
        queryFn: () => getEurYtd(companyId, year),
        staleTime: 60 * 1000,
        enabled: enabled && !!companyId && year > 0,
    });
}
