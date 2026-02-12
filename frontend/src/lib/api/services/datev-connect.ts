/**
 * DATEV Connect API Service
 *
 * Vollständige DATEVconnect API Integration mit OAuth2, Sync und Kontierung.
 * Basiert auf dem Backend unter /api/v1/datev-connect/
 */

import { apiClient } from '../client';

// =============================================================================
// ENUMS & STATUS TYPES
// =============================================================================

export type DATEVConnectionStatus = 'pending' | 'connected' | 'expired' | 'error' | 'revoked';

export type DATEVSyncType = 'stammdaten' | 'kontenplan' | 'buchungen' | 'belege';

export type DATEVKontierungStatus = 'suggested' | 'accepted' | 'rejected' | 'modified';

export type Kontenrahmen = 'SKR03' | 'SKR04';

// =============================================================================
// CONNECTION TYPES
// =============================================================================

export interface DATEVConnectionCreate {
    name: string;
    mandant_nr: string;
    berater_nr: string;
    kontenrahmen: Kontenrahmen;
    wirtschaftsjahr_beginn?: number;
    auto_kontierung?: boolean;
    auto_beleg_upload?: boolean;
}

export interface DATEVConnectionUpdate {
    name?: string;
    mandant_nr?: string;
    berater_nr?: string;
    kontenrahmen?: Kontenrahmen;
    wirtschaftsjahr_beginn?: number;
    auto_kontierung?: boolean;
    auto_beleg_upload?: boolean;
}

export interface DATEVConnectionResponse {
    id: string;
    name: string;
    mandant_nr: string;
    berater_nr: string;
    kontenrahmen: Kontenrahmen;
    wirtschaftsjahr_beginn: number;
    status: DATEVConnectionStatus;
    auto_kontierung: boolean;
    auto_beleg_upload: boolean;
    last_sync_at: string | null;
    token_expires_at: string | null;
    created_at: string;
    updated_at: string;
}

// =============================================================================
// OAUTH2 TYPES
// =============================================================================

export interface OAuth2AuthorizeResponse {
    authorization_url: string;
    state: string;
}

export interface OAuth2CallbackRequest {
    code: string;
    state: string;
}

export interface OAuth2TokenRefreshResponse {
    success: boolean;
    expires_at: string;
}

// =============================================================================
// SYNC TYPES
// =============================================================================

export interface DATEVSyncStatusResponse {
    connection_id: string;
    last_sync: {
        stammdaten: string | null;
        kontenplan: string | null;
        buchungen: string | null;
        belege: string | null;
    };
    pending_items: {
        buchungen: number;
        belege: number;
    };
    next_scheduled: string | null;
}

export interface DATEVSyncHistoryItem {
    id: string;
    connection_id: string;
    sync_type: DATEVSyncType;
    status: 'running' | 'completed' | 'failed';
    started_at: string;
    completed_at: string | null;
    items_synced: number;
    errors: string[];
}

export interface DATEVSyncHistoryResponse {
    items: DATEVSyncHistoryItem[];
    total: number;
    page: number;
    page_size: number;
}

// =============================================================================
// KONTENPLAN TYPES
// =============================================================================

export interface DATEVKontoResponse {
    id: string;
    connection_id: string;
    kontonummer: string;
    bezeichnung: string;
    kategorie: string;
    ist_aktiv: boolean;
    saldo: number | null;
    letzte_buchung: string | null;
}

export interface DATEVKontenplanResponse {
    items: DATEVKontoResponse[];
    total: number;
    kontenrahmen: Kontenrahmen;
    stand: string;
}

// =============================================================================
// BUCHUNG TYPES
// =============================================================================

export interface DATEVBuchungCreate {
    document_id: string;
    konto_soll: string;
    konto_haben: string;
    betrag: number;
    belegdatum: string;
    buchungstext: string;
    steuerschluessel?: string;
    kostenstelle?: string;
    kostentraeger?: string;
}

export interface DATEVBuchungResponse {
    id: string;
    connection_id: string;
    document_id: string;
    buchungs_nr: number | null;
    konto_soll: string;
    konto_haben: string;
    betrag: number;
    belegdatum: string;
    buchungstext: string;
    steuerschluessel: string | null;
    kostenstelle: string | null;
    kostentraeger: string | null;
    ist_festgeschrieben: boolean;
    festschreibung_hash: string | null;
    festgeschrieben_am: string | null;
    created_at: string;
    updated_at: string;
}

