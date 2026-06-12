/**
 * Teams React Query Hooks
 *
 * TanStack Query Hooks für Team-Verwaltung, Mitglieder, Einladungen und Aktivitäten.
 */

import { useMutation, useQuery, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { teamsApi, type TeamCreateRequest, type TeamUpdateRequest, type TeamListParams, type MemberAddRequest, type MemberUpdateRequest, type InvitationCreateRequest, type DocumentShareRequest, type ActivityListParams, type TeamDocumentPermission } from '../api/teams-api';

// ==================== Query Keys ====================

export const teamKeys = {
  all: ['teams'] as const,
  lists: () => [...teamKeys.all, 'list'] as const,
  list: (params?: TeamListParams) => [...teamKeys.lists(), params] as const,
  details: () => [...teamKeys.all, 'detail'] as const,
  detail: (id: string) => [...teamKeys.details(), id] as const,
  members: (teamId: string) => [...teamKeys.detail(teamId), 'members'] as const,
  invitations: (teamId: string) => [...teamKeys.detail(teamId), 'invitations'] as const,
  activity: (teamId: string) => [...teamKeys.detail(teamId), 'activity'] as const,
  documents: (teamId: string) => [...teamKeys.detail(teamId), 'documents'] as const,
};

// ==================== Team Queries ====================

/**
 * Teams auflisten
 */
export function useTeams(params?: TeamListParams) {
  return useQuery({
    queryKey: teamKeys.list(params),
    queryFn: () => teamsApi.listTeams(params),
  });
}

/**
 * Teams mit Infinite Scroll
 */
export function useTeamsInfinite(params?: Omit<TeamListParams, 'page'>) {
  return useInfiniteQuery({
    queryKey: teamKeys.list(params),
    queryFn: ({ pageParam = 1 }) =>
      teamsApi.listTeams({ ...params, page: pageParam, page_size: params?.page_size ?? 20 }),
    getNextPageParam: (lastPage) => {
      const nextPage = lastPage.page + 1;
      const totalPages = Math.ceil(lastPage.total / (params?.page_size ?? 20));
      return nextPage <= totalPages ? nextPage : undefined;
    },
    initialPageParam: 1,
  });
}

/**
 * Einzelnes Team laden
 */
export function useTeam(teamId: string) {
  return useQuery({
    queryKey: teamKeys.detail(teamId),
    queryFn: () => teamsApi.getTeam(teamId),
    enabled: !!teamId,
  });
}

// ==================== Team Mutations ====================

/**
 * Team erstellen
 */
export function useCreateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TeamCreateRequest) => teamsApi.createTeam(data),
    onSuccess: (team) => {
      queryClient.invalidateQueries({ queryKey: teamKeys.lists() });
      toast.success(`Team "${team.name}" wurde erstellt`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Team aktualisieren
 */
export function useUpdateTeam(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TeamUpdateRequest) => teamsApi.updateTeam(teamId, data),
    onSuccess: (team) => {
      queryClient.invalidateQueries({ queryKey: teamKeys.lists() });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      toast.success(`Team "${team.name}" wurde aktualisiert`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Team löschen
 */
export function useDeleteTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (teamId: string) => teamsApi.deleteTeam(teamId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.lists() });
      toast.success('Team wurde gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Team archivieren
 */
export function useArchiveTeam(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => teamsApi.archiveTeam(teamId),
    onSuccess: (team) => {
      queryClient.invalidateQueries({ queryKey: teamKeys.lists() });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      toast.success(`Team "${team.name}" wurde archiviert`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Archivieren: ${error.message}`);
    },
  });
}

// ==================== Member Queries & Mutations ====================

/**
 * Team-Mitglieder laden
 */
export function useTeamMembers(teamId: string) {
  return useQuery({
    queryKey: teamKeys.members(teamId),
    queryFn: () => teamsApi.listMembers(teamId),
    enabled: !!teamId,
  });
}

/**
 * Mitglied hinzufügen
 */
export function useAddMember(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: MemberAddRequest) => teamsApi.addMember(teamId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success('Mitglied wurde hinzugefügt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Mitglied-Rolle aktualisieren
 */
export function useUpdateMemberRole(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: MemberUpdateRequest }) =>
      teamsApi.updateMemberRole(teamId, userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success('Rolle wurde aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Mitglied entfernen
 */
export function useRemoveMember(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => teamsApi.removeMember(teamId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success('Mitglied wurde entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Invitation Queries & Mutations ====================

/**
 * Team-Einladungen laden
 */
export function useTeamInvitations(teamId: string) {
  return useQuery({
    queryKey: teamKeys.invitations(teamId),
    queryFn: () => teamsApi.listInvitations(teamId),
    enabled: !!teamId,
  });
}

/**
 * Einladung senden
 */
export function useSendInvitation(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: InvitationCreateRequest) => teamsApi.sendInvitation(teamId, data),
    onSuccess: (invitation) => {
      queryClient.invalidateQueries({ queryKey: teamKeys.invitations(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success(`Einladung an ${invitation.email} wurde gesendet`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Einladung widerrufen
 */
export function useRevokeInvitation(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invitationId: string) => teamsApi.revokeInvitation(teamId, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.invitations(teamId) });
      toast.success('Einladung wurde widerrufen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Einladung annehmen
 */
export function useAcceptInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (token: string) => teamsApi.acceptInvitation(token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.lists() });
      toast.success('Einladung wurde angenommen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Einladung ablehnen
 */
export function useDeclineInvitation() {
  return useMutation({
    mutationFn: (token: string) => teamsApi.declineInvitation(token),
    onSuccess: () => {
      toast.success('Einladung wurde abgelehnt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Activity Queries ====================

/**
 * Team-Aktivitäten laden
 */
export function useTeamActivity(teamId: string, params?: ActivityListParams) {
  return useQuery({
    queryKey: [...teamKeys.activity(teamId), params],
    queryFn: () => teamsApi.listActivity(teamId, params),
    enabled: !!teamId,
  });
}

/**
 * Team-Aktivitäten mit Infinite Scroll
 */
export function useTeamActivityInfinite(teamId: string, params?: Omit<ActivityListParams, 'page'>) {
  return useInfiniteQuery({
    queryKey: [...teamKeys.activity(teamId), params],
    queryFn: ({ pageParam = 1 }) =>
      teamsApi.listActivity(teamId, { ...params, page: pageParam, page_size: params?.page_size ?? 20 }),
    getNextPageParam: (lastPage) => {
      const nextPage = lastPage.page + 1;
      const totalPages = Math.ceil(lastPage.total / (params?.page_size ?? 20));
      return nextPage <= totalPages ? nextPage : undefined;
    },
    initialPageParam: 1,
    enabled: !!teamId,
  });
}

// ==================== Document Queries & Mutations ====================

/**
 * Geteilte Dokumente laden
 */
export function useTeamDocuments(teamId: string) {
  return useQuery({
    queryKey: teamKeys.documents(teamId),
    queryFn: () => teamsApi.listDocuments(teamId),
    enabled: !!teamId,
  });
}

/**
 * Dokument mit Team teilen
 */
export function useShareDocument(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: DocumentShareRequest) => teamsApi.shareDocument(teamId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.documents(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success('Dokument wurde geteilt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Dokument-Freigabe aktualisieren
 */
export function useUpdateDocumentShare(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      documentId,
      data,
    }: {
      documentId: string;
      data: { permission?: TeamDocumentPermission; notes?: string };
    }) => teamsApi.updateDocumentShare(teamId, documentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.documents(teamId) });
      toast.success('Freigabe wurde aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Dokument-Freigabe aufheben
 */
export function useUnshareDocument(teamId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (documentId: string) => teamsApi.unshareDocument(teamId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.documents(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.detail(teamId) });
      queryClient.invalidateQueries({ queryKey: teamKeys.activity(teamId) });
      toast.success('Freigabe wurde aufgehoben');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}
