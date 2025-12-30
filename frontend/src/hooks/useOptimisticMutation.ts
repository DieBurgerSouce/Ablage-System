/**
 * useOptimisticMutation - Generischer Hook fuer Optimistic Updates
 *
 * Abstrahiert das Pattern aus use-job-mutations.ts fuer wiederverwendbare
 * optimistische Mutations mit automatischem Rollback und Undo-Support.
 *
 * @example
 * ```tsx
 * const deleteDoc = useOptimisticMutation({
 *   mutationFn: (id) => api.deleteDocument(id),
 *   queryKey: ['documents'],
 *   optimisticUpdate: (cache, id) => cache.filter(d => d.id !== id),
 *   successMessage: 'Dokument geloescht',
 *   errorMessage: 'Fehler beim Loeschen',
 *   undoable: true,
 *   undoFn: (id) => api.restoreDocument(id),
 * });
 * ```
 */

import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useCallback, useRef, useState } from 'react';

// ==================== Types ====================

export interface OptimisticMutationOptions<
  TData,
  TVariables,
  TCacheData = unknown,
> {
  /** Die Mutation-Funktion die die API aufruft */
  mutationFn: (variables: TVariables) => Promise<TData>;

  /** Query Key fuer den zu aktualisierenden Cache */
  queryKey: QueryKey;

  /**
   * Funktion die den Cache optimistisch aktualisiert.
   * Gibt die neuen Cache-Daten zurueck.
   */
  optimisticUpdate: (cache: TCacheData, variables: TVariables) => TCacheData;

  /**
   * Optional: Zusaetzliche Query Keys die invalidiert werden sollen
   */
  invalidateKeys?: QueryKey[];

  /** Erfolgsmeldung (deutsch) */
  successMessage?: string | ((data: TData, variables: TVariables) => string);

  /** Fehlermeldung (deutsch) */
  errorMessage?: string;

  /**
   * Aktiviert Undo-Funktionalitaet im Toast
   * @default false
   */
  undoable?: boolean;

  /**
   * Funktion zum Rueckgaengig machen der Operation.
   * Wird nur benoetigt wenn undoable=true
   */
  undoFn?: (variables: TVariables) => Promise<void>;

  /**
   * Dauer in ms wie lange der Undo-Button angezeigt wird
   * @default 5000
   */
  undoDuration?: number;

  /**
   * Callback nach erfolgreicher Mutation
   */
  onSuccess?: (data: TData, variables: TVariables) => void;

  /**
   * Callback nach fehlgeschlagener Mutation
   */
  onError?: (error: Error, variables: TVariables) => void;

  /**
   * Ob der Cache nach der Mutation invalidiert werden soll
   * @default true
   */
  invalidateOnSettled?: boolean;
}

export interface OptimisticMutationContext<TCacheData> {
  previousData: TCacheData | undefined;
  mutationId: number;
}

// ==================== Hook ====================

export function useOptimisticMutation<
  TData,
  TVariables,
  TCacheData = unknown,
