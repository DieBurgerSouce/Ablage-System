/**
 * DATEV Export API Service
 *
 * Stellt alle API-Aufrufe für das DATEV-Modul bereit.
 * Basiert auf dem Backend unter /api/v1/datev/
 */

import { apiClient } from '../client';

// =============================================================================
// ENUMS & TYPES
// =============================================================================

export type Kontenrahmen = 'SKR03' | 'SKR04';

export type DATEVExportStatus = 'completed' | 'failed' | 'partial';

export type DATEVExportType = 'buchungsstapel' | 'stammdaten';

export type SollHaben = 'S' | 'H';

// =============================================================================
// CONFIGURATION TYPES
// =============================================================================

export interface DATEVConfigurationCreate {
    berater_nr: string;
    mandanten_nr: string;
    wj_beginn: string;
    kontenrahmen: Kontenrahmen;
    incoming_expense_account?: string;
    incoming_creditor_account?: string;
    outgoing_revenue_account?: string;
    outgoing_debtor_account?: string;
    sammelkonto_kreditoren?: string;
    sammelkonto_debitoren?: string;
    sachkontenlange?: number;
    buchungstext_format?: string;
    is_default?: boolean;
}

export interface DATEVConfigurationUpdate {
    berater_nr?: string;
    mandanten_nr?: string;
    wj_beginn?: string;
    kontenrahmen?: Kontenrahmen;
    incoming_expense_account?: string;
    incoming_creditor_account?: string;
    outgoing_revenue_account?: string;
    outgoing_debtor_account?: string;
    sammelkonto_kreditoren?: string;
    sammelkonto_debitoren?: string;
    sachkontenlange?: number;
    buchungstext_format?: string;
    is_default?: boolean;
}

