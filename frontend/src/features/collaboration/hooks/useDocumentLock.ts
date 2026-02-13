/**
 * useDocumentLock - Hook für Dokument-Sperren (Lock/Unlock)
 *
 * Ermöglicht exklusives Bearbeiten eines Dokuments durch einen Benutzer.
 * Andere Benutzer sehen ein "Locked"-Banner mit dem Namen des Editors.
 *
 * Backend-Endpunkte:
 * - POST /api/v1/collaboration/documents/{id}/lock
 * - DELETE /api/v1/collaboration/documents/{id}/lock
 * - GET /api/v1/collaboration/documents/{id}/lock
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { toast } from '@/components/ui/use-toast';

// ==================== Types ====================

export interface DocumentLock {
  document_id: string;
  locked_by_user_id: string;
  locked_by_user_name: string;
  locked_at: string;
  expires_at?: string;
}

export interface DocumentLockResponse {
  locked: boolean;
  lock?: DocumentLock;
}

// ==================== Query Keys ====================

export const lockKeys = {
  all: ['document-locks'] as const,
  lock: (documentId: string) => [...lockKeys.all, documentId] as const,
};

// ==================== API Functions ====================

async function getDocumentLock(documentId: string): Promise<DocumentLockResponse> {
  const response = await apiClient.get<DocumentLockResponse>(
    `/collaboration/documents/${documentId}/lock`
  );
  return response.data;
}

async function lockDocument(documentId: string): Promise<DocumentLock> {
  const response = await apiClient.post<DocumentLock>(
    `/collaboration/documents/${documentId}/lock`
  );
  return response.data;
}

async function unlockDocument(documentId: string): Promise<void> {
  await apiClient.delete(`/collaboration/documents/${documentId}/lock`);
}

// ==================== Hooks ====================

/**
 * Hook zum Prüfen ob ein Dokument gesperrt ist.
 *
 * Pollt alle 10 Sekunden und wird bei Lock/Unlock Mutations invalidiert.
 *
 * @param documentId - Dokument-ID
 */
export function useDocumentLockStatus(documentId: string) {
  return useQuery({
    queryKey: lockKeys.lock(documentId),
    queryFn: () => getDocumentLock(documentId),
    staleTime: 5000,
    refetchInterval: 10000,
    enabled: !!documentId,
    retry: 2,
  });
}

/**
 * Hook zum Sperren eines Dokuments.
 *
 * Zeigt Success/Error Toasts und invalidiert Lock-Status.
 */
export function useLockDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (documentId: string) => lockDocument(documentId),
    onSuccess: (_data, documentId) => {
      queryClient.invalidateQueries({ queryKey: lockKeys.lock(documentId) });
      toast({
        title: 'Dokument gesperrt',
        description: 'Sie bearbeiten nun exklusiv dieses Dokument',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Sperren fehlgeschlagen',
        description: error.message || 'Das Dokument konnte nicht gesperrt werden',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Entsperren eines Dokuments.
 *
 * Zeigt Success/Error Toasts und invalidiert Lock-Status.
 */
export function useUnlockDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (documentId: string) => unlockDocument(documentId),
    onSuccess: (_data, documentId) => {
      queryClient.invalidateQueries({ queryKey: lockKeys.lock(documentId) });
      toast({
        title: 'Sperre aufgehoben',
        description: 'Das Dokument kann nun von anderen bearbeitet werden',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Entsperren fehlgeschlagen',
        description: error.message || 'Die Sperre konnte nicht aufgehoben werden',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Kombinierter Hook mit Lock/Unlock Toggle-Funktion.
 *
 * @param documentId - Dokument-ID
 * @param currentUserId - User-ID des aktuellen Benutzers
 *
 * @example
 * const { isLocked, isLockedByMe, canEdit, toggleLock, isToggling } = useDocumentLock(docId, userId);
 */
export function useDocumentLock(documentId: string, currentUserId?: string) {
  const { data, isLoading } = useDocumentLockStatus(documentId);
  const lockMutation = useLockDocument();
  const unlockMutation = useUnlockDocument();

  const isLocked = data?.locked ?? false;
  const lock = data?.lock;
  const isLockedByMe = lock?.locked_by_user_id === currentUserId;
  const canEdit = !isLocked || isLockedByMe;

  const toggleLock = async () => {
    if (isLocked && isLockedByMe) {
      await unlockMutation.mutateAsync(documentId);
    } else if (!isLocked) {
      await lockMutation.mutateAsync(documentId);
    }
  };

  return {
    isLocked,
    lock,
    isLockedByMe,
    canEdit,
    isLoading,
    toggleLock,
    isToggling: lockMutation.isPending || unlockMutation.isPending,
    lockError: lockMutation.error || unlockMutation.error,
  };
}
