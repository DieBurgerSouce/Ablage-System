/**
 * Knowledge Management API
 *
 * API client and React Query hooks for knowledge management.
 */

import { useMutation, useQuery, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';
import type {
  KnowledgeNote,
  KnowledgeNoteDetail,
  KnowledgeNoteCreate,
  KnowledgeNoteUpdate,
  KnowledgeNoteListParams,
  KnowledgeNoteListResponse,
  KnowledgeChecklist,
  KnowledgeChecklistCreate,
  KnowledgeChecklistUpdate,
  KnowledgeChecklistListParams,
  KnowledgeChecklistListResponse,
  KnowledgeChecklistItemCreate,
  KnowledgeChecklistItemUpdate,
  KnowledgeChecklistItem,
  KnowledgeLink,
  KnowledgeLinkCreate,
  KnowledgeLinkListParams,
  KnowledgeLinkListResponse,
  KnowledgeTag,
  KnowledgeTagCreate,
  KnowledgeTagUpdate,
  KnowledgeTagListParams,
  KnowledgeTagListResponse,
} from '../types/knowledge-types';

const API_BASE = '/api/v1/knowledge';

// =============================================================================
// Query Keys
// =============================================================================

export const knowledgeKeys = {
  all: ['knowledge'] as const,
  // Notes
  notes: () => [...knowledgeKeys.all, 'notes'] as const,
  notesList: (params: KnowledgeNoteListParams) => [...knowledgeKeys.notes(), 'list', params] as const,
  noteDetail: (id: string) => [...knowledgeKeys.notes(), 'detail', id] as const,
  // Checklists
  checklists: () => [...knowledgeKeys.all, 'checklists'] as const,
  checklistsList: (params: KnowledgeChecklistListParams) => [...knowledgeKeys.checklists(), 'list', params] as const,
  checklistDetail: (id: string) => [...knowledgeKeys.checklists(), 'detail', id] as const,
  // Links
  links: () => [...knowledgeKeys.all, 'links'] as const,
  linksList: (params: KnowledgeLinkListParams) => [...knowledgeKeys.links(), 'list', params] as const,
  // Tags
  tags: () => [...knowledgeKeys.all, 'tags'] as const,
  tagsList: (params: KnowledgeTagListParams) => [...knowledgeKeys.tags(), 'list', params] as const,
};

// =============================================================================
// Helper: Build Query String
// =============================================================================

function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  }
  const query = searchParams.toString();
  return query ? `?${query}` : '';
}

// =============================================================================
// Notes API Functions
// =============================================================================

export async function listNotes(params: KnowledgeNoteListParams = {}): Promise<KnowledgeNoteListResponse> {
  return fetchWithAuth<KnowledgeNoteListResponse>(`${API_BASE}/notes${buildQueryString(params)}`);
}

export async function getNote(id: string): Promise<KnowledgeNoteDetail> {
  return fetchWithAuth<KnowledgeNoteDetail>(`${API_BASE}/notes/${id}`);
}

