/**
 * Notification Preferences Hooks
 *
 * TanStack Query Hooks fuer Benachrichtigungs-Praeferenzen.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/hooks/use-toast';
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  updateSeverityMatrix,
  updateQuietHours,
  sendTestNotification,
  toggleChannel,
  getChannelStatus,
  getEscalationChain,
} from './api';
import type {
  UpdateNotificationPreferencesRequest,
  UpdateSeverityMatrixRequest,
  TestNotificationRequest,
  QuietHoursConfig,
  NotificationChannel,
} from './types';

// Query Keys
export const notificationPreferencesKeys = {
  all: ['notification-preferences'] as const,
  preferences: () => [...notificationPreferencesKeys.all, 'preferences'] as const,
  channels: () => [...notificationPreferencesKeys.all, 'channels'] as const,
  escalation: () => [...notificationPreferencesKeys.all, 'escalation'] as const,
};

/**
 * Hook fuer Benachrichtigungs-Praeferenzen.
 */
export function useNotificationPreferences() {
  return useQuery({
    queryKey: notificationPreferencesKeys.preferences(),
    queryFn: getNotificationPreferences,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook fuer Kanal-Status.
 */
export function useChannelStatus() {
  return useQuery({
    queryKey: notificationPreferencesKeys.channels(),
    queryFn: getChannelStatus,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook fuer Eskalationskette.
 */
export function useEscalationChain() {
  return useQuery({
    queryKey: notificationPreferencesKeys.escalation(),
    queryFn: getEscalationChain,
    staleTime: 10 * 60 * 1000, // 10 Minuten
  });
}

/**
 * Hook zum Aktualisieren der Praeferenzen.
 */
export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UpdateNotificationPreferencesRequest) =>
      updateNotificationPreferences(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationPreferencesKeys.all });
      toast({
        title: 'Einstellungen gespeichert',
        description: 'Ihre Benachrichtigungs-Einstellungen wurden aktualisiert.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Einstellungen konnten nicht gespeichert werden.',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Aktualisieren der Schweregrad-Matrix.
 */
export function useUpdateSeverityMatrix() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UpdateSeverityMatrixRequest) => updateSeverityMatrix(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationPreferencesKeys.preferences() });
      toast({
        title: 'Matrix aktualisiert',
        description: 'Schweregrad-Kanal-Zuordnung wurde gespeichert.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Matrix konnte nicht aktualisiert werden.',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Aktualisieren der Ruhezeiten.
 */
export function useUpdateQuietHours() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: Partial<QuietHoursConfig>) => updateQuietHours(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationPreferencesKeys.preferences() });
      toast({
        title: 'Ruhezeiten gespeichert',
        description: 'Ihre Ruhezeiten-Konfiguration wurde aktualisiert.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Ruhezeiten konnten nicht gespeichert werden.',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook fuer Test-Benachrichtigungen.
 */
export function useTestNotification() {
  return useMutation({
    mutationFn: (request: TestNotificationRequest) => sendTestNotification(request),
    onSuccess: (data) => {
      if (data.success) {
        toast({
          title: 'Test gesendet',
          description: data.message,
        });
      } else {
        toast({
          title: 'Test fehlgeschlagen',
          description: data.errorMessage || 'Benachrichtigung konnte nicht gesendet werden.',
          variant: 'destructive',
        });
      }
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Test-Benachrichtigung fehlgeschlagen.',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Aktivieren/Deaktivieren eines Kanals.
 */
export function useToggleChannel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ channel, enabled }: { channel: NotificationChannel; enabled: boolean }) =>
      toggleChannel(channel, enabled),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: notificationPreferencesKeys.all });
      toast({
        title: variables.enabled ? 'Kanal aktiviert' : 'Kanal deaktiviert',
        description: variables.enabled
          ? 'Der Benachrichtigungskanal wurde aktiviert.'
          : 'Der Benachrichtigungskanal wurde deaktiviert.',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Kanal-Status konnte nicht geaendert werden.',
        variant: 'destructive',
      });
    },
  });
}