export interface DATEVConfigurationResponse {
    id: string;
    berater_nr: string;
    mandanten_nr: string;
    wj_beginn: string;
    kontenrahmen: Kontenrahmen;
    incoming_expense_account: string | null;
    incoming_creditor_account: string | null;
    outgoing_revenue_account: string | null;
    outgoing_debtor_account: string | null;
    sammelkonto_kreditoren: string;
    sammelkonto_debitoren: string;
    sachkontenlange: number;
    buchungstext_format: string;
    is_default: boolean;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

// =============================================================================
// VENDOR MAPPING TYPES
// =============================================================================

export interface DATEVVendorMappingCreate {
    vendor_name?: string;
    vendor_vat_id?: string;
    vendor_iban?: string;
    business_entity_id?: string;
    expense_account: string;
    creditor_account?: string;
    cost_center?: string;
    cost_object?: string;
}

export interface DATEVVendorMappingUpdate {
    vendor_name?: string;
    vendor_vat_id?: string;
    vendor_iban?: string;
    business_entity_id?: string;
    expense_account?: string;
    creditor_account?: string;
    cost_center?: string;
    cost_object?: string;
}

export interface DATEVVendorMappingResponse {
    id: string;
    config_id: string;
    vendor_name: string | null;
    vendor_vat_id: string | null;
    vendor_iban: string | null;
    business_entity_id: string | null;
    expense_account: string;
    creditor_account: string | null;
    cost_center: string | null;
    cost_object: string | null;
    created_at: string;
    updated_at: string;
}

// =============================================================================
// EXPORT TYPES
// =============================================================================

export interface DATEVExportRequest {
    config_id?: string;
    document_ids?: string[];
    period_from?: string;
    period_to?: string;
    include_already_exported?: boolean;
    export_type?: DATEVExportType;
}

export interface DATEVBuchungsstapelEntry {
    umsatz: number;
    soll_haben: SollHaben;
    wkz_umsatz: string;
    kurs: number | null;
    konto: string;
    gegenkonto: string;
    bu_schluessel: string | null;
    belegdatum: string;
    belegfeld_1: string;
    belegfeld_2: string | null;
    skonto: number | null;
    buchungstext: string;
    kostenstelle_1: string | null;
    kostenstelle_2: string | null;
    kostentraeger: string | null;
}

export interface DATEVExportPreview {
    document_count: number;
    period_from: string | null;
    period_to: string | null;
    total_amount: number;
    sample_entries: DATEVBuchungsstapelEntry[];
    warnings: string[];
    skipped_count: number;
    skipped_reasons: Record<string, number>;
}

export interface DATEVExportResponse {
    id: string;
    filename: string;
    export_type: DATEVExportType;
    document_count: number;
    file_size_bytes: number;
    status: DATEVExportStatus;
    content_hash: string;
    period_from: string | null;
    period_to: string | null;
    exported_at: string;
    download_url: string | null;
    included_documents: string[];
    skipped_documents: string[];
    warnings: string[];
}

export interface DATEVExportHistoryItem {
    id: string;
    export_type: DATEVExportType;
    filename: string;
    document_count: number;
    status: DATEVExportStatus;
    period_from: string | null;
    period_to: string | null;
    exported_at: string;
}

export interface DATEVExportHistoryResponse {
    items: DATEVExportHistoryItem[];
    total: number;
    page: number;
    page_size: number;
}

// =============================================================================
// KONTENRAHMEN TYPES
// =============================================================================

export interface KontenrahmenAccount {
    nummer: string;
    bezeichnung: string;
    kategorie: string;
}

export interface KontenrahmenInfo {
    name: Kontenrahmen;
    beschreibung: string;
    standard_konten: Record<string, string>;
    verfügbare_kategorien: string[];
}

// =============================================================================
// EXPORT DOWNLOAD RESULT
// =============================================================================

export interface DATEVExportDownloadResult {
    blob: Blob;
    filename: string;
    exportId: string | null;
    documentCount: number;
}

// =============================================================================
// DATEV SERVICE
// =============================================================================

const BASE_URL = '/datev';

export const datevService = {
    // =========================================================================
    // CONFIGURATION
    // =========================================================================

    /**
     * Neue DATEV-Konfiguration erstellen
     */
    createConfig: async (data: DATEVConfigurationCreate): Promise<DATEVConfigurationResponse> => {
        const response = await apiClient.post<DATEVConfigurationResponse>(
            `${BASE_URL}/config`,
            data
        );
        return response.data;
    },

    /**
     * Alle Konfigurationen des aktuellen Benutzers abrufen
     */
    getConfigs: async (): Promise<DATEVConfigurationResponse[]> => {
        const response = await apiClient.get<DATEVConfigurationResponse[]>(`${BASE_URL}/config`);
        return response.data;
    },

    /**
     * Standard-Konfiguration abrufen
     */
    getDefaultConfig: async (): Promise<DATEVConfigurationResponse> => {
        const response = await apiClient.get<DATEVConfigurationResponse>(
            `${BASE_URL}/config/default`
        );
        return response.data;
    },

    /**
     * Einzelne Konfiguration abrufen
     */
    getConfig: async (id: string): Promise<DATEVConfigurationResponse> => {
        const response = await apiClient.get<DATEVConfigurationResponse>(
            `${BASE_URL}/config/${id}`
        );
        return response.data;
    },

    /**
     * Konfiguration aktualisieren
     */
    updateConfig: async (
        id: string,
        data: DATEVConfigurationUpdate
    ): Promise<DATEVConfigurationResponse> => {
        const response = await apiClient.put<DATEVConfigurationResponse>(
            `${BASE_URL}/config/${id}`,
            data
        );
        return response.data;
    },

    /**
     * Konfiguration löschen (Soft-Delete)
     */
    deleteConfig: async (id: string): Promise<void> => {
        await apiClient.delete(`${BASE_URL}/config/${id}`);
    },

    // =========================================================================
    // VENDOR MAPPINGS
    // =========================================================================

    /**
     * Neues Vendor-Mapping erstellen
     */
    createVendorMapping: async (
        configId: string,
        data: DATEVVendorMappingCreate
    ): Promise<DATEVVendorMappingResponse> => {
        const response = await apiClient.post<DATEVVendorMappingResponse>(
            `${BASE_URL}/config/${configId}/vendors`,
            data
        );
        return response.data;
    },

    /**
     * Alle Vendor-Mappings einer Konfiguration abrufen
     */
    getVendorMappings: async (configId: string): Promise<DATEVVendorMappingResponse[]> => {
        const response = await apiClient.get<DATEVVendorMappingResponse[]>(
            `${BASE_URL}/config/${configId}/vendors`
        );
        return response.data;
    },

    /**
     * Vendor-Mapping aktualisieren
     */
    updateVendorMapping: async (
        configId: string,
        mappingId: string,
        data: DATEVVendorMappingUpdate
    ): Promise<DATEVVendorMappingResponse> => {
        const response = await apiClient.put<DATEVVendorMappingResponse>(
            `${BASE_URL}/config/${configId}/vendors/${mappingId}`,
            data
        );
        return response.data;
    },

    /**
     * Vendor-Mapping löschen
     */
    deleteVendorMapping: async (configId: string, mappingId: string): Promise<void> => {
        await apiClient.delete(`${BASE_URL}/config/${configId}/vendors/${mappingId}`);
    },

    // =========================================================================
    // EXPORT
    // =========================================================================

    /**
     * Export-Vorschau erstellen
     */
    previewExport: async (data: DATEVExportRequest): Promise<DATEVExportPreview> => {
        const response = await apiClient.post<DATEVExportPreview>(
            `${BASE_URL}/export/preview`,
            data
        );
        return response.data;
    },

    /**
     * Export ausführen und CSV herunterladen
     */
    executeExport: async (data: DATEVExportRequest): Promise<DATEVExportDownloadResult> => {
        const response = await apiClient.post(`${BASE_URL}/export`, data, {
            responseType: 'blob',
        });

        // Metadaten aus Response-Headers extrahieren
        const exportId = response.headers['x-datev-export-id'] || null;
        const documentCount = parseInt(response.headers['x-datev-document-count'] || '0', 10);
        const contentDisposition = response.headers['content-disposition'] || '';

        // Dateiname aus Content-Disposition extrahieren
        const filenameMatch = contentDisposition.match(/filename="(.+?)"/);
        const filename = filenameMatch
            ? filenameMatch[1]
            : `EXTF_Buchungsstapel_${new Date().toISOString().slice(0, 10)}.csv`;

        return {
            blob: response.data as Blob,
            filename,
            exportId,
            documentCount,
        };
    },

    /**
     * Export-Historie abrufen
     */
    getExportHistory: async (params?: {
        page?: number;
        page_size?: number;
    }): Promise<DATEVExportHistoryResponse> => {
        const response = await apiClient.get<DATEVExportHistoryResponse>(
            `${BASE_URL}/export/history`,
            { params }
        );
        return response.data;
    },

    // =========================================================================
    // KONTENRAHMEN
    // =========================================================================

    /**
     * Verfügbare Kontenrahmen abrufen
     */
    getKontenrahmen: async (): Promise<KontenrahmenInfo[]> => {
        const response = await apiClient.get<KontenrahmenInfo[]>(`${BASE_URL}/kontenrahmen`);
        return response.data;
    },
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Startet den Download einer Blob-Datei
 */
export function downloadBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}

/**
 * Formatiert einen Kontenrahmen-Namen für die Anzeige
 */
export function formatKontenrahmenName(kontenrahmen: Kontenrahmen): string {
    switch (kontenrahmen) {
        case 'SKR03':
            return 'SKR 03 (Industrie und Handel)';
        case 'SKR04':
            return 'SKR 04 (Bilanzierende Unternehmen)';
        default:
            return kontenrahmen;
    }
}

/**
 * Formatiert den Export-Status für die Anzeige
 */
export function formatExportStatus(status: DATEVExportStatus): string {
    switch (status) {
        case 'completed':
            return 'Erfolgreich';
        case 'failed':
            return 'Fehlgeschlagen';
        case 'partial':
            return 'Teilweise';
        default:
            return status;
    }
}
