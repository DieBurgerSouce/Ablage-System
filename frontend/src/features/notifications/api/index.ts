/**
 * Notification Center - API Client
 *
 * API-Funktionen für Benachrichtigungen und Einstellungen
 */

import { apiClient } from '@/lib/api';
import type {
  Notification,
  NotificationsResponse,
  UnreadCountResponse,
  NotificationSettings,
  NotificationSettingsUpdate,
  NotificationFilter,
  BulkDismissPayload
} from '../types';

const BASE_PATH = '/api/v1/notifications';

/**
 * Benachrichtigungen abrufen (mit Pagination und Filter)
 */
export async function getNotifications(params: {
  page?: number;
  page_size?: number;
  filter?: NotificationFilter;
}): Promise<NotificationsResponse> {
  const { page = 1, page_size = 20, filter } = params;

  const queryParams = new URLSearchParams({
    page: page.toString(),
    page_size: page_size.toString()
  });

  if (filter?.priority) {
    queryParams.append('priority', filter.priority);
  }
  if (filter?.type) {
    queryParams.append('type', filter.type);
  }
  if (filter?.unread_only) {
    queryParams.append('unread_only', 'true');
  }

  const response = await apiClient.get<NotificationsResponse>(
    `${BASE_PATH}?${queryParams}`
  );
  return response.data;
}

/**
 * Einzelne Benachrichtigung abrufen
 */
export async function getNotificationById(id: string): Promise<Notification> {
  const response = await apiClient.get<Notification>(`${BASE_PATH}/${id}`);
  return response.data;
}

/**
 * Benachrichtigung als gelesen markieren
 */
export async function markAsRead(id: string): Promise<Notification> {
  const response = await apiClient.patch<Notification>(
    `${BASE_PATH}/${id}/read`
  );
  return response.data;
}

/**
 * Alle Benachrichtigungen als gelesen markieren
 */
export async function markAllAsRead(): Promise<{ count: number }> {
  const response = await apiClient.post<{ count: number }>(
    `${BASE_PATH}/mark-all-read`
  );
  return response.data;
}

/**
 * Benachrichtigung löschen
 */
export async function deleteNotification(id: string): Promise<void> {
  await apiClient.delete(`${BASE_PATH}/${id}`);
}

/**
 * Mehrere Benachrichtigungen löschen
 */
export async function bulkDismiss(
  payload: BulkDismissPayload
): Promise<{ count: number }> {
  const response = await apiClient.post<{ count: number }>(
    `${BASE_PATH}/bulk-dismiss`,
    payload
  );
  return response.data;
}

/**
 * Anzahl ungelesener Benachrichtigungen abrufen
 */
export async function getUnreadCount(): Promise<number> {
  const response = await apiClient.get<UnreadCountResponse>(
    `${BASE_PATH}/unread-count`
  );
  return response.data.count;
}

/**
 * Benachrichtigungseinstellungen abrufen
 */
export async function getSettings(): Promise<NotificationSettings> {
  const response = await apiClient.get<NotificationSettings>(
    `${BASE_PATH}/settings`
  );
  return response.data;
}

/**
 * Benachrichtigungseinstellungen aktualisieren
 */
export async function updateSettings(
  update: NotificationSettingsUpdate
): Promise<NotificationSettings> {
  const response = await apiClient.patch<NotificationSettings>(
    `${BASE_PATH}/settings`,
    update
  );
  return response.data;
}
