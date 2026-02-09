/**
 * Anlage EUeR API Service
 *
 * API-Aufrufe fuer Einnahmen-Ueberschuss-Rechnung und Anlage EUeR Export.
 * Basiert auf dem Backend unter /api/v1/accounting/eur/
 */

import { apiClient } from '@/lib/api/client';

// =============================================================================
// TYPES
// =============================================================================

export interface EURCategorySummary {
    category: string;
    label: string;
    amount: number;
    count: number;
}

export interface EURReportResponse {
    company_id: string;
    fiscal_year: number;
    period_start: string;
    period_end: string;
    generated_at: string;
    status: string;
    income_categories: EURCategorySummary[];
    total_income: number;
    expense_categories: EURCategorySummary[];
    total_expenses: number;
    profit_loss: number;
    is_profit: boolean;
    deductible_vat: number;
}

export interface AnlageEUeRData {
    Jahr: number;
    Zeile_11: number;
    Zeile_12: number;
    Zeile_14: number;
    Zeile_16: number;
    Zeile_18: number;
    Zeile_20: number;
    Zeile_22: number;
    Zeile_27: number;
    Zeile_30: number;
    Zeile_35: number;
    Zeile_36: number;
    Zeile_40: number;
    Zeile_42: number;
    Zeile_43: number;
}

export interface AnlageEUeRResponse {
    fiscal_year: number;
    company_id: string;
    anlage_eur: AnlageEUeRData;
    generated_at: string;
}

export interface YTDMonthData {
    month: number;
    month_name: string;
    income: number;
    expenses: number;
    profit_loss: number;
}

export interface YTDSummaryResponse {
    year: number;
    months_completed: number;
    total_income: number;
    total_expenses: number;
    cumulative_profit: number;
    avg_monthly_income: number;
    avg_monthly_expenses: number;
    monthly_data: YTDMonthData[];
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * Jahres-EUeR Report abrufen
 */
export async function getEurReport(
    companyId: string,
    fiscalYear: number,
): Promise<EURReportResponse> {
    const { data } = await apiClient.get<EURReportResponse>(
        '/accounting/eur/annual',
        { params: { company_id: companyId, fiscal_year: fiscalYear } },
    );
    return data;
}

/**
 * Anlage EUeR (Steuerformular-Daten) abrufen
 */
export async function getAnlageEuer(
    companyId: string,
    fiscalYear: number,
): Promise<AnlageEUeRResponse> {
    const { data } = await apiClient.get<AnlageEUeRResponse>(
        '/accounting/eur/anlage-eur',
        { params: { company_id: companyId, fiscal_year: fiscalYear } },
    );
    return data;
}

/**
 * Year-to-Date EUeR Zusammenfassung abrufen
 */
export async function getEurYtd(
    companyId: string,
    year: number,
): Promise<YTDSummaryResponse> {
    const { data } = await apiClient.get<YTDSummaryResponse>(
        '/accounting/eur/ytd',
        { params: { company_id: companyId, year } },
    );
    return data;
}

/**
 * Anlage EUeR HTML Export URL generieren (fuer Browser-Druck)
 */
export function getAnlageEuerHtmlUrl(
    companyId: string,
    fiscalYear: number,
): string {
    const baseUrl = import.meta.env.VITE_API_URL || '/api/v1';
    return `${baseUrl}/accounting/eur/anlage-eur-html?company_id=${encodeURIComponent(companyId)}&fiscal_year=${encodeURIComponent(fiscalYear)}`;
}
