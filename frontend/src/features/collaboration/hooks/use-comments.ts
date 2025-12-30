/**
 * useComments - Hook fuer Dokumenten-Kommentare
 *
 * Ermoeglicht das Laden, Erstellen, Bearbeiten und Loeschen von Kommentaren.
 * Verwendet Mock-Daten bis Backend-API verfuegbar ist.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type {
  Comment,
  CommentsResponse,
  CreateCommentPayload,
  UpdateCommentPayload,
} from '../types/collaboration.types';

// ==================== Mock Data ====================

const MOCK_COMMENTS: Comment[] = [
  {
    id: 'comment-1',
    documentId: 'doc-1',
    userId: 'user-1',
    userName: 'Max Mustermann',
    content: 'Die Rechnung sieht korrekt aus. Bitte @anna.schmidt zur Pruefung weiterleiten.',
    mentions: [
      { userId: 'user-2', userName: 'Anna Schmidt', startIndex: 43, endIndex: 56 },
    ],
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    isEdited: false,
    reactions: [{ emoji: '👍', count: 2, userIds: ['user-2', 'user-3'] }],
  },
  {
    id: 'comment-2',
    documentId: 'doc-1',
    userId: 'user-2',
    userName: 'Anna Schmidt',
    content: 'Geprueft und freigegeben. Kann zur Zahlung weitergeleitet werden.',
    mentions: [],
    parentId: 'comment-1',
    createdAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    isEdited: false,
  },
  {
    id: 'comment-3',
    documentId: 'doc-1',
    userId: 'user-3',
    userName: 'Thomas Mueller',
    content: 'Hinweis: Der Skontobetrag wurde bereits abgezogen.',
    mentions: [],
    createdAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    isEdited: true,
    updatedAt: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
  },
];

// ==================== API Functions ====================

async function fetchComments(documentId: string): Promise<CommentsResponse> {
  // TODO: Replace with actual API call
  // const response = await apiClient.get<CommentsResponse>(`/documents/${documentId}/comments`);
  // return response.data;

  await new Promise((resolve) => setTimeout(resolve, 300));

  const comments = MOCK_COMMENTS.filter((c) => c.documentId === documentId || documentId === 'doc-1');
  return {
    comments,
    total: comments.length,
    hasMore: false,
  };
}

async function createComment(payload: CreateCommentPayload): Promise<Comment> {
  // TODO: Replace with actual API call
  // const response = await apiClient.post<Comment>(`/documents/${payload.documentId}/comments`, payload);
  // return response.data;

  await new Promise((resolve) => setTimeout(resolve, 300));

  const newComment: Comment = {
    id: `comment-${Date.now()}`,
    documentId: payload.documentId,
    userId: 'current-user',
    userName: 'Aktueller Benutzer',
    content: payload.content,
    mentions: payload.mentions?.map((m, idx) => ({
      ...m,
      startIndex: payload.content.indexOf(`@${m.userName}`),
      endIndex: payload.content.indexOf(`@${m.userName}`) + m.userName.length + 1,
    })) || [],
    parentId: payload.parentId,
    createdAt: new Date().toISOString(),
    isEdited: false,
  };

  return newComment;
}

async function updateComment(
  commentId: string,
  payload: UpdateCommentPayload
): Promise<Comment> {
  // TODO: Replace with actual API call
  await new Promise((resolve) => setTimeout(resolve, 300));

  const existing = MOCK_COMMENTS.find((c) => c.id === commentId);
  if (!existing) throw new Error('Kommentar nicht gefunden');

  return {
    ...existing,
    content: payload.content,
    isEdited: true,
    updatedAt: new Date().toISOString(),
  };
}

async function deleteComment(commentId: string): Promise<void> {
  // TODO: Replace with actual API call
  await new Promise((resolve) => setTimeout(resolve, 300));
}

// ==================== Hooks ====================

export function useComments(documentId: string) {
  return useQuery({
    queryKey: ['comments', documentId],
    queryFn: () => fetchComments(documentId),
    staleTime: 30000,
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
    },
  });
}

export function useUpdateComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ commentId, payload }: { commentId: string; payload: UpdateCommentPayload }) =>
      updateComment(commentId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments'] });
    },
  });
}

export function useDeleteComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteComment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments'] });
    },
  });
}
