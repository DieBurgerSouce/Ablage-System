/**
 * ELSTER Export API Service
 *
 * API-Aufrufe für USt-VA ELSTER XML Export.
 * Basiert auf dem Backend unter /api/v1/accounting/
 */

import { apiClient } from '@/lib/api/client';

// =============================================================================
// TYPES
// =============================================================================

export interface VATSummaryResponse {
    kennziffer: string;
    label: string;
    net_amount: number;
    vat_amount: number;
    count: number;
}

export interface VATReportResponse {
    company_id: string;
    period_type: string;
    period_start: string;
    period_end: string;
    period_label: string;
    generated_at: string;
    status: string;
    output_vat_19: VATSummaryResponse;
    output_vat_7: VATSummaryResponse;
    inner_eu_deliveries: VATSummaryResponse;
    export_deliveries: VATSummaryResponse;
    input_vat: VATSummaryResponse;
    input_vat_inner_eu: VATSummaryResponse;
    input_vat_reverse_charge: VATSummaryResponse;
    inner_eu_acquisition_19: VATSummaryResponse;
    inner_eu_acquisition_7: VATSummaryResponse;
    total_output_vat: number;
    total_input_vat: number;
    vat_payable: number;
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * USt-VA Report für einen Monat abrufen
 */
export async function getVatMonthlyReport(
    companyId: string,
    year: number,
    month: number,
): Promise<VATReportResponse> {
    const { data } = await apiClient.get<VATReportResponse>(
        '/accounting/vat/monthly',
        { params: { company_id: companyId, year, month } },
    );
    return data;
}

/**
 * USt-VA Report für ein Quartal abrufen
 */
export async function getVatQuarterlyReport(
    companyId: string,
    year: number,
    quarter: number,
): Promise<VATReportResponse> {
    const { data } = await apiClient.get<VATReportResponse>(
        '/accounting/vat/quarterly',
        { params: { company_id: companyId, year, quarter } },
    );
    return data;
}

/**
 * ELSTER XML herunterladen (gibt Blob zurück)
 */
export async function downloadElsterXml(
    companyId: string,
    year: number,
    month: number,
): Promise<{ blob: Blob; filename: string }> {
    const response = await apiClient.get('/accounting/vat/elster-xml', {
        params: { company_id: companyId, year, month },
        responseType: 'blob',
    });

    // Filename aus Content-Disposition Header oder Fallback
    const disposition = response.headers['content-disposition'] as string | undefined;
    let filename = `UStVA_${year}_${String(month).padStart(2, '0')}.xml`;
    if (disposition) {
        const match = disposition.match(/filename="?([^";\n]+)"?/);
        if (match) {
            filename = match[1];
        }
    }

    return { blob: response.data as Blob, filename };
}