export interface DATEVBuchungenListResponse {
    items: DATEVBuchungResponse[];
    total: number;
    page: number;
    page_size: number;
    festgeschrieben_count: number;
    pending_count: number;
}

// =============================================================================
// KONTIERUNG TYPES
// =============================================================================

export interface DATEVKontierungsvorschlagResponse {
    id: string;
    document_id: string;
    connection_id: string;
    konto_soll: string;
    konto_soll_bezeichnung: string;
    konto_haben: string;
    konto_haben_bezeichnung: string;
    steuerschluessel: string | null;
    kostenstelle: string | null;
    confidence: number;
    status: DATEVKontierungStatus;
    pattern_id: string | null;
    created_at: string;
}

export interface DATEVKontierungAcceptRequest {
    konto_soll?: string;
    konto_haben?: string;
    steuerschluessel?: string;
    kostenstelle?: string;
}

export interface DATEVKontierungLearnRequest {
    document_id: string;
    lieferant_name: string;
    konto_soll: string;
    konto_haben: string;
    steuerschluessel?: string;
    betrag_von?: number;
    betrag_bis?: number;
}

// =============================================================================
// BELEG TYPES
// =============================================================================

export interface DATEVBelegUploadResponse {
    id: string;
    buchung_id: string;
    document_id: string;
    status: 'pending' | 'uploaded' | 'error';
    duo_beleg_id: string | null;
    uploaded_at: string | null;
    error_message: string | null;
}

// =============================================================================
// GOBD COMPLIANCE TYPES
// =============================================================================

export interface GoBDComplianceReportResponse {
    connection_id: string;
    report_date: string;
    total_buchungen: number;
    festgeschrieben_count: number;
    pending_count: number;
    integrity_check: {
        passed: number;
        failed: number;
        issues: Array<{
            buchung_id: string;
            buchungs_nr: number;
            issue: string;
        }>;
    };
    festschreibung_eligible: number;
}

export interface FestschreibungRequest {
    buchung_ids?: string[];
    all_pending?: boolean;
}

export interface FestschreibungResponse {
    success: boolean;
    festgeschrieben_count: number;
    buchung_ids: string[];
    festschreibung_timestamp: string;
}

// =============================================================================
// DATEV CONNECT SERVICE
// =============================================================================

const BASE_URL = '/datev-connect';

