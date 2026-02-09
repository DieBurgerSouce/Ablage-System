/**
 * ELSTER Export Query Hooks
 *
 * TanStack Query Hooks fuer USt-VA und ELSTER XML Export.
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import {
    getVatMonthlyReport,
    getVatQuarterlyReport,
    downloadElsterXml,
} from '../api/elster-api';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const elsterQueryKeys = {
    all: ['elster'] as const,
    vatReport: (companyId: string, year: number, period: number, type: string) =>
        [...elsterQueryKeys.all, 'vat-report', companyId, year, period, type] as const,
};

// =============================================================================
// HOOKS
// =============================================================================

/**
 * USt-VA Monatsbericht abrufen
 */
export function useVatMonthlyReport(
    companyId: string,
    year: number,
    month: number,
    enabled = true,
) {
    return useQuery({
        queryKey: elsterQueryKeys.vatReport(companyId, year, month, 'monthly'),
        queryFn: () => getVatMonthlyReport(companyId, year, month),
        staleTime: 60 * 1000, // 1 Minute
        enabled: enabled && !!companyId && year > 0 && month >= 1 && month <= 12,
    });
}

/**
 * USt-VA Quartalsbericht abrufen
 */
export function useVatQuarterlyReport(
    companyId: string,
    year: number,
    quarter: number,
    enabled = true,
) {
    return useQuery({
        queryKey: elsterQueryKeys.vatReport(companyId, year, quarter, 'quarterly'),
        queryFn: () => getVatQuarterlyReport(companyId, year, quarter),
        staleTime: 60 * 1000,
        enabled: enabled && !!companyId && year > 0 && quarter >= 1 && quarter <= 4,
    });
}

/**
 * ELSTER XML herunterladen (Mutation -> Download)
 */
export function useElsterXmlDownload() {
    return useMutation({
        mutationFn: (params: { companyId: string; year: number; month: number }) =>
            downloadElsterXml(params.companyId, params.year, params.month),
        onSuccess: (result) => {
            // Datei-Download triggern
            const url = window.URL.createObjectURL(result.blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = result.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('ELSTER: XML-Download fehlgeschlagen', error);
            }
        },
    });
}
