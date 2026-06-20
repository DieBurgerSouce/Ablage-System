/**
 * Notification Center - API Client
 *
 * API-Funktionen für Benachrichtigungen und Einstellungen.
 *
 * ECHTER BACKEND-VERTRAG (B5, 2026-06-12, app/api/v1/notifications.py +
 * app/db/schemas.py::NotificationsListResponse):
 *
 *   GET /api/v1/notifications/?page=&per_page=&unread_only=
 *   -> { "notifications": [ { id, type, title, message, isRead, createdAt,
 *        actionUrl, documentId, documentName, fromUserId, fromUserName,
 *        fromUserAvatar } ], "unreadCount": n, "total": n }
 *
 * Abweichungen zum frueheren Frontend-Wunschdenken:
 * - Pagination-Parameter heisst `per_page` (NICHT `page_size`)
 * - Es gibt KEINE `items`/`has_more`/`page`-Felder in der Antwort
 * - `priority`/`type`-Filter existieren auf GET /notifications/ NICHT
 *   (nur unter /notifications/system) -> Prioritaets-Tabs filtern clientseitig
 * - Eintraege nutzen camelCase-Legacy-Felder (isRead/createdAt/actionUrl)
 *   und enthalten weder priority noch snoozed_until noch group_key
 *
 * Dieses Modul normalisiert die Backend-Antwort defensiv in das
 * Frontend-Schema. Ein unerwarteter Response darf NIE die App crashen.
 */

import { apiClient } from '@/lib/api';
import type {
  Notification,
  NotificationsResponse,
  NotificationSettings,
  NotificationSettingsUpdate,
  NotificationFilter,
  BulkDismissPayload
} from '../types';
import { NotificationPriority } from '../types';

const BASE_PATH = '/notifications';

const KNOWN_PRIORITIES: ReadonlySet<string> = new Set(
  Object.values(NotificationPriority)
);

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/**
 * Normalisiert einen rohen Backend-Eintrag (camelCase-Legacy-Felder) in das
 * Frontend-Notification-Schema.
 *
 * Gibt `null` zurueck, wenn der Eintrag unbrauchbar ist (kein Objekt /
 * keine id) - solche Eintraege werden verworfen statt die UI zu crashen.
 */
export function normalizeNotification(raw: unknown): Notification | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }
  const r = raw as Record<string, unknown>;

  const id = asString(r.id);
  if (!id) {
    return null;
  }

  const priorityRaw = asString(r.priority);
  const priority = (
    priorityRaw && KNOWN_PRIORITIES.has(priorityRaw)
      ? priorityRaw
      : NotificationPriority.INFO
  ) as Notification['priority'];

  return {
    id,
    // Unbekannte Backend-Typen (z.B. "document_shared") laufen in der UI
    // auf das Default-Icon - bewusst nicht hart auf das Enum gefiltert.
    type: (asString(r.type) ?? 'system') as Notification['type'],
    title: asString(r.title) ?? '',
    message: asString(r.message) ?? '',
    priority,
    read: typeof r.read === 'boolean' ? r.read : Boolean(r.isRead),
    created_at: asString(r.created_at) ?? asString(r.createdAt) ?? '',
    link: asString(r.link) ?? asString(r.actionUrl),
    snoozed_until: asString(r.snoozed_until),
    group_key: asString(r.group_key)
  };
}

/**
 * Benachrichtigungen abrufen (mit Pagination und Filter).
 *
 * Sendet den echten Backend-Vertrag (`page`/`per_page`/`unread_only`) und
 * normalisiert `{notifications, unreadCount, total}` in das Frontend-Schema
 * (`{items, total, page, page_size, has_more}`).
 */
export async function getNotifications(params: {
  page?: number;
  page_size?: number;
  filter?: NotificationFilter;
}): Promise<NotificationsResponse> {
  const { page = 1, page_size = 20, filter } = params;

  const queryParams = new URLSearchParams({
    page: page.toString(),
    per_page: page_size.toString()
  });

  if (filter?.unread_only) {
    queryParams.append('unread_only', 'true');
  }
  // HINWEIS: priority/type werden von GET /notifications/ NICHT unterstuetzt
  // und deshalb bewusst nicht gesendet - die Prioritaets-Tabs filtern
  // clientseitig (siehe NotificationCenter).

  const response = await apiClient.get<unknown>(`${BASE_PATH}?${queryParams}`);
  const body = (response.data ?? {}) as Record<string, unknown>;

  const rawItems = Array.isArray(body.notifications)
    ? body.notifications
    : Array.isArray(body.items) // tolerant gegenueber kuenftigem items-Vertrag
      ? body.items
      : [];

  const items = rawItems
    .map(normalizeNotification)
    .filter((n): n is Notification => n !== null);

  const total = typeof body.total === 'number' ? body.total : items.length;

  return {
    items,
    total,
    page,
    page_size,
    has_more: page * page_size < total
  };
}