export const datevConnectService = {
    // =========================================================================
    // CONNECTIONS
    // =========================================================================

    /**
     * Neue DATEV-Verbindung erstellen
     */
    createConnection: async (data: DATEVConnectionCreate): Promise<DATEVConnectionResponse> => {
        const response = await apiClient.post<DATEVConnectionResponse>(
            `${BASE_URL}/connections`,
            data
        );
        return response.data;
    },

    /**
     * Alle Verbindungen abrufen
     */
    getConnections: async (): Promise<DATEVConnectionResponse[]> => {
        const response = await apiClient.get<DATEVConnectionResponse[]>(
            `${BASE_URL}/connections`
        );
        return response.data;
    },

    /**
     * Einzelne Verbindung abrufen
     */
    getConnection: async (id: string): Promise<DATEVConnectionResponse> => {
        const response = await apiClient.get<DATEVConnectionResponse>(
            `${BASE_URL}/connections/${id}`
        );
        return response.data;
    },

    /**
     * Verbindung aktualisieren
     */
    updateConnection: async (
        id: string,
        data: DATEVConnectionUpdate
    ): Promise<DATEVConnectionResponse> => {
        const response = await apiClient.patch<DATEVConnectionResponse>(
            `${BASE_URL}/connections/${id}`,
            data
        );
        return response.data;
    },

    /**
     * Verbindung löschen
     */
    deleteConnection: async (id: string): Promise<void> => {
        await apiClient.delete(`${BASE_URL}/connections/${id}`);
    },

    /**
     * Verbindung testen
     */
    testConnection: async (id: string): Promise<{ success: boolean; message: string }> => {
        const response = await apiClient.post<{ success: boolean; message: string }>(
            `${BASE_URL}/connections/${id}/test`
        );
        return response.data;
    },

    // =========================================================================
    // OAUTH2
    // =========================================================================

    /**
     * OAuth2 Autorisierungs-URL abrufen
     */
    getAuthorizationUrl: async (connectionId: string): Promise<OAuth2AuthorizeResponse> => {
        const response = await apiClient.get<OAuth2AuthorizeResponse>(
            `${BASE_URL}/connections/${connectionId}/oauth2/authorize`
        );
        return response.data;
    },

    /**
     * OAuth2 Callback verarbeiten
     */
    handleOAuthCallback: async (
        connectionId: string,
        data: OAuth2CallbackRequest
    ): Promise<DATEVConnectionResponse> => {
        const response = await apiClient.post<DATEVConnectionResponse>(
            `${BASE_URL}/connections/${connectionId}/oauth2/callback`,
            data
        );
        return response.data;
    },

    /**
     * OAuth2 Token manuell aktualisieren
     */
    refreshToken: async (connectionId: string): Promise<OAuth2TokenRefreshResponse> => {
        const response = await apiClient.post<OAuth2TokenRefreshResponse>(
            `${BASE_URL}/connections/${connectionId}/oauth2/refresh`
        );
        return response.data;
    },

    /**
     * OAuth2 Verbindung widerrufen
     */
    revokeConnection: async (connectionId: string): Promise<void> => {
        await apiClient.post(`${BASE_URL}/connections/${connectionId}/oauth2/revoke`);
    },

    // =========================================================================
    // SYNC
    // =========================================================================

    /**
     * Sync-Status abrufen
     */
    getSyncStatus: async (connectionId: string): Promise<DATEVSyncStatusResponse> => {
        const response = await apiClient.get<DATEVSyncStatusResponse>(
            `${BASE_URL}/sync/${connectionId}/status`
        );
        return response.data;
    },

    /**
     * Sync manuell auslösen
     */
    triggerSync: async (
        connectionId: string,
        syncTypes?: DATEVSyncType[]
    ): Promise<{ task_ids: string[] }> => {
        const response = await apiClient.post<{ task_ids: string[] }>(
            `${BASE_URL}/sync/${connectionId}/trigger`,
            { sync_types: syncTypes }
        );
        return response.data;
    },

    /**
     * Sync-Historie abrufen
     */
    getSyncHistory: async (
        connectionId: string,
        params?: { page?: number; page_size?: number; sync_type?: DATEVSyncType }
    ): Promise<DATEVSyncHistoryResponse> => {
        const response = await apiClient.get<DATEVSyncHistoryResponse>(
            `${BASE_URL}/sync/${connectionId}/history`,
            { params }
        );
        return response.data;
    },

    // =========================================================================
    // KONTENPLAN
    // =========================================================================

    /**
     * Kontenplan abrufen
     */
    getKontenplan: async (
        connectionId: string,
        params?: { kategorie?: string; search?: string }
    ): Promise<DATEVKontenplanResponse> => {
        const response = await apiClient.get<DATEVKontenplanResponse>(
            `${BASE_URL}/stammdaten/${connectionId}/konten`,
            { params }
        );
        return response.data;
    },

    // =========================================================================
    // BUCHUNGEN
    // =========================================================================

    /**
     * Buchungen abrufen
     */
    getBuchungen: async (
        connectionId: string,
        params?: {
            page?: number;
            page_size?: number;
            festgeschrieben?: boolean;
            von?: string;
            bis?: string;
        }
    ): Promise<DATEVBuchungenListResponse> => {
        const response = await apiClient.get<DATEVBuchungenListResponse>(
            `${BASE_URL}/buchungen/${connectionId}`,
            { params }
        );
        return response.data;
    },

    /**
     * Buchung erstellen
     */
    createBuchung: async (
        connectionId: string,
        data: DATEVBuchungCreate
    ): Promise<DATEVBuchungResponse> => {
        const response = await apiClient.post<DATEVBuchungResponse>(
            `${BASE_URL}/buchungen/${connectionId}`,
            data
        );
        return response.data;
    },

    /**
     * Buchung zu DATEV exportieren (Push)
     */
    exportBuchung: async (
        connectionId: string,
        buchungId: string
    ): Promise<{ success: boolean; datev_buchungs_nr: number }> => {
        const response = await apiClient.post<{ success: boolean; datev_buchungs_nr: number }>(
            `${BASE_URL}/buchungen/${connectionId}/${buchungId}/export`
        );
        return response.data;
    },

    // =========================================================================
    // KONTIERUNG
    // =========================================================================

    /**
     * Kontierungsvorschlag für Dokument abrufen
     */
    getKontierungsvorschlag: async (
        connectionId: string,
        documentId: string
    ): Promise<DATEVKontierungsvorschlagResponse> => {
        const response = await apiClient.get<DATEVKontierungsvorschlagResponse>(
            `${BASE_URL}/kontierung/${connectionId}/suggest/${documentId}`
        );
        return response.data;
    },

    /**
     * Kontierungsvorschlag akzeptieren
     */
    acceptKontierung: async (
        connectionId: string,
        vorschlagId: string,
        data?: DATEVKontierungAcceptRequest
    ): Promise<DATEVBuchungResponse> => {
        const response = await apiClient.post<DATEVBuchungResponse>(
            `${BASE_URL}/kontierung/${connectionId}/${vorschlagId}/accept`,
            data || {}
        );
        return response.data;
    },

    /**
     * Kontierungsvorschlag ablehnen
     */
    rejectKontierung: async (
        connectionId: string,
        vorschlagId: string
    ): Promise<void> => {
        await apiClient.post(
            `${BASE_URL}/kontierung/${connectionId}/${vorschlagId}/reject`
        );
    },

    /**
     * Neues Kontierungsmuster lernen
     */
    learnKontierungsmuster: async (
        connectionId: string,
        data: DATEVKontierungLearnRequest
    ): Promise<{ pattern_id: string; message: string }> => {
        const response = await apiClient.post<{ pattern_id: string; message: string }>(
            `${BASE_URL}/kontierung/${connectionId}/learn`,
            data
        );
        return response.data;
    },

    // =========================================================================
    // BELEGE
    // =========================================================================

    /**
     * Beleg zu DUO hochladen
     */
    uploadBeleg: async (
        connectionId: string,
        buchungId: string
    ): Promise<DATEVBelegUploadResponse> => {
        const response = await apiClient.post<DATEVBelegUploadResponse>(
            `${BASE_URL}/belege/${connectionId}/${buchungId}/upload`
        );
        return response.data;
    },

    /**
     * Beleg-Upload-Status abrufen
     */
    getBelegStatus: async (
        connectionId: string,
        buchungId: string
    ): Promise<DATEVBelegUploadResponse> => {
        const response = await apiClient.get<DATEVBelegUploadResponse>(
            `${BASE_URL}/belege/${connectionId}/${buchungId}/status`
        );
        return response.data;
    },

    // =========================================================================
    // GOBD COMPLIANCE
    // =========================================================================

    /**
     * GoBD Compliance Report abrufen
     */
    getComplianceReport: async (connectionId: string): Promise<GoBDComplianceReportResponse> => {
        const response = await apiClient.get<GoBDComplianceReportResponse>(
            `${BASE_URL}/gobd/${connectionId}/report`
        );
        return response.data;
    },

    /**
     * Buchungen festschreiben
     */
    festschreiben: async (
        connectionId: string,
        data: FestschreibungRequest
    ): Promise<FestschreibungResponse> => {
        const response = await apiClient.post<FestschreibungResponse>(
            `${BASE_URL}/gobd/${connectionId}/festschreiben`,
            data
        );
        return response.data;
    },

    /**
     * Integrität einer Buchung prüfen
     */
    verifyIntegrity: async (
        connectionId: string,
        buchungId: string
    ): Promise<{ valid: boolean; details: string }> => {
        const response = await apiClient.get<{ valid: boolean; details: string }>(
            `${BASE_URL}/gobd/${connectionId}/verify/${buchungId}`
        );
        return response.data;
    },
};

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Formatiert den Verbindungsstatus für die Anzeige
 */
