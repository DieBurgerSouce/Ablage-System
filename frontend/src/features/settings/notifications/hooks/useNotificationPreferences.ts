/**
 * useNotificationPreferences Hook
 *
 * Aggregierter Hook fuer Benachrichtigungs-Praeferenzen.
 * Kombiniert alle relevanten Queries und Mutations.
 */

import { useMemo } from 'react';
import {
  useNotificationPreferences as usePreferences,
  useChannelStatus,
  useEscalationChain,
  useUpdateNotificationPreferences,
  useUpdateSeverityMatrix,
  useUpdateQuietHours,
  useTestNotification,
  useToggleChannel,
} from '../hooks';
import type {
  NotificationChannel,
  NotificationCategory,
  NotificationPreferences,
  ChannelConfig,
  EscalationStep,
  QuietHoursConfig,
} from '../types';

interface NotificationTypeConfig {
  category: NotificationCategory;
  enabled: boolean;
  channels: NotificationChannel[];
  description: string;
}

interface UseNotificationPreferencesReturn {
  // Data
  preferences: NotificationPreferences | undefined;
  channelStatus: ChannelConfig[];
  escalationChain: EscalationStep[];
  notificationTypes: NotificationTypeConfig[];

  // Loading states
  isLoading: boolean;
  isUpdating: boolean;

  // Actions
  toggleGlobal: (enabled: boolean) => void;
  toggleChannel: (channel: NotificationChannel, enabled: boolean) => void;
  updateChannelPriority: (channels: NotificationChannel[]) => void;
  updateNotificationType: (
    category: NotificationCategory,
    enabled: boolean,
    channels: NotificationChannel[]
  ) => void;
  updateQuietHours: (config: Partial<QuietHoursConfig>) => void;
  sendTestNotification: (channel: NotificationChannel) => void;

  // Computed
  enabledChannels: NotificationChannel[];
  configuredChannels: NotificationChannel[];
  availableChannels: NotificationChannel[];
}

const CATEGORY_DESCRIPTIONS: Record<NotificationCategory, string> = {
  document: 'Dokumente und OCR',
  alert: 'Warnungen und Hinweise',
  workflow: 'Workflows und Aufgaben',
  system: 'Systemmeldungen',
  security: 'Sicherheit',
  finance: 'Finanzen',
  compliance: 'Compliance',
  reminder: 'Erinnerungen',
};

const ALL_CATEGORIES: NotificationCategory[] = [
  'document',
  'alert',
  'workflow',
  'system',
  'security',
  'finance',
  'compliance',
  'reminder',
];

export function useNotificationPreferencesHook(): UseNotificationPreferencesReturn {
  // Queries
  const { data: preferencesData, isLoading: prefsLoading } = usePreferences();
  const { data: channelStatus, isLoading: channelsLoading } = useChannelStatus();
  const { data: escalationChain, isLoading: escalationLoading } = useEscalationChain();

  // Mutations
  const updatePreferences = useUpdateNotificationPreferences();
  const updateSeverity = useUpdateSeverityMatrix();
  const updateQuietHoursMutation = useUpdateQuietHours();
  const toggleChannelMutation = useToggleChannel();
  const testNotificationMutation = useTestNotification();

  // Extract preferences from response
  const preferences = useMemo(() => {
    if (!preferencesData) return undefined;
    // Handle both response formats
    return 'preferences' in preferencesData
      ? preferencesData.preferences
      : preferencesData;
  }, [preferencesData]);

  // Compute notification type configs
  const notificationTypes = useMemo((): NotificationTypeConfig[] => {
    if (!preferences) return [];

    return ALL_CATEGORIES.map((category) => {
      // Determine enabled state based on category-specific settings
      const channels: NotificationChannel[] = [];

      if (preferences.emailCategories?.includes(category)) channels.push('email');
      if (preferences.pushCategories?.includes(category)) channels.push('push');
      if (preferences.smsCategories?.includes(category)) channels.push('sms');

      // Default enabled if any channel is configured for this category
      const enabled = channels.length > 0;

      return {
        category,
        enabled,
        channels,
        description: CATEGORY_DESCRIPTIONS[category],
      };
    });
  }, [preferences]);

  // Compute enabled and configured channels
  const enabledChannels = useMemo(
    () => (channelStatus ?? []).filter((c) => c.enabled).map((c) => c.channel),
    [channelStatus]
  );

  const configuredChannels = useMemo(
    () => (channelStatus ?? []).filter((c) => c.configured).map((c) => c.channel),
    [channelStatus]
  );

  const availableChannels = useMemo(
    () => (channelStatus ?? []).filter((c) => c.configured && c.enabled).map((c) => c.channel),
    [channelStatus]
  );

  // Loading state
  const isLoading = prefsLoading || channelsLoading || escalationLoading;
  const isUpdating =
    updatePreferences.isPending ||
    updateSeverity.isPending ||
    updateQuietHoursMutation.isPending ||
    toggleChannelMutation.isPending;

  // Actions
  const toggleGlobal = (enabled: boolean) => {
    updatePreferences.mutate({ enabled });
  };

  const toggleChannel = (channel: NotificationChannel, enabled: boolean) => {
    toggleChannelMutation.mutate({ channel, enabled });
  };

  const updateChannelPriority = (_channels: NotificationChannel[]) => {
    // This would call a backend endpoint to update channel priority order
    // For now, we'll just log it since the backend may not support this yet
    console.log('Channel priority update:', _channels);
  };

  const updateNotificationType = (
    category: NotificationCategory,
    enabled: boolean,
    channels: NotificationChannel[]
  ) => {
    // Build update request based on category
    const emailCategories = preferences?.emailCategories?.filter((c) => c !== category) ?? [];
    const pushCategories = preferences?.pushCategories?.filter((c) => c !== category) ?? [];
    const smsCategories = preferences?.smsCategories?.filter((c) => c !== category) ?? [];

    if (enabled) {
      if (channels.includes('email')) emailCategories.push(category);
      if (channels.includes('push')) pushCategories.push(category);
      if (channels.includes('sms')) smsCategories.push(category);
    }

    updatePreferences.mutate({
      emailCategories,
      pushCategories,
      smsCategories,
    });
  };

  const updateQuietHours = (config: Partial<QuietHoursConfig>) => {
    updateQuietHoursMutation.mutate(config);
  };

  const sendTestNotification = (channel: NotificationChannel) => {
    testNotificationMutation.mutate({ channel });
  };

  return {
    // Data
    preferences,
    channelStatus: channelStatus ?? [],
    escalationChain: escalationChain ?? [],
    notificationTypes,

    // Loading states
    isLoading,
    isUpdating,

    // Actions
    toggleGlobal,
    toggleChannel,
    updateChannelPriority,
    updateNotificationType,
    updateQuietHours,
    sendTestNotification,

    // Computed
    enabledChannels,
    configuredChannels,
    availableChannels,
  };
}

export default useNotificationPreferencesHook;
