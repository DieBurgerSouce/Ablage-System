/**
 * Annotation Hooks - TanStack Query Hooks fuer Dokument-Annotationen
 *
 * Ermoeglicht das Laden, Erstellen, Aktualisieren und Loeschen von Annotationen.
 * Integriert mit Backend API: /api/v1/annotations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getAnnotations,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  type AnnotationCreatePayload,
  type AnnotationUpdatePayload,
} from '../api/annotations-api';

// ==================== Query Keys ====================

export const annotationKeys = {
  all: ['annotations'] as const,
  document: (documentId: string) => [...annotationKeys.all, 'document', documentId] as const,
};

// ==================== Query Hooks ====================

/**
 * Hook fuer alle Annotationen eines Dokuments
 */
export function useAnnotations(documentId: string) {
  return useQuery({
    queryKey: annotationKeys.document(documentId),
    queryFn: () => getAnnotations(documentId),
    enabled: !!documentId,
    staleTime: 30000,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Hook zum Erstellen einer Annotation
 */
export function useCreateAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AnnotationCreatePayload) => createAnnotation(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: annotationKeys.document(documentId) });
      toast.success('Annotation erstellt');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Erstellen der Annotation', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

/**
 * Hook zum Aktualisieren einer Annotation
 */
export function useUpdateAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AnnotationUpdatePayload }) =>
      updateAnnotation(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: annotationKeys.document(documentId) });
      toast.success('Annotation aktualisiert');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Aktualisieren', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

/**
 * Hook zum Aufloesen (Erledigen) einer Annotation
 */
export function useResolveAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => updateAnnotation(id, { is_resolved: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: annotationKeys.document(documentId) });
      toast.success('Annotation erledigt');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Erledigen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

/**
 * Hook zum Loeschen einer Annotation
 */
export function useDeleteAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteAnnotation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: annotationKeys.document(documentId) });
      toast.success('Annotation geloescht');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Loeschen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}
