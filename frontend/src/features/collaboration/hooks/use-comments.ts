/**
 * useComments - Hook fuer Dokumenten-Kommentare
 *
 * Ermoeglicht das Laden, Erstellen, Bearbeiten und Loeschen von Kommentaren.
 * Integriert mit Backend API: /api/v1/documents/{documentId}/comments
 *
 * Enterprise Features:
 * - Error Handling mit Toast-Benachrichtigungen
 * - Query Invalidation nach Mutations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type {
  Comment,
  CommentsResponse,
  CreateCommentPayload,
  UpdateCommentPayload,
} from '../types/collaboration.types';

// ==================== API Functions ====================

async function fetchComments(documentId: string): Promise<CommentsResponse> {
  const response = await apiClient.get<CommentsResponse>(`/documents/${documentId}/comments`);
  return response.data;
}

async function createComment(payload: CreateCommentPayload): Promise<Comment> {
  const response = await apiClient.post<Comment>(`/documents/${payload.documentId}/comments`, {
    content: payload.content,
    mentions: payload.mentions,
    parentId: payload.parentId,
  });
  return response.data;
}

async function updateComment(
  documentId: string,
  commentId: string,
  payload: UpdateCommentPayload
): Promise<Comment> {
  const response = await apiClient.patch<Comment>(
    `/documents/${documentId}/comments/${commentId}`,
    payload
  );
  return response.data;
}

async function deleteComment(documentId: string, commentId: string): Promise<void> {
  await apiClient.delete(`/documents/${documentId}/comments/${commentId}`);
}

// ==================== Hooks ====================

export function useComments(documentId: string) {
  return useQuery({
    queryKey: ['comments', documentId],
    queryFn: () => fetchComments(documentId),
    staleTime: 30000,
    enabled: !!documentId,
  });
}

export function useCreateComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createComment,
    onSuccess: (newComment) => {
      queryClient.invalidateQueries({
        queryKey: ['comments', newComment.documentId],
      });
      toast.success('Kommentar hinzugefügt');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Erstellen des Kommentars', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useUpdateComment(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ commentId, payload }: { commentId: string; payload: UpdateCommentPayload }) =>
      updateComment(documentId, commentId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      toast.success('Kommentar aktualisiert');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Aktualisieren des Kommentars', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useDeleteComment(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (commentId: string) => deleteComment(documentId, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      toast.success('Kommentar gelöscht');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Löschen des Kommentars', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}
