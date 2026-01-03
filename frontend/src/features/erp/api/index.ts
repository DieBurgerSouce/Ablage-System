/**
 * ERP Integration API Client
 *
 * API-Funktionen fuer ERP-Verbindungen, Sync und Konflikte.
 */

import { apiClient as api } from '@/lib/api/client';
import type {
  ERPConnection,
  ERPConnectionCreate,
  ERPConnectionUpdate,
  ERPConnectionTestResult,
  ERPSyncHistory,
  ERPConflict,
  ERPConflictResolve,
  ERPStats,
  SyncTriggerResponse,
} from '../types';

const BASE_URL = '/admin/erp';

// =============================================================================
// Connection Management
// =============================================================================

export async function listConnections(): Promise<ERPConnection[]> {
  const response = await api.get<ERPConnection[]>(`${BASE_URL}/connections`);
  return response.data;
}

export async function getConnection(connectionId: string): Promise<ERPConnection> {
  const response = await api.get<ERPConnection>(`${BASE_URL}/connections/${connectionId}`);
  return response.data;
}

export async function createConnection(data: ERPConnectionCreate): Promise<ERPConnection> {
  const response = await api.post<ERPConnection>(`${BASE_URL}/connections`, data);
  return response.data;
}

export async function updateConnection(
  connectionId: string,
  data: ERPConnectionUpdate
): Promise<ERPConnection> {
  const response = await api.put<ERPConnection>(
    `${BASE_URL}/connections/${connectionId}`,
    data
  );
  return response.data;
}

export async function deleteConnection(connectionId: string): Promise<void> {
  await api.delete(`${BASE_URL}/connections/${connectionId}`);
}

export async function testConnection(connectionId: string): Promise<ERPConnectionTestResult> {
  const response = await api.post<ERPConnectionTestResult>(
    `${BASE_URL}/connections/${connectionId}/test`
  );
  return response.data;
}

// =============================================================================
// Sync Operations
// =============================================================================

export async function triggerSync(
  connectionId: string,
  syncType: 'full' | 'delta' = 'delta'
): Promise<SyncTriggerResponse> {
  const response = await api.post<SyncTriggerResponse>(
    `${BASE_URL}/connections/${connectionId}/sync`,
    null,
    { params: { sync_type: syncType } }
  );
  return response.data;
}

export async function getSyncHistory(
  connectionId: string,
  limit: number = 50
): Promise<ERPSyncHistory[]> {
  const response = await api.get<ERPSyncHistory[]>(
    `${BASE_URL}/connections/${connectionId}/sync-history`,
    { params: { limit } }
  );
  return response.data;
}

// =============================================================================
// Conflict Management
// =============================================================================

export async function listConflicts(
  connectionId?: string,
  status?: 'pending' | 'resolved' | 'ignored'
): Promise<ERPConflict[]> {
  const params: Record<string, string> = {};
  if (connectionId) params.connection_id = connectionId;
  if (status) params.status = status;

  const response = await api.get<ERPConflict[]>(`${BASE_URL}/conflicts`, { params });
  return response.data;
}

export async function resolveConflict(
  conflictId: string,
  resolution: ERPConflictResolve
): Promise<ERPConflict> {
  const response = await api.post<ERPConflict>(
    `${BASE_URL}/conflicts/${conflictId}/resolve`,
    resolution
  );
  return response.data;
}

// =============================================================================
// Statistics
// =============================================================================

export async function getERPStats(): Promise<ERPStats> {
  const response = await api.get<ERPStats>(`${BASE_URL}/stats`);
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const erpKeys = {
  all: ['erp'] as const,
  connections: () => [...erpKeys.all, 'connections'] as const,
  connection: (id: string) => [...erpKeys.connections(), id] as const,
  syncHistory: (id: string) => [...erpKeys.connection(id), 'sync-history'] as const,
  conflicts: (filters?: { connectionId?: string; status?: string }) =>
    [...erpKeys.all, 'conflicts', filters] as const,
  stats: () => [...erpKeys.all, 'stats'] as const,
};
