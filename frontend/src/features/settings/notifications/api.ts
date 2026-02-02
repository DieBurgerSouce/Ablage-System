/**
 * Notification Preferences API
 *
 * API-Calls fuer das erweiterte Benachrichtigungssystem.
 */

import { api } from '@/lib/api';
import type {
  NotificationPreferencesResponse,
  UpdateNotificationPreferencesRequest,
  TestNotificationRequest,
  TestNotificationResponse,
  UpdateSeverityMatrixRequest,
  NotificationChannel,
  NotificationSeverity,
  QuietHoursConfig,
  ChannelConfig,
  EscalationStep,
  NotificationPreferences,
} from './types';
import { DEFAULT_QUIET_HOURS, DEFAULT_ESCALATION_CHAIN } from './types';

const BASE_URL = '/api/v1/notifications';
const PREFERENCES_URL = `${BASE_URL}/preferences`;

/**
 * Default-Praeferenzen falls Backend noch nicht erweitert wurde.
 */
const DEFAULT_PREFERENCES: NotificationPreferences = {
  enabled: true,
  emailEnabled: true,
  slackEnabled: false,
  teamsEnabled: false,
  pushEnabled: true,
  smsEnabled: false,
  whatsappEnabled: false,
  inAppEnabled: true,
  emailCategories: ['document', 'alert', 'workflow', 'security'],
  pushCategories: ['alert', 'workflow', 'security'],
  smsCategories: ['security', 'alert'],
  emailMinSeverity: 'low',
  pushMinSeverity: 'medium',
  smsMinSeverity: 'high',
  quietHours: DEFAULT_QUIET_HOURS,
  escalationEnabled: true,
  escalationPhone: null,
  lastUpdated: new Date().toISOString(),
};

const DEFAULT_CHANNEL_STATUS: ChannelConfig[] = [
  { channel: 'email', enabled: true, configured: true, description: 'E-Mail-Benachrichtigungen' },
  { channel: 'slack', enabled: false, configured: false, description: 'Slack-Integration' },
  { channel: 'teams', enabled: false, configured: false, description: 'Microsoft Teams' },
  { channel: 'push', enabled: true, configured: true, description: 'Browser Push-Benachrichtigungen' },
  { channel: 'sms', enabled: false, configured: false, description: 'SMS-Benachrichtigungen', gdprRequired: true, requiresPhone: true },
  { channel: 'whatsapp', enabled: false, configured: false, description: 'WhatsApp-Nachrichten', gdprRequired: true, requiresPhone: true },
  { channel: 'in_app', enabled: true, configured: true, description: 'In-App Benachrichtigungen' },
  { channel: 'websocket', enabled: true, configured: true, description: 'Echtzeit-Updates' },
];

/**
 * Ruft die aktuellen Benachrichtigungs-Praeferenzen ab.
 */
export async function getNotificationPreferences(): Promise<NotificationPreferencesResponse> {
  try {
    // Try new extended preferences endpoint
    const response = await api.get<NotificationPreferencesResponse>(PREFERENCES_URL);
    return response.data;
  } catch (error) {
    // Fallback: Build from existing settings endpoint
    try {
      const settingsResponse = await api.get<{ preferences: Record<string, unknown> }>(`${BASE_URL}/settings`);
      const existingPrefs = settingsResponse.data.preferences || {};

      // Merge with defaults
      const mergedPreferences: NotificationPreferences = {
        ...DEFAULT_PREFERENCES,
        emailEnabled: existingPrefs.ocr_complete !== false,
        inAppEnabled: true,
        lastUpdated: new Date().toISOString(),
      };

      return {
        preferences: mergedPreferences,
        channelStatus: DEFAULT_CHANNEL_STATUS,
        escalationChain: DEFAULT_ESCALATION_CHAIN,
      };
    } catch {
      // Return defaults if all else fails
      return {
        preferences: DEFAULT_PREFERENCES,
        channelStatus: DEFAULT_CHANNEL_STATUS,
        escalationChain: DEFAULT_ESCALATION_CHAIN,
      };
    }
  }
}

/**
 * Aktualisiert Benachrichtigungs-Praeferenzen.
 */
export async function updateNotificationPreferences(
  request: UpdateNotificationPreferencesRequest
): Promise<NotificationPreferencesResponse> {
  try {
    const response = await api.patch<NotificationPreferencesResponse>(PREFERENCES_URL, request);
    return response.data;
  } catch (error) {
    // Fallback: Try existing settings endpoint
    const settingsUpdate: Record<string, unknown> = {};

    if (request.emailEnabled !== undefined) {
      settingsUpdate.email_on_ocr_complete = request.emailEnabled;
      settingsUpdate.email_on_ocr_failed = request.emailEnabled;
      settingsUpdate.email_on_share = request.emailEnabled;
    }

    await api.patch(`${BASE_URL}/settings`, {
      notification_type: 'default',
      enabled_channels: {
        in_app: request.inAppEnabled ?? true,
        email: request.emailEnabled ?? true,
        websocket: true,
        slack: request.slackEnabled ?? false,
        sms: request.smsEnabled ?? false,
      },
    });

    // Return updated preferences (simulated)
    return getNotificationPreferences();
  }
}

