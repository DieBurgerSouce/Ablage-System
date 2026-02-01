/**
 * Teams API Client
 *
 * API-Client fuer Team-Verwaltung, Mitglieder, Einladungen und Aktivitaeten.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Enums ====================

export type TeamType = 'department' | 'project' | 'working_group' | 'committee' | 'virtual';
export type TeamStatus = 'active' | 'inactive' | 'archived' | 'pending';
export type TeamVisibility = 'public' | 'private' | 'company';
export type TeamMemberRole = 'member' | 'lead' | 'admin' | 'deputy' | 'observer';
export type InvitationStatus = 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked';
export type TeamActivityType =
  | 'member_added'
  | 'member_removed'
  | 'member_role_changed'
  | 'team_created'
  | 'team_updated'
  | 'team_archived'
  | 'document_shared'
  | 'document_unshared'
  | 'invitation_sent'
  | 'invitation_accepted'
  | 'invitation_declined';
export type TeamDocumentPermission = 'view' | 'edit' | 'full';

// ==================== Types ====================

export interface Team {
  id: string;
  name: string;
  description?: string;
  team_type: TeamType;
  status: TeamStatus;
  visibility: TeamVisibility;
  settings: Record<string, unknown>;
  parent_team_id?: string;
  company_id: string;
  created_at: string;
  updated_at?: string;
  created_by_id: string;
  member_count?: number;
  document_count?: number;
}

export interface TeamMember {
  id: string;
  team_id: string;
  user_id: string;
  role: TeamMemberRole;
  joined_at: string;
  invited_by_id?: string;
  // Joined user data
  user?: {
    id: string;
    username: string;
    email: string;
    full_name?: string;
  };
}

export interface TeamActivity {
  id: string;
  team_id: string;
  activity_type: TeamActivityType;
  actor_id: string;
  target_user_id?: string;
  target_document_id?: string;
  details: Record<string, unknown>;
  created_at: string;
  // Joined data
  actor?: {
    id: string;
    username: string;
    full_name?: string;
  };
  target_user?: {
    id: string;
    username: string;
    full_name?: string;
  };
}

export interface TeamInvitation {
  id: string;
  team_id: string;
  email: string;
  role: TeamMemberRole;
  status: InvitationStatus;
  token: string;
  message?: string;
  invited_by_id: string;
  expires_at: string;
  accepted_at?: string;
  declined_at?: string;
  created_at: string;
  // Joined data
  invited_by?: {
    id: string;
    username: string;
    full_name?: string;
  };
}

export interface TeamDocument {
  id: string;
  team_id: string;
  document_id: string;
  permission: TeamDocumentPermission;
  shared_by_id: string;
  shared_at: string;
  notes?: string;
  // Joined data
  document?: {
    id: string;
    title: string;
    document_type?: string;
    created_at: string;
  };
  shared_by?: {
    id: string;
    username: string;
    full_name?: string;
  };
}

// ==================== Request/Response Types ====================

export interface TeamCreateRequest {
  name: string;
  description?: string;
  team_type?: TeamType;
  visibility?: TeamVisibility;
  settings?: Record<string, unknown>;
  parent_team_id?: string;
}

export interface TeamUpdateRequest {
  name?: string;
  description?: string;
  team_type?: TeamType;
  status?: TeamStatus;
  visibility?: TeamVisibility;
  settings?: Record<string, unknown>;
  parent_team_id?: string;
}

export interface TeamListResponse {
  teams: Team[];
  total: number;
  page: number;
  page_size: number;
}

export interface TeamListParams {
  page?: number;
  page_size?: number;
  status?: TeamStatus;
  team_type?: TeamType;
  visibility?: TeamVisibility;
  search?: string;
}

export interface MemberAddRequest {
  user_id: string;
  role?: TeamMemberRole;
}

export interface MemberUpdateRequest {
  role: TeamMemberRole;
}

export interface InvitationCreateRequest {
  email: string;
  role?: TeamMemberRole;
  message?: string;
}

export interface DocumentShareRequest {
  document_id: string;
  permission?: TeamDocumentPermission;
  notes?: string;
}

export interface ActivityListParams {
  page?: number;
  page_size?: number;
  activity_type?: TeamActivityType;
}

export interface ActivityListResponse {
  activities: TeamActivity[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== API Functions ====================

/**
 * Teams auflisten
 */
export async function listTeams(params?: TeamListParams): Promise<TeamListResponse> {
  const response = await apiClient.get<TeamListResponse>('/teams', { params });
  return response.data;
}

/**
 * Team erstellen
 */
export async function createTeam(data: TeamCreateRequest): Promise<Team> {
  const response = await apiClient.post<Team>('/teams', data);
  return response.data;
}

/**
 * Team abrufen
 */
export async function getTeam(teamId: string): Promise<Team> {
  const response = await apiClient.get<Team>(`/teams/${teamId}`);
  return response.data;
}

