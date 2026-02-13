/**
 * DATEV Connect Query Hooks
 *
 * Query-Verwaltung für die DATEVconnect API Integration.
 * Verwendet TanStack Query für Server-State-Management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import {
    datevConnectService,
    type DATEVConnectionCreate,
    type DATEVConnectionUpdate,
    type DATEVSyncType,
    type DATEVBuchungCreate,
    type DATEVKontierungAcceptRequest,
    type DATEVKontierungLearnRequest,
    type FestschreibungRequest,
} from '@/lib/api/services/datev-connect';

// =============================================================================
// STALE TIME KONFIGURATION
// =============================================================================

const STALE_TIMES = {
    connections: 5 * 60 * 1000,     // 5 Minuten
    syncStatus: 30 * 1000,          // 30 Sekunden (häufig aktualisiert)
    syncHistory: 60 * 1000,         // 1 Minute
    kontenplan: 30 * 60 * 1000,     // 30 Minuten
    buchungen: 60 * 1000,           // 1 Minute
    kontierung: 60 * 1000,          // 1 Minute
    compliance: 5 * 60 * 1000,      // 5 Minuten
} as const;

// =============================================================================
// QUERY KEYS
// =============================================================================

export const datevConnectQueryKeys = {
    all: ['datev-connect'] as const,

    // Connections
    connections: () => [...datevConnectQueryKeys.all, 'connections'] as const,
    connectionList: () => [...datevConnectQueryKeys.connections(), 'list'] as const,
    connectionDetail: (id: string) => [...datevConnectQueryKeys.connections(), 'detail', id] as const,

    // Sync
    sync: () => [...datevConnectQueryKeys.all, 'sync'] as const,
    syncStatus: (connectionId: string) => [...datevConnectQueryKeys.sync(), 'status', connectionId] as const,
    syncHistory: (connectionId: string, page?: number, pageSize?: number, syncType?: DATEVSyncType) =>
        [...datevConnectQueryKeys.sync(), 'history', connectionId, page, pageSize, syncType] as const,

    // Kontenplan
    kontenplan: (connectionId: string) => [...datevConnectQueryKeys.all, 'kontenplan', connectionId] as const,

    // Buchungen
    buchungen: () => [...datevConnectQueryKeys.all, 'buchungen'] as const,
    buchungenList: (connectionId: string, params?: Record<string, unknown>) =>
        [...datevConnectQueryKeys.buchungen(), 'list', connectionId, params] as const,

    // Kontierung
    kontierung: () => [...datevConnectQueryKeys.all, 'kontierung'] as const,
    kontierungVorschlag: (connectionId: string, documentId: string) =>
        [...datevConnectQueryKeys.kontierung(), 'vorschlag', connectionId, documentId] as const,
    kontierungList: (connectionId: string) =>
        [...datevConnectQueryKeys.kontierung(), 'list', connectionId] as const,

    // GoBD Compliance
    compliance: () => [...datevConnectQueryKeys.all, 'compliance'] as const,
    complianceReport: (connectionId: string) =>
        [...datevConnectQueryKeys.compliance(), 'report', connectionId] as const,
};

// =============================================================================
// CONNECTION HOOKS
// =============================================================================

/**
 * Alle DATEV Connect Verbindungen abrufen
 */
export function useConnections() {
    return useQuery({
        queryKey: datevConnectQueryKeys.connectionList(),
        queryFn: () => datevConnectService.getConnections(),
        staleTime: STALE_TIMES.connections,
    });
}

/**
 * Einzelne Verbindung abrufen
 */
export function useConnection(id: string, enabled = true) {
    return useQuery({
        queryKey: datevConnectQueryKeys.connectionDetail(id),
        queryFn: () => datevConnectService.getConnection(id),
        staleTime: STALE_TIMES.connections,
        enabled: enabled && !!id,
    });
}

/**
 * Verbindung erstellen
 */
export function useCreateConnection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: DATEVConnectionCreate) => datevConnectService.createConnection(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: datevConnectQueryKeys.connections() });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Verbindung erstellen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Verbindung aktualisieren
 */