export function formatConnectionStatus(status: DATEVConnectionStatus): string {
    switch (status) {
        case 'pending':
            return 'Ausstehend';
        case 'connected':
            return 'Verbunden';
        case 'expired':
            return 'Abgelaufen';
        case 'error':
            return 'Fehler';
        case 'revoked':
            return 'Widerrufen';
        default:
            return status;
    }
}

/**
 * Gibt die Badge-Variante für den Status zurück
 */
export function getConnectionStatusVariant(
    status: DATEVConnectionStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
    switch (status) {
        case 'connected':
            return 'default';
        case 'pending':
            return 'secondary';
        case 'expired':
        case 'error':
        case 'revoked':
            return 'destructive';
        default:
            return 'outline';
    }
}

/**
 * Formatiert den Sync-Typ für die Anzeige
 */
export function formatSyncType(syncType: DATEVSyncType): string {
    switch (syncType) {
        case 'stammdaten':
            return 'Stammdaten';
        case 'kontenplan':
            return 'Kontenplan';
        case 'buchungen':
            return 'Buchungen';
        case 'belege':
            return 'Belege';
        default:
            return syncType;
    }
}

/**
 * Formatiert die Konfidenz als Prozent
 */
export function formatConfidence(confidence: number): string {
    return `${Math.round(confidence * 100)}%`;
}