export async function createNote(data: KnowledgeNoteCreate): Promise<KnowledgeNote> {
  return fetchWithAuth<KnowledgeNote>(`${API_BASE}/notes`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateNote(id: string, data: KnowledgeNoteUpdate): Promise<KnowledgeNote> {
  return fetchWithAuth<KnowledgeNote>(`${API_BASE}/notes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteNote(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/notes/${id}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// Checklists API Functions
// =============================================================================

export async function listChecklists(params: KnowledgeChecklistListParams = {}): Promise<KnowledgeChecklistListResponse> {
  return fetchWithAuth<KnowledgeChecklistListResponse>(`${API_BASE}/checklists${buildQueryString(params)}`);
}

export async function getChecklist(id: string): Promise<KnowledgeChecklist> {
  return fetchWithAuth<KnowledgeChecklist>(`${API_BASE}/checklists/${id}`);
}

export async function createChecklist(data: KnowledgeChecklistCreate): Promise<KnowledgeChecklist> {
  return fetchWithAuth<KnowledgeChecklist>(`${API_BASE}/checklists`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateChecklist(id: string, data: KnowledgeChecklistUpdate): Promise<KnowledgeChecklist> {
  return fetchWithAuth<KnowledgeChecklist>(`${API_BASE}/checklists/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteChecklist(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/checklists/${id}`, {
    method: 'DELETE',
  });
}

// Checklist Items
export async function addChecklistItem(checklistId: string, data: KnowledgeChecklistItemCreate): Promise<KnowledgeChecklistItem> {
  return fetchWithAuth<KnowledgeChecklistItem>(`${API_BASE}/checklists/${checklistId}/items`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateChecklistItem(
  checklistId: string,
  itemId: string,
  data: KnowledgeChecklistItemUpdate
): Promise<KnowledgeChecklistItem> {
  return fetchWithAuth<KnowledgeChecklistItem>(`${API_BASE}/checklists/${checklistId}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteChecklistItem(checklistId: string, itemId: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/checklists/${checklistId}/items/${itemId}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// Links API Functions
// =============================================================================

export async function listLinks(params: KnowledgeLinkListParams = {}): Promise<KnowledgeLinkListResponse> {
  return fetchWithAuth<KnowledgeLinkListResponse>(`${API_BASE}/links${buildQueryString(params)}`);
}

export async function createLink(data: KnowledgeLinkCreate): Promise<KnowledgeLink> {
  return fetchWithAuth<KnowledgeLink>(`${API_BASE}/links`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteLink(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/links/${id}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// Tags API Functions
// =============================================================================

export async function listTags(params: KnowledgeTagListParams = {}): Promise<KnowledgeTagListResponse> {
  return fetchWithAuth<KnowledgeTagListResponse>(`${API_BASE}/tags${buildQueryString(params)}`);
}

export async function createTag(data: KnowledgeTagCreate): Promise<KnowledgeTag> {
  return fetchWithAuth<KnowledgeTag>(`${API_BASE}/tags`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateTag(id: string, data: KnowledgeTagUpdate): Promise<KnowledgeTag> {
  return fetchWithAuth<KnowledgeTag>(`${API_BASE}/tags/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteTag(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/tags/${id}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// React Query Hooks - Notes
// =============================================================================

export function useNotes(params: KnowledgeNoteListParams = {}, options?: Partial<UseQueryOptions<KnowledgeNoteListResponse>>) {
  return useQuery({
    queryKey: knowledgeKeys.notesList(params),
    queryFn: () => listNotes(params),
    ...options,
  });
}

export function useNote(id: string, options?: Partial<UseQueryOptions<KnowledgeNoteDetail>>) {
  return useQuery({
    queryKey: knowledgeKeys.noteDetail(id),
    queryFn: () => getNote(id),
    enabled: !!id,
    ...options,
  });
}

export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  });
}

export function useUpdateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: KnowledgeNoteUpdate }) => updateNote(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.noteDetail(variables.id) });
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  });
}

export function useDeleteNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  });
}

// =============================================================================
// React Query Hooks - Checklists
// =============================================================================

export function useChecklists(
  params: KnowledgeChecklistListParams = {},
  options?: Partial<UseQueryOptions<KnowledgeChecklistListResponse>>
) {
  return useQuery({
    queryKey: knowledgeKeys.checklistsList(params),
    queryFn: () => listChecklists(params),
    ...options,
  });
}

export function useChecklist(id: string, options?: Partial<UseQueryOptions<KnowledgeChecklist>>) {
  return useQuery({
    queryKey: knowledgeKeys.checklistDetail(id),
    queryFn: () => getChecklist(id),
    enabled: !!id,
    ...options,
  });
}

export function useCreateChecklist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createChecklist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklists() });
    },
  });
}

export function useUpdateChecklist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: KnowledgeChecklistUpdate }) => updateChecklist(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklistDetail(variables.id) });
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklists() });
    },
  });
}

export function useDeleteChecklist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteChecklist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklists() });
    },
  });
}

// Checklist Items
export function useAddChecklistItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checklistId, data }: { checklistId: string; data: KnowledgeChecklistItemCreate }) =>
      addChecklistItem(checklistId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklistDetail(variables.checklistId) });
    },
  });
}

export function useUpdateChecklistItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      checklistId,
      itemId,
      data,
    }: {
      checklistId: string;
      itemId: string;
      data: KnowledgeChecklistItemUpdate;
    }) => updateChecklistItem(checklistId, itemId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklistDetail(variables.checklistId) });
    },
  });
}

export function useDeleteChecklistItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checklistId, itemId }: { checklistId: string; itemId: string }) =>
      deleteChecklistItem(checklistId, itemId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.checklistDetail(variables.checklistId) });
    },
  });
}

// =============================================================================
// React Query Hooks - Links
// =============================================================================

export function useLinks(params: KnowledgeLinkListParams = {}, options?: Partial<UseQueryOptions<KnowledgeLinkListResponse>>) {
  return useQuery({
    queryKey: knowledgeKeys.linksList(params),
    queryFn: () => listLinks(params),
    ...options,
  });
}

export function useCreateLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.links() });
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  });
}

export function useDeleteLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.links() });
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  });
}

// =============================================================================
// React Query Hooks - Tags
// =============================================================================

export function useTags(params: KnowledgeTagListParams = {}, options?: Partial<UseQueryOptions<KnowledgeTagListResponse>>) {
  return useQuery({
    queryKey: knowledgeKeys.tagsList(params),
    queryFn: () => listTags(params),
    ...options,
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTag,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.tags() });
    },
  });
}

export function useUpdateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: KnowledgeTagUpdate }) => updateTag(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.tags() });
    },
  });
}

export function useDeleteTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteTag,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.tags() });
    },
  });
}