export function useUpdateConnection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: DATEVConnectionUpdate }) =>
            datevConnectService.updateConnection(id, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: datevConnectQueryKeys.connections() });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.connectionDetail(variables.id),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Verbindung aktualisieren fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Verbindung löschen
 */
export function useDeleteConnection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: string) => datevConnectService.deleteConnection(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: datevConnectQueryKeys.connections() });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Verbindung löschen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Verbindung testen
 */
export function useTestConnection() {
    return useMutation({
        mutationFn: (id: string) => datevConnectService.testConnection(id),
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Verbindungstest fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// OAUTH2 HOOKS
// =============================================================================

/**
 * OAuth2 Autorisierung starten
 */
export function useStartOAuth2() {
    return useMutation({
        mutationFn: (connectionId: string) => datevConnectService.getAuthorizationUrl(connectionId),
        onSuccess: (result) => {
            // Redirect zu DATEV OAuth2
            window.location.href = result.authorization_url;
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: OAuth2 Start fehlgeschlagen', error);
            }
        },
    });
}

/**
 * OAuth2 Callback verarbeiten
 */
export function useOAuth2Callback() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, code, state }: { connectionId: string; code: string; state: string }) =>
            datevConnectService.handleOAuthCallback(connectionId, { code, state }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: datevConnectQueryKeys.connections() });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.connectionDetail(variables.connectionId),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: OAuth2 Callback fehlgeschlagen', error);
            }
        },
    });
}

/**
 * OAuth2 Token aktualisieren
 */
export function useRefreshOAuth2Token() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (connectionId: string) => datevConnectService.refreshToken(connectionId),
        onSuccess: (_, connectionId) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.connectionDetail(connectionId),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Token Refresh fehlgeschlagen', error);
            }
        },
    });
}

/**
 * OAuth2 Verbindung widerrufen
 */
export function useRevokeConnection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (connectionId: string) => datevConnectService.revokeConnection(connectionId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: datevConnectQueryKeys.connections() });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Verbindung widerrufen fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// SYNC HOOKS
// =============================================================================

/**
 * Sync-Status abrufen
 */
export function useSyncStatus(connectionId: string, enabled = true) {
    return useQuery({
        queryKey: datevConnectQueryKeys.syncStatus(connectionId),
        queryFn: () => datevConnectService.getSyncStatus(connectionId),
        staleTime: STALE_TIMES.syncStatus,
        enabled: enabled && !!connectionId,
        refetchInterval: 30000, // Alle 30 Sekunden aktualisieren
    });
}

/**
 * Sync manuell auslösen
 */
export function useTriggerSync() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, syncTypes }: { connectionId: string; syncTypes?: DATEVSyncType[] }) =>
            datevConnectService.triggerSync(connectionId, syncTypes),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.syncStatus(variables.connectionId),
            });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.sync(),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Sync auslösen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Sync-Historie abrufen
 */
export function useSyncHistory(
    connectionId: string,
    params?: { page?: number; page_size?: number; sync_type?: DATEVSyncType },
    enabled = true
) {
    return useQuery({
        queryKey: datevConnectQueryKeys.syncHistory(
            connectionId,
            params?.page,
            params?.page_size,
            params?.sync_type
        ),
        queryFn: () => datevConnectService.getSyncHistory(connectionId, params),
        staleTime: STALE_TIMES.syncHistory,
        enabled: enabled && !!connectionId,
    });
}

// =============================================================================
// KONTENPLAN HOOKS
// =============================================================================

/**
 * Kontenplan abrufen
 */
export function useKontenplan(
    connectionId: string,
    params?: { kategorie?: string; search?: string },
    enabled = true
) {
    return useQuery({
        queryKey: datevConnectQueryKeys.kontenplan(connectionId),
        queryFn: () => datevConnectService.getKontenplan(connectionId, params),
        staleTime: STALE_TIMES.kontenplan,
        enabled: enabled && !!connectionId,
    });
}

// =============================================================================
// BUCHUNGEN HOOKS
// =============================================================================

/**
 * Buchungen abrufen
 */
