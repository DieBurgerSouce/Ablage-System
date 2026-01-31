/**
 * useUndoableAction - Undo Stack Management Hook
 *
 * Verwaltet einen Stack von rueckgaengig machbaren Aktionen.
 * Nuetzlich fuer komplexe Szenarien mit mehreren Undo-Schritten.
 *
 * @example
 * ```tsx
 * const { executeAction, undo, canUndo, undoStack } = useUndoableAction({
 *   maxStackSize: 10,
 *   onUndo: (action) => logger.debug('Rueckgaengig:', action.description),
 * });
 *
 * // Eine Aktion ausfuehren
 * await executeAction({
 *   description: 'Dokument geloescht',
 *   execute: () => api.deleteDocument(id),
 *   undo: () => api.restoreDocument(id),
 * });
 *
 * // Rückgängig machen
 * if (canUndo) {
 *   await undo();
 * }
 * ```
 */

import { useState, useCallback, useRef, createContext, useContext, type ReactNode } from 'react';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';

// ==================== Types ====================

export interface UndoableAction<T = unknown> {
  /** Eindeutige ID der Aktion */
  id: string;
  /** Beschreibung fuer UI/Logs */
  description: string;
  /** Zeitstempel der Ausfuehrung */
  timestamp: Date;
  /** Die Funktion die die Aktion ausfuehrt */
  execute: () => Promise<T>;
  /** Die Funktion die die Aktion rueckgaengig macht */
  undo: () => Promise<void>;
  /** Optionale Daten die mit der Aktion gespeichert werden */
  data?: T;
}

export interface UseUndoableActionOptions {
  /**
   * Maximale Groesse des Undo-Stacks
   * @default 20
   */
  maxStackSize?: number;

  /**
   * Callback wenn eine Aktion rueckgaengig gemacht wird
   */
  onUndo?: (action: UndoableAction) => void;

  /**
   * Callback wenn eine Aktion ausgefuehrt wird
   */
  onExecute?: (action: UndoableAction) => void;

  /**
   * Ob Toast-Benachrichtigungen angezeigt werden sollen
   * @default true
   */
  showToasts?: boolean;

  /**
   * Dauer in ms bis der Undo-Button verschwindet
   * @default 5000
   */
  toastDuration?: number;
}

export interface UseUndoableActionReturn {
  /** Fuehrt eine Aktion aus und fuegt sie zum Undo-Stack hinzu */
  executeAction: <T>(
    action: Omit<UndoableAction<T>, 'id' | 'timestamp' | 'data'>
  ) => Promise<T>;
  /** Macht die letzte Aktion rueckgaengig */
  undo: () => Promise<void>;
  /** Wiederholt die letzte rueckgaengig gemachte Aktion */
  redo: () => Promise<void>;
  /** Ob es Aktionen zum Rückgängig machen gibt */
  canUndo: boolean;
  /** Ob es Aktionen zum Wiederholen gibt */
  canRedo: boolean;
  /** Der aktuelle Undo-Stack */
  undoStack: UndoableAction[];
  /** Der aktuelle Redo-Stack */
  redoStack: UndoableAction[];
  /** Leert den Undo- und Redo-Stack */
  clearStack: () => void;
  /** Ob gerade eine Undo-Operation laeuft */
  isUndoing: boolean;
  /** Ob gerade eine Redo-Operation laeuft */
  isRedoing: boolean;
}

// ==================== Hook ====================

