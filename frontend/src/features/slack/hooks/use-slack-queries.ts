/**
 * Slack Integration React Query Hooks.
 *
 * TanStack Query Hooks für die Slack-Integration.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import * as slackApi from '../api/slack-api';
import type {
    SlackChannelCreate,
    SlackChannelUpdate,
    SlackUserMappingCreate,
    SlackTestMessageRequest,
} from '../types';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const slackKeys = {
    all: ['slack'] as const,
    status: () => [...slackKeys.all, 'status'] as const,
    statistics: () => [...slackKeys.all, 'statistics'] as const,
    channels: () => [...slackKeys.all, 'channels'] as const,
    channelsList: (params?: { company_id?: string; active_only?: boolean }) =>
        [...slackKeys.channels(), 'list', params] as const,
    channel: (id: string) => [...slackKeys.channels(), 'detail', id] as const,
    messages: () => [...slackKeys.all, 'messages'] as const,
    messagesList: (params?: {
        channel_id?: string;
        notification_type?: string;
        status?: string;
        limit?: number;
        offset?: number;
    }) => [...slackKeys.messages(), 'list', params] as const,
    userMapping: () => [...slackKeys.all, 'user-mapping'] as const,
    userMappings: () => [...slackKeys.all, 'user-mappings'] as const,
    notificationTypes: () => [...slackKeys.all, 'notification-types'] as const,
};

// =============================================================================
// STATUS & STATISTICS HOOKS
// =============================================================================

/**
 * Hook für Slack-Verbindungsstatus.
 */
export function useSlackStatus() {
    return useQuery({
        queryKey: slackKeys.status(),
        queryFn: slackApi.getSlackStatus,
        staleTime: 30 * 1000, // 30 Sekunden
        refetchOnWindowFocus: false,
    });
}

/**
 * Hook für Slack-Statistiken.
 */
export function useSlackStatistics() {
    return useQuery({
        queryKey: slackKeys.statistics(),
        queryFn: slackApi.getSlackStatistics,
        staleTime: 60 * 1000, // 1 Minute
    });
}

// =============================================================================
// CHANNEL HOOKS
// =============================================================================

/**
 * Hook für Slack-Kanal-Liste.
 */
export function useSlackChannels(params?: { company_id?: string; active_only?: boolean }) {
    return useQuery({
        queryKey: slackKeys.channelsList(params),
        queryFn: () => slackApi.listSlackChannels(params),
        staleTime: 30 * 1000,
    });
}

/**
 * Hook für einzelnen Slack-Kanal.
 */
export function useSlackChannel(channelId: string) {
    return useQuery({
        queryKey: slackKeys.channel(channelId),
        queryFn: () => slackApi.getSlackChannel(channelId),
        enabled: !!channelId,
    });
}

/**
 * Hook für Kanal-Erstellung.
 */
export function useCreateSlackChannel() {
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: (data: SlackChannelCreate) => slackApi.createSlackChannel(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: slackKeys.channels() });
            toast({
                title: 'Kanal hinzugefügt',
                description: 'Der Slack-Kanal wurde erfolgreich konfiguriert.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Kanal konnte nicht hinzugefügt werden.',
                variant: 'destructive',
            });
        },
    });
}

/**
 * Hook für Kanal-Update.
 */
export function useUpdateSlackChannel() {
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: ({ channelId, data }: { channelId: string; data: SlackChannelUpdate }) =>
            slackApi.updateSlackChannel(channelId, data),
        onSuccess: (_, { channelId }) => {
            queryClient.invalidateQueries({ queryKey: slackKeys.channels() });
            queryClient.invalidateQueries({ queryKey: slackKeys.channel(channelId) });
            toast({
                title: 'Gespeichert',
                description: 'Die Kanal-Konfiguration wurde aktualisiert.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Kanal konnte nicht aktualisiert werden.',
                variant: 'destructive',
            });
        },
    });
}

/**
 * Hook für Kanal-Löschung.
 */
export function useDeleteSlackChannel() {
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: (channelId: string) => slackApi.deleteSlackChannel(channelId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: slackKeys.channels() });
            toast({
                title: 'Gelöscht',
                description: 'Der Slack-Kanal wurde entfernt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Kanal konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        },
    });
}

// =============================================================================
// MESSAGE HOOKS
// =============================================================================

/**
 * Hook für Nachrichten-Liste.
 */
export function useSlackMessages(params?: {
    channel_id?: string;
    notification_type?: string;
    status?: string;
    limit?: number;
    offset?: number;
}) {
    return useQuery({
        queryKey: slackKeys.messagesList(params),
        queryFn: () => slackApi.listSlackMessages(params),
        staleTime: 30 * 1000,
    });
}

/**
 * Hook für Test-Nachricht.
 */
export function useSendTestMessage() {
    const { toast } = useToast();

    return useMutation({
        mutationFn: (data: SlackTestMessageRequest) => slackApi.sendTestMessage(data),
        onSuccess: (result) => {
            if (result.success) {
                toast({
                    title: 'Test erfolgreich',
                    description: 'Die Test-Nachricht wurde an Slack gesendet.',
                });
            } else {
                toast({
                    title: 'Test fehlgeschlagen',
                    description: result.error || 'Nachricht konnte nicht gesendet werden.',
                    variant: 'destructive',
                });
            }
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Test-Nachricht konnte nicht gesendet werden.',
                variant: 'destructive',
            });
        },
    });
}

// =============================================================================
// USER MAPPING HOOKS
// =============================================================================

/**
 * Hook für eigenes User-Mapping.
 */
export function useMySlackMapping() {
    return useQuery({
        queryKey: slackKeys.userMapping(),
        queryFn: slackApi.getMySlackMapping,
        staleTime: 60 * 1000,
    });
}

/**
 * Hook für User-Mapping Erstellung.
 */
export function useCreateMySlackMapping() {
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: (data: SlackUserMappingCreate) => slackApi.createMySlackMapping(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: slackKeys.userMapping() });
            toast({
                title: 'Verknüpft',
                description: 'Ihr Slack-Account wurde erfolgreich verknüpft.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Verknüpfung konnte nicht erstellt werden.',
                variant: 'destructive',
            });
        },
    });
}

/**
 * Hook für User-Mapping Löschung.
 */
export function useDeleteMySlackMapping() {
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: () => slackApi.deleteMySlackMapping(),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: slackKeys.userMapping() });
            toast({
                title: 'Entfernt',
                description: 'Die Slack-Verknüpfung wurde aufgehoben.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Verknüpfung konnte nicht entfernt werden.',
                variant: 'destructive',
            });
        },
    });
}

/**
 * Hook für alle User-Mappings (Admin).
 */
export function useAllSlackUserMappings() {
    return useQuery({
        queryKey: slackKeys.userMappings(),
        queryFn: slackApi.listAllUserMappings,
        staleTime: 60 * 1000,
    });
}

// =============================================================================
// NOTIFICATION TYPE HOOKS
// =============================================================================

/**
 * Hook für Notification-Typen.
 */
export function useSlackNotificationTypes() {
    return useQuery({
        queryKey: slackKeys.notificationTypes(),
        queryFn: slackApi.getNotificationTypes,
        staleTime: 5 * 60 * 1000, // 5 Minuten
    });
}
