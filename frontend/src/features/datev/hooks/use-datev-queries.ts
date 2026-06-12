/**
 * DATEV Query Hooks
 *
 * Zentrale Query-Verwaltung für das DATEV-Feature.
 * Verwendet TanStack Query für Server-State-Management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import {
    datevService,
    downloadBlob,
    type DATEVConfigurationCreate,
    type DATEVConfigurationUpdate,
    type DATEVVendorMappingCreate,
    type DATEVVendorMappingUpdate,
    type DATEVExportRequest,
} from '@/lib/api/services/datev';
import { QUERY_VOLATILE, QUERY_SEMI_STATIC } from '@/lib/api/query-config';

// =============================================================================
// STALE TIME KONFIGURATION
// =============================================================================

const STALE_TIMES = {
    configs: QUERY_SEMI_STATIC.staleTime,     // 5min
    vendors: QUERY_SEMI_STATIC.staleTime,     // 5min
    kontenrahmen: QUERY_SEMI_STATIC.gcTime,   // 30min (nicht Infinity - kann sich bei Updates ändern)
    history: QUERY_VOLATILE.staleTime,        // 30s (häufiger aktualisiert nach Exports)
} as const;

// =============================================================================
// QUERY KEYS
// =============================================================================

export const datevQueryKeys = {
    all: ['datev'] as const,

    // Configurations
    configs: () => [...datevQueryKeys.all, 'configs'] as const,
    configList: () => [...datevQueryKeys.configs(), 'list'] as const,
    configDefault: () => [...datevQueryKeys.configs(), 'default'] as const,
    configDetail: (id: string) => [...datevQueryKeys.configs(), 'detail', id] as const,

    // Vendor Mappings
    vendors: () => [...datevQueryKeys.all, 'vendors'] as const,
    vendorList: (configId: string) => [...datevQueryKeys.vendors(), 'list', configId] as const,

    // Export
    export: () => [...datevQueryKeys.all, 'export'] as const,
    exportHistory: (page?: number, pageSize?: number) =>
        [...datevQueryKeys.export(), 'history', page, pageSize] as const,

    // Kontenrahmen
    kontenrahmen: () => [...datevQueryKeys.all, 'kontenrahmen'] as const,
};

// =============================================================================
// CONFIGURATION HOOKS
// =============================================================================

/**
 * Alle DATEV-Konfigurationen abrufen
 */
export function useConfigs() {
    return useQuery({
        queryKey: datevQueryKeys.configList(),
        queryFn: () => datevService.getConfigs(),
        staleTime: STALE_TIMES.configs,
    });
}

/**
 * Standard-Konfiguration abrufen
 */
export function useDefaultConfig(enabled = true) {
    return useQuery({
        queryKey: datevQueryKeys.configDefault(),
        queryFn: () => datevService.getDefaultConfig(),
        staleTime: STALE_TIMES.configs,
        enabled,
        retry: false, // 404 wenn keine Default-Config existiert
    });
}

/**
 * Einzelne Konfiguration abrufen
 */
export function useConfig(id: string, enabled = true) {
    return useQuery({
        queryKey: datevQueryKeys.configDetail(id),
        queryFn: () => datevService.getConfig(id),
        staleTime: STALE_TIMES.configs,
        enabled: enabled && !!id,
    });
}

/**
 * Konfiguration erstellen
 */
export function useCreateConfig() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: DATEVConfigurationCreate) => datevService.createConfig(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Konfiguration erstellen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Konfiguration aktualisieren
 */
export function useUpdateConfig() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: DATEVConfigurationUpdate }) =>
            datevService.updateConfig(id, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
            queryClient.invalidateQueries({
                queryKey: datevQueryKeys.configDetail(variables.id),
            });
        },
        onError: (error, _variables) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Konfiguration aktualisieren fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Konfiguration löschen
 */
export function useDeleteConfig() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: string) => datevService.deleteConfig(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
        },
        onError: (error, _id) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Konfiguration löschen fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// VENDOR MAPPING HOOKS
// =============================================================================

/**
 * Vendor-Mappings einer Konfiguration abrufen
 */
export function useVendorMappings(configId: string, enabled = true) {
    return useQuery({
        queryKey: datevQueryKeys.vendorList(configId),
        queryFn: () => datevService.getVendorMappings(configId),
        staleTime: STALE_TIMES.vendors,
        enabled: enabled && !!configId,
    });
}

/**
 * Vendor-Mapping erstellen
 */
export function useCreateVendorMapping() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            configId,
            data,
        }: {
            configId: string;
            data: DATEVVendorMappingCreate;
        }) => datevService.createVendorMapping(configId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevQueryKeys.vendorList(variables.configId),
            });
            // Cascade: Configs auch invalidieren (kann vendor_count haben)
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
        },
        onError: (error, _variables) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Vendor-Mapping erstellen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Vendor-Mapping aktualisieren
 */
export function useUpdateVendorMapping() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            configId,
            mappingId,
            data,
        }: {
            configId: string;
            mappingId: string;
            data: DATEVVendorMappingUpdate;
        }) => datevService.updateVendorMapping(configId, mappingId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevQueryKeys.vendorList(variables.configId),
            });
            // Cascade: Configs auch invalidieren
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
        },
        onError: (error, _variables) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Vendor-Mapping aktualisieren fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Vendor-Mapping löschen
 */
export function useDeleteVendorMapping() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ configId, mappingId }: { configId: string; mappingId: string }) =>
            datevService.deleteVendorMapping(configId, mappingId),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: datevQueryKeys.vendorList(variables.configId),
            });
            // Cascade: Configs auch invalidieren
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.configs() });
        },
        onError: (error, _variables) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Vendor-Mapping löschen fehlgeschlagen', error);
            }
        },
    });
}

// =============================================================================
// EXPORT HOOKS
// =============================================================================

/**
 * Export-Vorschau erstellen
 */
export function useExportPreview() {
    return useMutation({
        mutationFn: (data: DATEVExportRequest) => datevService.previewExport(data),
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Export-Vorschau fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Export ausführen und CSV herunterladen
 */
export function useExecuteExport() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: DATEVExportRequest) => datevService.executeExport(data),
        onSuccess: (result) => {
            // Download starten
            downloadBlob(result.blob, result.filename);

            // Export-Historie aktualisieren (alle History-Queries)
            queryClient.invalidateQueries({ queryKey: datevQueryKeys.export() });
        },
        onError: (error) => {
            if (import.meta.env.DEV) {
                logger.error('DATEV: Export ausführen fehlgeschlagen', error);
            }
        },
    });
}

/**
 * Export-Historie abrufen
 */
export function useExportHistory(params?: { page?: number; page_size?: number }) {
    return useQuery({
        queryKey: datevQueryKeys.exportHistory(params?.page, params?.page_size),
        queryFn: () => datevService.getExportHistory(params),
        staleTime: STALE_TIMES.history,
    });
}

// =============================================================================
// KONTENRAHMEN HOOKS
// =============================================================================

/**
 * Verfügbare Kontenrahmen abrufen
 */
export function useKontenrahmen() {
    return useQuery({
        queryKey: datevQueryKeys.kontenrahmen(),
        queryFn: () => datevService.getKontenrahmen(),
        staleTime: STALE_TIMES.kontenrahmen,
    });
}
