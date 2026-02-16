/**
 * useUndoRedo - Undo/Redo State Management Hook
 *
 * Provides comprehensive undo/redo functionality with:
 * - Action history stack with configurable size
 * - Grouped actions for batch undo
 * - Integration with keyboard shortcuts (Ctrl+Z, Ctrl+Y)
 * - Toast notifications with undo option
 * - Support for async operations
 *
 * @example
 * ```tsx
 * const { executeAction, undo, redo, canUndo, canRedo } = useUndoRedo({
 *   maxStackSize: 20,
 *   enableKeyboardShortcuts: true,
 * });
 *
 * // Execute an undoable action
 * await executeAction({
 *   description: 'Dokument gelöscht',
 *   execute: () => api.deleteDocument(id),
 *   undo: () => api.restoreDocument(id),
 * });
 *
 * // Undo the last action
 * await undo();
 * ```
 */

import { useState, useCallback, useRef, useEffect, createContext, useContext, type ReactNode } from 'react';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { useRegisterShortcut, type KeyboardShortcut } from './useKeyboardShortcuts';

// ==================== Types ====================

/**
 * An undoable action
 */
export interface UndoableAction<T = unknown> {
  /** Unique identifier */
  id: string;
  /** Human-readable description (German) */
  description: string;
  /** Timestamp of execution */
  timestamp: Date;
  /** Function to execute the action */
  execute: () => Promise<T>;
  /** Function to undo the action */
  undo: () => Promise<void>;
  /** Optional data associated with the action */
  data?: T;
  /** Action group ID for batch undo */
  groupId?: string;
  /** Whether this action can be undone */
  canUndo?: boolean;
}

/**
 * Action definition for executeAction (without auto-generated fields)
 */
export interface ActionDefinition<T = unknown> {
  /** Human-readable description (German) */
  description: string;
  /** Function to execute the action */
  execute: () => Promise<T>;
  /** Function to undo the action */
  undo: () => Promise<void>;
  /** Optional group ID for batch undo */
  groupId?: string;
  /** Whether to show toast notification */
  showToast?: boolean;
  /** Toast duration in ms */
  toastDuration?: number;
}

/**
 * Options for useUndoRedo hook
 */
export interface UseUndoRedoOptions {
  /** Maximum size of the undo stack (default: 20) */
  maxStackSize?: number;
  /** Whether to show toast notifications (default: true) */
  showToasts?: boolean;
  /** Default toast duration in ms (default: 5000) */
  toastDuration?: number;
  /** Enable keyboard shortcuts Ctrl+Z/Ctrl+Y (default: true) */
  enableKeyboardShortcuts?: boolean;
  /** Callback when an action is undone */
  onUndo?: (action: UndoableAction) => void;
  /** Callback when an action is redone */
  onRedo?: (action: UndoableAction) => void;
  /** Callback when an action is executed */
  onExecute?: (action: UndoableAction) => void;
}

/**
 * Return type of useUndoRedo hook
 */
export interface UseUndoRedoReturn {
  /** Execute an undoable action */
  executeAction: <T>(action: ActionDefinition<T>) => Promise<T>;
  /** Execute a grouped action (multiple actions undone together) */
  executeGroupedAction: <T>(groupId: string, action: ActionDefinition<T>) => Promise<T>;
  /** Undo the last action (or group) */
  undo: () => Promise<void>;
  /** Redo the last undone action (or group) */
  redo: () => Promise<void>;
  /** Whether there are actions to undo */
  canUndo: boolean;
  /** Whether there are actions to redo */
  canRedo: boolean;
  /** Current undo stack */
  undoStack: UndoableAction[];
  /** Current redo stack */
  redoStack: UndoableAction[];
  /** Clear all history */
  clearHistory: () => void;
  /** Whether an undo operation is in progress */
  isUndoing: boolean;
  /** Whether a redo operation is in progress */
  isRedoing: boolean;
  /** Get keyboard shortcuts for registration */
  getKeyboardShortcuts: () => KeyboardShortcut[];
}

// ==================== Utilities ====================

/**
 * Generate a unique action ID
 */
let actionIdCounter = 0;
function generateActionId(): string {
  return `action-${++actionIdCounter}-${Date.now()}`;
}

// ==================== Hook ====================