/**
 * Team aktualisieren
 */
export async function updateTeam(teamId: string, data: TeamUpdateRequest): Promise<Team> {
  const response = await apiClient.patch<Team>(`/teams/${teamId}`, data);
  return response.data;
}

/**
 * Team loeschen
 */
export async function deleteTeam(teamId: string): Promise<void> {
  await apiClient.delete(`/teams/${teamId}`);
}

/**
 * Team archivieren
 */
export async function archiveTeam(teamId: string): Promise<Team> {
  const response = await apiClient.post<Team>(`/teams/${teamId}/archive`);
  return response.data;
}

// ==================== Members ====================

/**
 * Team-Mitglieder auflisten
 */
export async function listMembers(teamId: string): Promise<TeamMember[]> {
  const response = await apiClient.get<TeamMember[]>(`/teams/${teamId}/members`);
  return response.data;
}

/**
 * Mitglied hinzufuegen
 */
export async function addMember(teamId: string, data: MemberAddRequest): Promise<TeamMember> {
  const response = await apiClient.post<TeamMember>(`/teams/${teamId}/members`, data);
  return response.data;
}

/**
 * Mitglied-Rolle aktualisieren
 */
export async function updateMemberRole(
  teamId: string,
  userId: string,
  data: MemberUpdateRequest
): Promise<TeamMember> {
  const response = await apiClient.patch<TeamMember>(`/teams/${teamId}/members/${userId}`, data);
  return response.data;
}

/**
 * Mitglied entfernen
 */
export async function removeMember(teamId: string, userId: string): Promise<void> {
  await apiClient.delete(`/teams/${teamId}/members/${userId}`);
}

// ==================== Invitations ====================

/**
 * Einladungen auflisten
 */
export async function listInvitations(teamId: string): Promise<TeamInvitation[]> {
  const response = await apiClient.get<TeamInvitation[]>(`/teams/${teamId}/invitations`);
  return response.data;
}

/**
 * Einladung senden
 */
export async function sendInvitation(
  teamId: string,
  data: InvitationCreateRequest
): Promise<TeamInvitation> {
  const response = await apiClient.post<TeamInvitation>(`/teams/${teamId}/invitations`, data);
  return response.data;
}

/**
 * Einladung widerrufen
 */
export async function revokeInvitation(teamId: string, invitationId: string): Promise<void> {
  await apiClient.delete(`/teams/${teamId}/invitations/${invitationId}`);
}

/**
 * Einladung annehmen (via Token)
 */
export async function acceptInvitation(token: string): Promise<TeamMember> {
  const response = await apiClient.post<TeamMember>(`/teams/invitations/${token}/accept`);
  return response.data;
}

/**
 * Einladung ablehnen (via Token)
 */
export async function declineInvitation(token: string): Promise<void> {
  await apiClient.post(`/teams/invitations/${token}/decline`);
}

// ==================== Activity ====================

/**
 * Team-Aktivitaeten auflisten
 */
export async function listActivity(
  teamId: string,
  params?: ActivityListParams
): Promise<ActivityListResponse> {
  const response = await apiClient.get<ActivityListResponse>(`/teams/${teamId}/activity`, {
    params,
  });
  return response.data;
}

// ==================== Documents ====================

/**
 * Geteilte Dokumente auflisten
 */
export async function listDocuments(teamId: string): Promise<TeamDocument[]> {
  const response = await apiClient.get<TeamDocument[]>(`/teams/${teamId}/documents`);
  return response.data;
}

/**
 * Dokument mit Team teilen
 */
export async function shareDocument(teamId: string, data: DocumentShareRequest): Promise<TeamDocument> {
  const response = await apiClient.post<TeamDocument>(`/teams/${teamId}/documents`, data);
  return response.data;
}

/**
 * Dokument-Freigabe aktualisieren
 */
export async function updateDocumentShare(
  teamId: string,
  documentId: string,
  data: { permission?: TeamDocumentPermission; notes?: string }
): Promise<TeamDocument> {
  const response = await apiClient.patch<TeamDocument>(
    `/teams/${teamId}/documents/${documentId}`,
    data
  );
  return response.data;
}

/**
 * Dokument-Freigabe aufheben
 */
export async function unshareDocument(teamId: string, documentId: string): Promise<void> {
  await apiClient.delete(`/teams/${teamId}/documents/${documentId}`);
}

// ==================== Export ====================

export const teamsApi = {
  // Teams
  listTeams,
  createTeam,
  getTeam,
  updateTeam,
  deleteTeam,
  archiveTeam,
  // Members
  listMembers,
  addMember,
  updateMemberRole,
  removeMember,
  // Invitations
  listInvitations,
  sendInvitation,
  revokeInvitation,
  acceptInvitation,
  declineInvitation,
  // Activity
  listActivity,
  // Documents
  listDocuments,
  shareDocument,
  updateDocumentShare,
  unshareDocument,
};
