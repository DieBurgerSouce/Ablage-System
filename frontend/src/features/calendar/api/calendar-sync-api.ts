/**
 * Kalender-Synchronisation API Client
 *
 * API-Funktionen für die bidirektionale Kalender-Synchronisation
 * mit Google, Outlook, CalDAV und iCal-Export.
 */

import { apiClient } from '@/lib/api/client';
import type {
  OAuthStatusMap,
  OAuthAuthorizeRequest,
  OAuthAuthorizeResponse,
  SyncResult,
  SyncStatus,
  CalendarEventPreview,
  CalendarInfo,
  CalendarSyncConfig,
  ConnectionTestRequest,
  ConnectionTestResponse,
} from '../types/calendar-types';

// ==================== Query Keys ====================

export const calendarSyncKeys = {
  all: ['calendar-sync'] as const,
  config: () => [...calendarSyncKeys.all, 'config'] as const,
  oauthStatus: () => [...calendarSyncKeys.all, 'oauth-status'] as const,
  syncStatus: () => [...calendarSyncKeys.all, 'sync-status'] as const,
  preview: (daysAhead?: number) => [...calendarSyncKeys.all, 'preview', daysAhead] as const,
  calendars: () => [...calendarSyncKeys.all, 'calendars'] as const,
};

// ==================== Config ====================

export async function getCalendarSyncConfig(): Promise<CalendarSyncConfig> {
  const response = await apiClient.get<CalendarSyncConfig>('/calendar-sync/config');
  return response.data;
}

export async function updateCalendarSyncConfig(
  config: Partial<CalendarSyncConfig>
): Promise<CalendarSyncConfig> {
  const response = await apiClient.put<CalendarSyncConfig>('/calendar-sync/config', config);
  return response.data;
}

// ==================== OAuth ====================

export async function getOAuthStatus(): Promise<OAuthStatusMap> {
  const response = await apiClient.get<OAuthStatusMap>('/calendar-sync/oauth/status');
  return response.data;
}

export async function startOAuthFlow(
  request: OAuthAuthorizeRequest
): Promise<OAuthAuthorizeResponse> {
  const response = await apiClient.post<OAuthAuthorizeResponse>(
    '/calendar-sync/oauth/authorize',
    request
  );
  return response.data;
}

export async function revokeOAuth(provider: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(
    `/calendar-sync/oauth/revoke/${provider}`
  );
  return response.data;
}

// ==================== Sync ====================

export async function triggerSync(): Promise<SyncResult> {
  const response = await apiClient.post<SyncResult>('/calendar-sync/sync');
  return response.data;
}

export async function getSyncStatus(): Promise<SyncStatus> {
  const response = await apiClient.get<SyncStatus>('/calendar-sync/sync/status');
  return response.data;
}

// ==================== Preview & Calendars ====================

export async function getCalendarPreview(daysAhead?: number): Promise<CalendarEventPreview[]> {
  const params = daysAhead !== undefined ? { days_ahead: daysAhead } : {};
  const response = await apiClient.get<CalendarEventPreview[]>(
    '/calendar-sync/preview',
    { params }
  );
  return response.data;
}

export async function getAvailableCalendars(): Promise<CalendarInfo[]> {
  const response = await apiClient.get<CalendarInfo[]>('/calendar-sync/calendars');
  return response.data;
}

// ==================== Connection Test ====================

export async function testConnection(
  config: ConnectionTestRequest
): Promise<ConnectionTestResponse> {
  const response = await apiClient.post<ConnectionTestResponse>(
    '/calendar-sync/test-connection',
    config
  );
  return response.data;
}

// ==================== iCal Export ====================

export function getICalExportUrl(): string {
  return '/api/v1/calendar-sync/export.ics';
}