export function useUndoRedo(options: UseUndoRedoOptions = {}): UseUndoRedoReturn {
  const {
    maxStackSize = 20,
    showToasts = true,
    toastDuration = 5000,
    enableKeyboardShortcuts = true,
    onUndo,
    onRedo,
    onExecute,
  } = options;

  const [undoStack, setUndoStack] = useState<UndoableAction[]>([]);
  const [redoStack, setRedoStack] = useState<UndoableAction[]>([]);
  const [isUndoing, setIsUndoing] = useState(false);
  const [isRedoing, setIsRedoing] = useState(false);

  // Ref-based locks for race condition prevention
  const isUndoingRef = useRef(false);
  const isRedoingRef = useRef(false);

  // Ref for current stack (prevents stale closures in toast callbacks)
  const undoStackRef = useRef<UndoableAction[]>(undoStack);
  undoStackRef.current = undoStack;

  // Mutation ID for tracking stack changes
  const mutationIdRef = useRef(0);

  /**
   * Execute an undoable action
   */
  const executeAction = useCallback(
    async <T,>(actionDef: ActionDefinition<T>): Promise<T> => {
      const id = generateActionId();
      const shouldShowToast = actionDef.showToast ?? showToasts;
      const duration = actionDef.toastDuration ?? toastDuration;

      try {
        // Execute the action
        const result = await actionDef.execute();

        // Create the full action object
        const fullAction: UndoableAction<T> = {
          id,
          description: actionDef.description,
          timestamp: new Date(),
          execute: actionDef.execute,
          undo: actionDef.undo,
          data: result,
          groupId: actionDef.groupId,
          canUndo: true,
        };

        // Capture mutation ID for toast callback
        const capturedMutationId = ++mutationIdRef.current;

        // Add to undo stack, clear redo stack
        setUndoStack(prev => {
          const newStack = [fullAction as UndoableAction, ...prev];
          return newStack.slice(0, maxStackSize);
        });
        setRedoStack([]);

        // Callback
        onExecute?.(fullAction as UndoableAction);

        // Show toast with undo option
        if (shouldShowToast) {
          toast.success(actionDef.description, {
            action: {
              label: 'Rückgängig',
              onClick: async () => {
                // Check if stack was modified
                if (capturedMutationId !== mutationIdRef.current) {
                  const stillExists = undoStackRef.current.find(a => a.id === id);
                  if (!stillExists) {
                    toast.error('Aktion nicht mehr verfügbar');
                    return;
                  }
                  logger.warn('[useUndoRedo] Stack wurde seit Toast-Erstellung geändert');
                }

                const actionToUndo = undoStackRef.current.find(a => a.id === id);
                if (!actionToUndo) {
                  toast.error('Aktion nicht mehr verfügbar');
                  return;
                }

                try {
                  await actionToUndo.undo();
                  mutationIdRef.current++;
                  setUndoStack(prev => prev.filter(a => a.id !== id));
                  toast.success('Rückgängig gemacht');
                } catch (err) {
                  toast.error('Rückgängig machen fehlgeschlagen', {
                    description: err instanceof Error ? err.message : 'Unbekannter Fehler',
                  });
                }
              },
            },
            duration,
          });
        }

        return result;
      } catch (error) {
        toast.error('Aktion fehlgeschlagen', {
          description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        });
        throw error;
      }
    },
    [maxStackSize, showToasts, toastDuration, onExecute]
  );

  /**
   * Execute a grouped action (for batch undo)
   */
  const executeGroupedAction = useCallback(
    async <T,>(groupId: string, actionDef: ActionDefinition<T>): Promise<T> => {
      return executeAction({ ...actionDef, groupId });
    },
    [executeAction]
  );

  /**
   * Undo the last action or group
   */
  const undo = useCallback(async () => {
    if (undoStack.length === 0 || isUndoingRef.current || isRedoingRef.current) return;

    isUndoingRef.current = true;
    setIsUndoing(true);

    try {
      // Get the first action
      const firstAction = undoStack[0];
      const groupId = firstAction.groupId;

      // If grouped, get all actions in the group
      const actionsToUndo = groupId
        ? undoStack.filter(a => a.groupId === groupId)
        : [firstAction];

      // Undo all actions in reverse order
      for (let i = actionsToUndo.length - 1; i >= 0; i--) {
        await actionsToUndo[i].undo();
      }

      // Move to redo stack
      setUndoStack(prev => prev.filter(a => !actionsToUndo.includes(a)));
      setRedoStack(prev => [...actionsToUndo, ...prev].slice(0, maxStackSize));

      // Callbacks
      actionsToUndo.forEach(a => onUndo?.(a));

      if (showToasts) {
        const count = actionsToUndo.length;
        toast.success(
          count > 1
            ? `${count} Aktionen rückgängig gemacht`
            : 'Rückgängig gemacht',
          { description: firstAction.description }
        );
      }
    } catch (error) {
      toast.error('Rückgängig machen fehlgeschlagen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    } finally {
      isUndoingRef.current = false;
      setIsUndoing(false);
    }
  }, [undoStack, maxStackSize, showToasts, onUndo]);

  /**
   * Redo the last undone action or group
   */
  const redo = useCallback(async () => {
    if (redoStack.length === 0 || isUndoingRef.current || isRedoingRef.current) return;

    isRedoingRef.current = true;
    setIsRedoing(true);

    try {
      // Get the first action
      const firstAction = redoStack[0];
      const groupId = firstAction.groupId;

      // If grouped, get all actions in the group
      const actionsToRedo = groupId
        ? redoStack.filter(a => a.groupId === groupId)
        : [firstAction];

      // Execute all actions in order
      const updatedActions: UndoableAction[] = [];
      for (const action of actionsToRedo) {
        const result = await action.execute();
        updatedActions.push({
          ...action,
          data: result,
          timestamp: new Date(),
        });
      }

      // Move to undo stack
      setRedoStack(prev => prev.filter(a => !actionsToRedo.includes(a)));
      setUndoStack(prev => [...updatedActions, ...prev].slice(0, maxStackSize));

      // Callbacks
      updatedActions.forEach(a => onRedo?.(a));

      if (showToasts) {
        const count = updatedActions.length;
        toast.success(
          count > 1
            ? `${count} Aktionen wiederholt`
            : 'Wiederholt',
          { description: firstAction.description }
        );
      }
    } catch (error) {
      toast.error('Wiederholen fehlgeschlagen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    } finally {
      isRedoingRef.current = false;
      setIsRedoing(false);
    }
  }, [redoStack, maxStackSize, showToasts, onRedo]);

  /**
   * Clear all history
   */
  const clearHistory = useCallback(() => {
    setUndoStack([]);
    setRedoStack([]);
  }, []);

  /**
   * Get keyboard shortcuts for registration
   */
  const getKeyboardShortcuts = useCallback((): KeyboardShortcut[] => {
    return [
      {
        id: 'undo',
        description: 'Rückgängig machen',
        keys: 'ctrl+z',
        category: 'actions',
        handler: undo,
        enabled: undoStack.length > 0 && !isUndoing && !isRedoing,
      },
      {
        id: 'redo',
        description: 'Wiederholen',
        keys: 'ctrl+y',
        category: 'actions',
        handler: redo,
        enabled: redoStack.length > 0 && !isUndoing && !isRedoing,
      },
      {
        id: 'redo-alt',
        description: 'Wiederholen (alternativ)',
        keys: 'ctrl+shift+z',
        category: 'actions',
        handler: redo,
        enabled: redoStack.length > 0 && !isUndoing && !isRedoing,
      },
    ];
  }, [undo, redo, undoStack.length, redoStack.length, isUndoing, isRedoing]);

  // Register keyboard shortcuts if enabled
  const undoShortcut: KeyboardShortcut | null = enableKeyboardShortcuts ? {
    id: 'undo-redo-undo',
    description: 'Rückgängig machen',
    keys: 'ctrl+z',
    category: 'actions',
    handler: undo,
    enabled: true,
  } : null;

  const redoShortcut: KeyboardShortcut | null = enableKeyboardShortcuts ? {
    id: 'undo-redo-redo',
    description: 'Wiederholen',
    keys: 'ctrl+y',
    category: 'actions',
    handler: redo,
    enabled: true,
  } : null;

  useRegisterShortcut(undoShortcut);
  useRegisterShortcut(redoShortcut);

  return {
    executeAction,
    executeGroupedAction,
    undo,
    redo,
    canUndo: undoStack.length > 0 && !isUndoing && !isRedoing,
    canRedo: redoStack.length > 0 && !isUndoing && !isRedoing,
    undoStack,
    redoStack,
    clearHistory,
    isUndoing,
    isRedoing,
    getKeyboardShortcuts,
  };
}

// ==================== Context ====================

const UndoRedoContext = createContext<UseUndoRedoReturn | null>(null);

/**
 * Provider for global undo/redo functionality
 */
export function UndoRedoProvider({
  children,
  options,
}: {
  children: ReactNode;
  options?: UseUndoRedoOptions;
}) {
  const undoRedo = useUndoRedo(options);

  return (
    <UndoRedoContext.Provider value={undoRedo}>
      {children}
    </UndoRedoContext.Provider>
  );
}

/**
 * Hook to access global undo/redo context
 */
export function useGlobalUndoRedo(): UseUndoRedoReturn {
  const context = useContext(UndoRedoContext);
  if (!context) {
    throw new Error('useGlobalUndoRedo must be used within UndoRedoProvider');
  }
  return context;
}

// ==================== Exports ====================

export type { UndoableAction, ActionDefinition, UseUndoRedoOptions, UseUndoRedoReturn };
export default useUndoRedo;