export function useBuchungen(
    connectionId: string,
    params?: {
        page?: number;
        page_size?: number;
        festgeschrieben?: boolean;
        von?: string;
        bis?: string;
    },
    enabled = true
) {
    return useQuery({
        queryKey: datevConnectQueryKeys.buchungenList(connectionId, params),
        queryFn: () => datevConnectService.getBuchungen(connectionId, params),
        staleTime: STALE_TIMES.buchungen,
        enabled: enabled && !!connectionId,
    });
}

/**
 * Buchung erstellen
 */
export function useCreateBuchung() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, data }: { connectionId: string; data: DATEVBuchungCreate }) =>
            datevConnectService.createBuchung(connectionId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.buchungen(),
            });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.syncStatus(variables.connectionId),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Buchung erstellen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Buchung zu DATEV exportieren
 */
export function useExportBuchung() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, buchungId }: { connectionId: string; buchungId: string }) =>
            datevConnectService.exportBuchung(connectionId, buchungId),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.buchungen(),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Buchung exportieren fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// KONTIERUNG HOOKS
// =============================================================================

/**
 * Kontierungsvorschlag abrufen
 */
export function useKontierungsvorschlag(
    connectionId: string,
    documentId: string,
    enabled = true
) {
    return useQuery({
        queryKey: datevConnectQueryKeys.kontierungVorschlag(connectionId, documentId),
        queryFn: () => datevConnectService.getKontierungsvorschlag(connectionId, documentId),
        staleTime: STALE_TIMES.kontierung,
        enabled: enabled && !!connectionId && !!documentId,
    });
}

/**
 * Alle ausstehenden Kontierungsvorschlaege fuer eine Verbindung
 */
export function useKontierungsvorschlaege(connectionId: string, enabled = true) {
    return useQuery({
        queryKey: datevConnectQueryKeys.kontierungList(connectionId),
        queryFn: () => datevConnectService.getKontierungsvorschlaege(connectionId),
        staleTime: STALE_TIMES.kontierung,
        enabled: enabled && !!connectionId,
    });
}

/**
 * Kontierungsvorschlag akzeptieren
 */
export function useAcceptKontierung() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            connectionId,
            vorschlagId,
            data,
        }: {
            connectionId: string;
            vorschlagId: string;
            data?: DATEVKontierungAcceptRequest;
        }) => datevConnectService.acceptKontierung(connectionId, vorschlagId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.kontierung(),
            });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.buchungen(),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Kontierung akzeptieren fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Kontierungsvorschlag ablehnen
 */
export function useRejectKontierung() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, vorschlagId }: { connectionId: string; vorschlagId: string }) =>
            datevConnectService.rejectKontierung(connectionId, vorschlagId),
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.kontierung(),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Kontierung ablehnen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Kontierungsmuster lernen
 */
export function useLearnKontierung() {
    return useMutation({
        mutationFn: ({ connectionId, data }: { connectionId: string; data: DATEVKontierungLearnRequest }) =>
            datevConnectService.learnKontierungsmuster(connectionId, data),
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Kontierung lernen fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// GOBD COMPLIANCE HOOKS
// =============================================================================

/**
 * GoBD Compliance Report abrufen
 */
export function useComplianceReport(connectionId: string, enabled = true) {
    return useQuery({
        queryKey: datevConnectQueryKeys.complianceReport(connectionId),
        queryFn: () => datevConnectService.getComplianceReport(connectionId),
        staleTime: STALE_TIMES.compliance,
        enabled: enabled && !!connectionId,
    });
}

/**
 * Buchungen festschreiben
 */
export function useFestschreiben() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ connectionId, data }: { connectionId: string; data: FestschreibungRequest }) =>
            datevConnectService.festschreiben(connectionId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.buchungen(),
            });
            queryClient.invalidateQueries({
                queryKey: datevConnectQueryKeys.complianceReport(variables.connectionId),
            });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Festschreiben fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Integrität prüfen
 */
export function useVerifyIntegrity() {
    return useMutation({
        mutationFn: ({ connectionId, buchungId }: { connectionId: string; buchungId: string }) =>
            datevConnectService.verifyIntegrity(connectionId, buchungId),
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV Connect: Integritätsprüfung fehlgeschlagen', error);
            }
        },
    });
}