export function useUndoableAction(
  options: UseUndoableActionOptions = {}
): UseUndoableActionReturn {
  const {
    maxStackSize = 20,
    onUndo,
    onExecute,
    showToasts = true,
    toastDuration = 5000,
  } = options;

  const [undoStack, setUndoStack] = useState<UndoableAction[]>([]);
  const [redoStack, setRedoStack] = useState<UndoableAction[]>([]);
  const [isUndoing, setIsUndoing] = useState(false);
  const [isRedoing, setIsRedoing] = useState(false);
  const idCounter = useRef(0);

  // Use ref-based lock to prevent race conditions from rapid undo/redo calls
  const isUndoingRef = useRef(false);
  const isRedoingRef = useRef(false);

  // Ref fuer aktuellen Stack - verhindert stale closures in Toast-Callbacks
  const undoStackRef = useRef<UndoableAction[]>(undoStack);
  undoStackRef.current = undoStack;

  // ENTERPRISE FIX: Mutation ID um veraltete Toast-Clicks zu erkennen
  // Wenn der Stack durch andere Operationen geaendert wurde,
  // kann der Toast-Click auf eine veraltete Action zeigen
  const mutationIdRef = useRef(0);

  const executeAction = useCallback(
    async <T,>(
      action: Omit<UndoableAction<T>, 'id' | 'timestamp' | 'data'>
    ): Promise<T> => {
      // Generate unique ID
      const id = `action-${++idCounter.current}-${Date.now()}`;

      try {
        // Execute the action
        const result = await action.execute();

        // Create full action object with result
        const fullAction: UndoableAction<T> = {
          ...action,
          id,
          timestamp: new Date(),
          data: result,
        };

        // ENTERPRISE FIX: Capture mutation ID at time of action execution
        // This allows detecting if stack was modified by other operations
        const capturedMutationId = ++mutationIdRef.current;

        // Add to stack (with size limit) and clear redo stack (new action invalidates redo history)
        setUndoStack((prev) => {
          const newStack = [fullAction as UndoableAction, ...prev];
          return newStack.slice(0, maxStackSize);
        });
        setRedoStack([]); // Clear redo stack on new action

        // Callback
        onExecute?.(fullAction as UndoableAction);

        // Show toast with undo option
        if (showToasts) {
          toast.success(action.description, {
            action: {
              label: 'Rückgängig',
              onClick: async () => {
                // ENTERPRISE FIX: Prüfe ob Stack durch andere Ops geändert wurde
                if (capturedMutationId !== mutationIdRef.current) {
                  // Stack wurde geändert seit Toast erstellt wurde
                  // Die Action könnte nicht mehr im erwarteten State sein
                  const stillExists = undoStackRef.current.find((a) => a.id === id);
                  if (!stillExists) {
                    toast.error('Aktion nicht mehr verfügbar');
                    return;
                  }
                  // Warnung ausgeben aber trotzdem versuchen wenn Action noch existiert
                  logger.warn('[useUndoableAction] Stack wurde seit Toast-Erstellung geändert');
                }

                // KRITISCH: Finde Action BEVOR wir versuchen sie rueckgaengig zu machen
                // und entferne sie NUR bei Erfolg aus dem Stack!
                // Verwende Ref fuer AKTUELLEN Stack (keine stale closure)
                const actionToUndo = undoStackRef.current.find((a) => a.id === id);

                if (!actionToUndo) {
                  toast.error('Aktion nicht mehr verfügbar');
                  return;
                }

                try {
                  // Fuehre undo aus und WARTE auf Erfolg
                  await actionToUndo.undo();

                  // NUR bei Erfolg: Entferne aus Stack und inkrementiere mutation ID
                  mutationIdRef.current++;
                  setUndoStack((prev) => prev.filter((a) => a.id !== id));
                  toast.success('Rückgängig gemacht');
                } catch (err) {
                  // Bei Fehler: Behalte im Stack fuer erneuten Versuch
                  toast.error('Rückgängig machen fehlgeschlagen - erneut versuchen möglich', {
                    description:
                      err instanceof Error ? err.message : 'Unbekannter Fehler',
                  });
                  // Stack bleibt unveraendert - User kann es erneut versuchen
                }
              },
            },
            duration: toastDuration,
          });
        }

        return result;
      } catch (error) {
        // Don't add failed actions to stack
        toast.error('Aktion fehlgeschlagen', {
          description:
            error instanceof Error ? error.message : 'Unbekannter Fehler',
        });
        throw error;
      }
    },
    [maxStackSize, onExecute, showToasts, toastDuration]
  );

  const undo = useCallback(async () => {
    // Use ref-based lock to prevent race conditions from rapid calls
    // State-based isUndoing can have stale values in quick succession
    if (undoStack.length === 0 || isUndoingRef.current || isRedoingRef.current) return;

    // Lock immediately using ref (synchronous)
    isUndoingRef.current = true;
    setIsUndoing(true);

    const [actionToUndo, ...remainingStack] = undoStack;

    try {
      // Execute undo
      await actionToUndo.undo();

      // Only remove from stack on SUCCESS and add to redo stack
      setUndoStack(remainingStack);
      setRedoStack((prev) => [actionToUndo, ...prev].slice(0, maxStackSize));

      // Callback
      onUndo?.(actionToUndo);

      // Toast
      if (showToasts) {
        toast.success('Rückgängig gemacht', {
          description: actionToUndo.description,
        });
      }
    } catch (error) {
      // KEEP action in stack on failure - allow retry
      toast.error('Rückgängig machen fehlgeschlagen - erneut versuchen möglich', {
        description:
          error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
      // Don't re-throw - let user retry
    } finally {
      isUndoingRef.current = false;
      setIsUndoing(false);
    }
  }, [undoStack, onUndo, showToasts, maxStackSize]);

  const redo = useCallback(async () => {
    // Use ref-based lock to prevent race conditions from rapid calls
    if (redoStack.length === 0 || isRedoingRef.current || isUndoingRef.current) return;

    // Lock immediately using ref (synchronous)
    isRedoingRef.current = true;
    setIsRedoing(true);

    const [actionToRedo, ...remainingRedoStack] = redoStack;

    try {
      // Re-execute the action
      const result = await actionToRedo.execute();

      // Update the action with new result
      const updatedAction: UndoableAction = {
        ...actionToRedo,
        data: result,
        timestamp: new Date(),
      };

      // Only move from redo to undo stack on SUCCESS
      setRedoStack(remainingRedoStack);
      setUndoStack((prev) => [updatedAction, ...prev].slice(0, maxStackSize));

      // Toast
      if (showToasts) {
        toast.success('Wiederholt', {
          description: actionToRedo.description,
        });
      }
    } catch (error) {
      // KEEP action in redo stack on failure - allow retry
      toast.error('Wiederholen fehlgeschlagen - erneut versuchen möglich', {
        description:
          error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
      // Don't re-throw - let user retry
    } finally {
      isRedoingRef.current = false;
      setIsRedoing(false);
    }
  }, [redoStack, showToasts, maxStackSize]);

  const clearStack = useCallback(() => {
    setUndoStack([]);
    setRedoStack([]);
  }, []);

  return {
    executeAction,
    undo,
    redo,
    canUndo: undoStack.length > 0 && !isUndoing && !isRedoing,
    canRedo: redoStack.length > 0 && !isUndoing && !isRedoing,
    undoStack,
    redoStack,
    clearStack,
    isUndoing,
    isRedoing,
  };
}

// ==================== Context for Global Undo ====================

const UndoContext = createContext<UseUndoableActionReturn | null>(null);

export function UndoProvider({
  children,
  options,
}: {
  children: ReactNode;
  options?: UseUndoableActionOptions;
}) {
  const undoActions = useUndoableAction(options);

  return (
    <UndoContext.Provider value={undoActions}>{children}</UndoContext.Provider>
  );
}

export function useGlobalUndo(): UseUndoableActionReturn {
  const context = useContext(UndoContext);
  if (!context) {
    throw new Error('useGlobalUndo must be used within UndoProvider');
  }
  return context;
}

// ==================== Export ====================

export default useUndoableAction;
