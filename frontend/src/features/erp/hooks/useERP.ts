/**
 * ERP Integration React Query Hooks
 *
 * Custom Hooks fuer ERP-Daten mit TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  listConnections,
  getConnection,
  createConnection,
  updateConnection,
  deleteConnection,
  testConnection,
  triggerSync,
  getSyncHistory,
  listConflicts,
  resolveConflict,
  getERPStats,
  erpKeys,
} from '../api';
import type {
  ERPConnectionCreate,
  ERPConnectionUpdate,
  ERPConflictResolve,
} from '../types';

// =============================================================================
// Connection Hooks
// =============================================================================

export function useERPConnections() {
  return useQuery({
    queryKey: erpKeys.connections(),
    queryFn: listConnections,
  });
}

export function useERPConnection(connectionId: string) {
  return useQuery({
    queryKey: erpKeys.connection(connectionId),
    queryFn: () => getConnection(connectionId),
    enabled: !!connectionId,
  });
}

export function useCreateConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ERPConnectionCreate) => createConnection(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.connections() });
      toast.success('ERP-Verbindung erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

export function useUpdateConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      connectionId,
      data,
    }: {
      connectionId: string;
      data: ERPConnectionUpdate;
    }) => updateConnection(connectionId, data),
    onSuccess: (_, { connectionId }) => {
      queryClient.invalidateQueries({ queryKey: erpKeys.connections() });
      queryClient.invalidateQueries({ queryKey: erpKeys.connection(connectionId) });
      toast.success('ERP-Verbindung aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

export function useDeleteConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (connectionId: string) => deleteConnection(connectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.connections() });
      toast.success('ERP-Verbindung geloescht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Loeschen: ${error.message}`);
    },
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: (connectionId: string) => testConnection(connectionId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(`Verbindung erfolgreich (${result.erp_type} v${result.version})`);
      } else {
        toast.error(`Verbindung fehlgeschlagen: ${result.error}`);
      }
    },
    onError: (error: Error) => {
      toast.error(`Verbindungstest fehlgeschlagen: ${error.message}`);
    },
  });
}

// =============================================================================
// Sync Hooks
// =============================================================================

export function useTriggerSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      connectionId,
      syncType = 'delta',
    }: {
      connectionId: string;
      syncType?: 'full' | 'delta';
    }) => triggerSync(connectionId, syncType),
    onSuccess: (result, { connectionId }) => {
      queryClient.invalidateQueries({ queryKey: erpKeys.syncHistory(connectionId) });
      toast.success(`Synchronisation gestartet (Task: ${result.task_id})`);
    },
    onError: (error: Error) => {
      toast.error(`Sync-Fehler: ${error.message}`);
    },
  });
}

export function useSyncHistory(connectionId: string, limit: number = 50) {
  return useQuery({
    queryKey: erpKeys.syncHistory(connectionId),
    queryFn: () => getSyncHistory(connectionId, limit),
    enabled: !!connectionId,
    refetchInterval: 30000, // Alle 30 Sekunden aktualisieren
  });
}

// =============================================================================
// Conflict Hooks
// =============================================================================

export function useERPConflicts(
  connectionId?: string,
  status?: 'pending' | 'resolved' | 'ignored'
) {
  return useQuery({
    queryKey: erpKeys.conflicts({ connectionId, status }),
    queryFn: () => listConflicts(connectionId, status),
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}

export function useResolveConflict() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      conflictId,
      resolution,
    }: {
      conflictId: string;
      resolution: ERPConflictResolve;
    }) => resolveConflict(conflictId, resolution),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: erpKeys.conflicts() });
      queryClient.invalidateQueries({ queryKey: erpKeys.stats() });
      toast.success('Konflikt aufgeloest');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aufloesen: ${error.message}`);
    },
  });
}

// =============================================================================
// Stats Hook
// =============================================================================

export function useERPStats() {
  return useQuery({
    queryKey: erpKeys.stats(),
    queryFn: getERPStats,
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}
