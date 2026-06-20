/**
 * Slack Integration API.
 *
 * API-Funktionen für die Slack-Integration.
 */

import { apiClient } from '@/lib/api/client';
import type { SlackChannel, SlackChannelCreate, SlackChannelUpdate, SlackChannelListResponse, SlackMessageListResponse, SlackUserMapping, SlackUserMappingCreate, SlackConnectionStatus, SlackStatistics, SlackTestMessageRequest, SlackTestMessageResponse, SlackNotificationTypeInfo } from '../types';

const BASE_URL = '/slack';

// =============================================================================
// CONNECTION & STATUS
// =============================================================================

/**
 * Prüft den Verbindungs-Status der Slack-Integration.
 */
export async function getSlackStatus(): Promise<SlackConnectionStatus> {
    const response = await apiClient.get<SlackConnectionStatus>(`${BASE_URL}/status`);
    return response.data;
}

/**
 * Ruft Slack-Statistiken ab.
 */
export async function getSlackStatistics(): Promise<SlackStatistics> {
    const response = await apiClient.get<SlackStatistics>(`${BASE_URL}/statistics`);
    return response.data;
}

// =============================================================================
// CHANNELS
// =============================================================================

/**
 * Listet alle Slack-Kanäle auf.
 */
export async function listSlackChannels(params?: {
    company_id?: string;
    active_only?: boolean;
}): Promise<SlackChannelListResponse> {
    const response = await apiClient.get<SlackChannelListResponse>(`${BASE_URL}/channels`, {
        params,
    });
    return response.data;
}

/**
 * Ruft einen einzelnen Slack-Kanal ab.
 */
export async function getSlackChannel(channelId: string): Promise<SlackChannel> {
    const response = await apiClient.get<SlackChannel>(`${BASE_URL}/channels/${channelId}`);
    return response.data;
}

/**
 * Erstellt einen neuen Slack-Kanal.
 */
export async function createSlackChannel(data: SlackChannelCreate): Promise<SlackChannel> {
    const response = await apiClient.post<SlackChannel>(`${BASE_URL}/channels`, data);
    return response.data;
}

/**
 * Aktualisiert einen Slack-Kanal.
 */
export async function updateSlackChannel(
    channelId: string,
    data: SlackChannelUpdate
): Promise<SlackChannel> {
    const response = await apiClient.patch<SlackChannel>(
        `${BASE_URL}/channels/${channelId}`,
        data
    );
    return response.data;
}

/**
 * Löscht einen Slack-Kanal.
 */
export async function deleteSlackChannel(channelId: string): Promise<void> {
    await apiClient.delete(`${BASE_URL}/channels/${channelId}`);
}

// =============================================================================
// MESSAGES
// =============================================================================

/**
 * Listet Slack-Nachrichten-Logs auf.
 */
export async function listSlackMessages(params?: {
    channel_id?: string;
    notification_type?: string;
    status?: string;
    limit?: number;
    offset?: number;
}): Promise<SlackMessageListResponse> {
    const response = await apiClient.get<SlackMessageListResponse>(`${BASE_URL}/messages`, {
        params,
    });
    return response.data;
}

/**
 * Sendet eine Test-Nachricht.
 */
export async function sendTestMessage(
    data: SlackTestMessageRequest
): Promise<SlackTestMessageResponse> {
    const response = await apiClient.post<SlackTestMessageResponse>(`${BASE_URL}/test`, data);
    return response.data;
}

// =============================================================================
// USER MAPPINGS
// =============================================================================

/**
 * Ruft das eigene Slack-Mapping ab.
 */
export async function getMySlackMapping(): Promise<SlackUserMapping | null> {
    try {
        const response = await apiClient.get<SlackUserMapping | null>(`${BASE_URL}/user-mapping`);
        return response.data;
    } catch (error) {
        // 404 bedeutet kein Mapping vorhanden
        return null;
    }
}

/**
 * Erstellt ein Slack-Mapping für den aktuellen Benutzer.
 */
export async function createMySlackMapping(
    data: SlackUserMappingCreate
): Promise<SlackUserMapping> {
    const response = await apiClient.post<SlackUserMapping>(`${BASE_URL}/user-mapping`, data);
    return response.data;
}

/**
 * Löscht das eigene Slack-Mapping.
 */
export async function deleteMySlackMapping(): Promise<void> {
    await apiClient.delete(`${BASE_URL}/user-mapping`);
}

/**
 * Listet alle User-Mappings auf (Admin).
 */
export async function listAllUserMappings(): Promise<SlackUserMapping[]> {
    const response = await apiClient.get<SlackUserMapping[]>(`${BASE_URL}/user-mappings`);
    return response.data;
}

// =============================================================================
// NOTIFICATION TYPES
// =============================================================================

/**
 * Ruft alle verfügbaren Notification-Typen ab.
 */
export async function getNotificationTypes(): Promise<SlackNotificationTypeInfo[]> {
    const response = await apiClient.get<SlackNotificationTypeInfo[]>(
        `${BASE_URL}/notification-types`
    );
    return response.data;
}