/**
 * Einzelne Benachrichtigung abrufen.
 *
 * BEFUND (B5): GET /notifications/{id} existiert im Backend NICHT
 * (nur GET /notifications/system/{id} fuer das System-Modell). Der
 * zugehoerige Hook `useNotification` wird aktuell nirgends verwendet;
 * Aufrufe wuerden mit 404 fehlschlagen.
 */
export async function getNotificationById(id: string): Promise<Notification> {
  const response = await apiClient.get<unknown>(`${BASE_PATH}/${id}`);
  const normalized = normalizeNotification(response.data);
  if (!normalized) {
    throw new Error('Unerwartete Antwort des Servers');
  }
  return normalized;
}

/**
 * Benachrichtigung als gelesen markieren
 */
export async function markAsRead(id: string): Promise<Notification> {
  const response = await apiClient.patch<unknown>(`${BASE_PATH}/${id}/read`);
  const normalized = normalizeNotification(response.data);
  if (!normalized) {
    throw new Error('Unerwartete Antwort beim Markieren als gelesen');
  }
  return normalized;
}

/**
 * Alle Benachrichtigungen als gelesen markieren.
 *
 * Echter Vertrag: POST /notifications/mark-all-read -> { message, success }
 * (es gibt KEIN count-Feld).
 */
export async function markAllAsRead(): Promise<{ success: boolean }> {
  const response = await apiClient.post<{ success?: boolean }>(
    `${BASE_PATH}/mark-all-read`
  );
  return { success: response.data?.success === true };
}

/**
 * Benachrichtigung löschen
 */
export async function deleteNotification(id: string): Promise<void> {
  await apiClient.delete(`${BASE_PATH}/${id}`);
}

/**
 * Mehrere Benachrichtigungen löschen.
 *
 * Echter Vertrag: Fuer User-Benachrichtigungen existiert KEIN Bulk-Endpoint
 * (POST /notifications/bulk-dismiss -> 405; /notifications/system/bulk-dismiss
 * gehoert zum anderen, systemseitigen Notification-Modell). Daher werden
 * einzelne DELETE /notifications/{id} Aufrufe parallel abgesetzt.
 */
export async function bulkDismiss(
  payload: BulkDismissPayload
): Promise<{ count: number }> {
  const results = await Promise.allSettled(
    payload.notification_ids.map((id) => deleteNotification(id))
  );
  const count = results.filter((r) => r.status === 'fulfilled').length;
  if (count === 0 && payload.notification_ids.length > 0) {
    throw new Error('Benachrichtigungen konnten nicht gelöscht werden');
  }
  return { count };
}

/**
 * Anzahl ungelesener Benachrichtigungen abrufen.
 *
 * Echter Vertrag: GET /notifications/unread-count
 * -> { unreadCount, systemCount, userCount } (es gibt KEIN count-Feld).
 */
export async function getUnreadCount(): Promise<number> {
  const response = await apiClient.get<Record<string, unknown>>(
    `${BASE_PATH}/unread-count`
  );
  const data = response.data ?? {};
  if (typeof data.unreadCount === 'number') {
    return data.unreadCount;
  }
  if (typeof data.count === 'number') {
    return data.count;
  }
  return 0;
}

/**
 * Benachrichtigung snoozen.
 *
 * BEFUND (B5): PATCH /notifications/{id}/snooze persistiert snoozed_until,
 * aber die Listen-Antwort von GET /notifications/ liefert das Feld nicht
 * zurueck - der clientseitige Snooze-Filter greift erst, wenn das Backend
 * snoozed_until im Listen-Response ergaenzt.
 */
export async function snoozeNotification(
  id: string,
  until: string
): Promise<Notification> {
  const response = await apiClient.patch<unknown>(
    `${BASE_PATH}/${id}/snooze`,
    { snoozed_until: until }
  );
  const normalized = normalizeNotification(response.data);
  if (!normalized) {
    throw new Error('Unerwartete Antwort beim Zurückstellen');
  }
  return normalized;
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