>(options: OptimisticMutationOptions<TData, TVariables, TCacheData>) {
  const queryClient = useQueryClient();
  const undoTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Lock to prevent undo after mutation succeeds on server
  const [isUndoLocked, setIsUndoLocked] = useState(false);
  // Use ref to access current lock state in closures (toast callbacks)
  const isUndoLockedRef = useRef(false);
  isUndoLockedRef.current = isUndoLocked;

  const mutationIdRef = useRef(0);

  const {
    mutationFn,
    queryKey,
    optimisticUpdate,
    invalidateKeys = [],
    successMessage,
    errorMessage = 'Ein Fehler ist aufgetreten',
    undoable = false,
    undoFn,
    undoDuration = 5000,
    onSuccess,
    onError,
    invalidateOnSettled = true,
  } = options;

  // Undo-Mutation (separater Hook um Circular Dependencies zu vermeiden)
  const undoMutate = useCallback(
    async (
      variables: TVariables,
      previousData: TCacheData | undefined,
      mutationId: number
    ) => {
      // SECURITY: Check mutationId FIRST - prevents stale undo from old mutations
      // Dies muss VOR dem isUndoLockedRef Check kommen, da mutationId sich
      // zwischen schnellen Clicks aendern kann waehrend Lock noch nicht gesetzt ist
      if (mutationId !== mutationIdRef.current) {
        toast.error('Diese Aktion ist nicht mehr verfuegbar');
        return;
      }

      // Dann weitere Checks: undoFn vorhanden, Daten vorhanden, nicht bereits gelockt
      if (!undoFn || !previousData || isUndoLockedRef.current) {
        toast.error('Rueckgaengig machen nicht mehr moeglich');
        return;
      }

      // KRITISCH: Lock SOFORT via ref BEVOR async Operation startet!
      // Dies verhindert Race Conditions wenn Toast zwischen Renders geklickt wird.
      // Der Ref-Update ist synchron und sofort sichtbar fuer alle Closures.
      isUndoLockedRef.current = true;
      setIsUndoLocked(true);

      // Revert cache immediately
      queryClient.setQueryData(queryKey, previousData);

      try {
        await undoFn(variables);
        toast.success('Rueckgaengig gemacht');
      } catch {
        // Re-apply the original mutation on undo failure
        toast.error('Rueckgaengig machen fehlgeschlagen');
        queryClient.invalidateQueries({ queryKey });
      } finally {
        // WICHTIG: Ref UND State zuruecksetzen fuer Konsistenz
        isUndoLockedRef.current = false;
        setIsUndoLocked(false);
      }
    },
    [undoFn, queryKey, queryClient]
  );

  const mutation = useMutation<
    TData,
    Error,
    TVariables,
    OptimisticMutationContext<TCacheData>
  >({
    mutationFn,

    onMutate: async (variables) => {
      // Increment mutation ID to invalidate stale undo attempts
      mutationIdRef.current += 1;
      const currentMutationId = mutationIdRef.current;

      // Cancel outgoing refetches to prevent race conditions
      await queryClient.cancelQueries({ queryKey });

      // Snapshot current cache
      const previousData = queryClient.getQueryData<TCacheData>(queryKey);

      // Optimistically update cache
      if (previousData !== undefined) {
        queryClient.setQueryData<TCacheData>(
          queryKey,
          optimisticUpdate(previousData, variables)
        );
      }

      return { previousData, mutationId: currentMutationId };
    },

    onSuccess: (data, variables, context) => {
      // Clear any pending undo timeout
      if (undoTimeoutRef.current) {
        clearTimeout(undoTimeoutRef.current);
        undoTimeoutRef.current = null;
      }

      // Build success message
      const message =
        typeof successMessage === 'function'
          ? successMessage(data, variables)
          : successMessage;

      if (message) {
        if (undoable && undoFn && context?.previousData !== undefined) {
          // Capture mutationId to prevent stale undo attempts
          const capturedMutationId = context.mutationId;

          // Toast with Undo button
          toast.success(message, {
            action: {
              label: 'Rueckgaengig',
              onClick: () => {
                undoMutate(variables, context.previousData, capturedMutationId);
              },
            },
            duration: undoDuration,
          });
        } else {
          // Regular toast
          toast.success(message);
        }
      }

      // Invalidate additional query keys
      invalidateKeys.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });

      // User callback
      onSuccess?.(data, variables);
    },

    onError: (error, variables, context) => {
      // Revert cache on error
      if (context?.previousData !== undefined) {
        queryClient.setQueryData(queryKey, context.previousData);
      }

      // Show error toast
      toast.error(errorMessage, {
        description: error.message,
      });

      // User callback
      onError?.(error, variables);
    },

    onSettled: () => {
      // Always refetch to ensure consistency (optional)
      if (invalidateOnSettled) {
        queryClient.invalidateQueries({ queryKey });
      }
    },
  });

  return mutation;
}

// ==================== Convenience Hooks ====================

/**
 * Vorkonfigurierter Hook fuer Loeschoperationen mit Undo
 */
export function useOptimisticDelete<TItem extends { id: string }>(options: {
  queryKey: QueryKey;
  deleteFn: (id: string) => Promise<void>;
  restoreFn?: (id: string) => Promise<void>;
  itemName?: string;
}) {
  const { queryKey, deleteFn, restoreFn, itemName = 'Element' } = options;

  return useOptimisticMutation<void, string, TItem[]>({
    mutationFn: deleteFn,
    queryKey,
    optimisticUpdate: (cache, id) => cache.filter((item) => item.id !== id),
    successMessage: `${itemName} geloescht`,
    errorMessage: `Fehler beim Loeschen`,
    undoable: !!restoreFn,
    undoFn: restoreFn,
  });
}

/**
 * Vorkonfigurierter Hook fuer Update-Operationen
 */
export function useOptimisticUpdate<TItem extends { id: string }>(options: {
  queryKey: QueryKey;
  updateFn: (item: Partial<TItem> & { id: string }) => Promise<TItem>;
}) {
  const { queryKey, updateFn } = options;

  return useOptimisticMutation<TItem, Partial<TItem> & { id: string }, TItem[]>({
    mutationFn: updateFn,
    queryKey,
    optimisticUpdate: (cache, updates) =>
      cache.map((item) =>
        item.id === updates.id ? { ...item, ...updates } : item
      ),
    successMessage: 'Gespeichert',
    errorMessage: 'Fehler beim Speichern',
  });
}

// ==================== Export ====================

export default useOptimisticMutation;