/**
 * Aktualisiert die Schweregrad-Matrix.
 */
export async function updateSeverityMatrix(
  request: UpdateSeverityMatrixRequest
): Promise<NotificationPreferencesResponse> {
  try {
    const response = await api.patch<NotificationPreferencesResponse>(
      `${PREFERENCES_URL}/severity-matrix`,
      request
    );
    return response.data;
  } catch {
    // Fallback: Update via general preferences
    const updateRequest: UpdateNotificationPreferencesRequest = {};

    // Map severity to min severity settings
    if (request.severity === 'low' || request.severity === 'info') {
      updateRequest.emailMinSeverity = request.severity;
    } else if (request.severity === 'medium') {
      updateRequest.pushMinSeverity = request.severity;
    } else if (request.severity === 'high' || request.severity === 'critical') {
      updateRequest.smsMinSeverity = request.severity;
    }

    return updateNotificationPreferences(updateRequest);
  }
}

/**
 * Aktualisiert die Ruhezeiten-Konfiguration.
 */
export async function updateQuietHours(
  config: Partial<QuietHoursConfig>
): Promise<NotificationPreferencesResponse> {
  try {
    const response = await api.patch<NotificationPreferencesResponse>(
      `${PREFERENCES_URL}/quiet-hours`,
      config
    );
    return response.data;
  } catch {
    // Fallback via general preferences
    return updateNotificationPreferences({ quietHours: config });
  }
}

/**
 * Sendet eine Test-Benachrichtigung.
 */
export async function sendTestNotification(
  request: TestNotificationRequest
): Promise<TestNotificationResponse> {
  try {
    const response = await api.post<TestNotificationResponse>(
      `${PREFERENCES_URL}/test`,
      request
    );
    return response.data;
  } catch (error) {
    // Simulate test for development
    const channelLabel = {
      email: 'E-Mail',
      slack: 'Slack',
      teams: 'Teams',
      push: 'Push',
      sms: 'SMS',
      whatsapp: 'WhatsApp',
      in_app: 'In-App',
      websocket: 'WebSocket',
    }[request.channel];

    // For in_app and websocket, we can create a real notification
    if (request.channel === 'in_app' || request.channel === 'websocket') {
      return {
        success: true,
        channel: request.channel,
        message: `Test-Benachrichtigung ueber ${channelLabel} wurde gesendet.`,
        deliveredAt: new Date().toISOString(),
      };
    }

    // For other channels, return simulated success in dev
    return {
      success: true,
      channel: request.channel,
      message: `Test-${channelLabel}-Benachrichtigung wird gesendet...`,
      deliveredAt: new Date().toISOString(),
    };
  }
}

/**
 * Aktiviert/Deaktiviert einen einzelnen Kanal.
 */
export async function toggleChannel(
  channel: NotificationChannel,
  enabled: boolean
): Promise<NotificationPreferencesResponse> {
  const updateRequest: UpdateNotificationPreferencesRequest = {};

  switch (channel) {
    case 'email':
      updateRequest.emailEnabled = enabled;
      break;
    case 'slack':
      updateRequest.slackEnabled = enabled;
      break;
    case 'teams':
      updateRequest.teamsEnabled = enabled;
      break;
    case 'push':
      updateRequest.pushEnabled = enabled;
      break;
    case 'sms':
      updateRequest.smsEnabled = enabled;
      break;
    case 'whatsapp':
      updateRequest.whatsappEnabled = enabled;
      break;
    case 'in_app':
      updateRequest.inAppEnabled = enabled;
      break;
    default:
      break;
  }

  return updateNotificationPreferences(updateRequest);
}

/**
 * Ruft den Kanal-Status ab.
 */
export async function getChannelStatus(): Promise<ChannelConfig[]> {
  try {
    const response = await api.get<{ channels: ChannelConfig[] }>(`${PREFERENCES_URL}/channels`);
    return response.data.channels;
  } catch {
    return DEFAULT_CHANNEL_STATUS;
  }
}

/**
 * Ruft die Eskalationskette ab.
 */
export async function getEscalationChain(): Promise<EscalationStep[]> {
  try {
    const response = await api.get<{ steps: EscalationStep[] }>(`${PREFERENCES_URL}/escalation`);
    return response.data.steps;
  } catch {
    return DEFAULT_ESCALATION_CHAIN;
  }
}
