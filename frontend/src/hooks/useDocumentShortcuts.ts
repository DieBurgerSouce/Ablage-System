/**
 * useDocumentShortcuts - Keyboard Shortcuts for Document List Views
 *
 * Provides keyboard shortcuts specifically for document list/grid views:
 * - Ctrl+D: Delete selected documents
 * - Ctrl+M: Move selected documents
 * - Ctrl+A: Select all documents
 * - Escape: Clear selection
 * - Arrow keys: Navigate in list
 * - Enter: Open selected document
 * - Space: Toggle selection
 *
 * Usage:
 * ```tsx
 * const { handlers, shortcuts } = useDocumentShortcuts({
 *   selectedIds: selection.selectedIds,
 *   documentIds: documents.map(d => d.id),
 *   onDelete: handleDelete,
 *   onMove: handleMove,
 *   onSelectAll: handleSelectAll,
 *   onClearSelection: handleClearSelection,
 *   onOpen: handleOpen,
 *   onToggleSelect: handleToggle,
 * });
 *
 * // Listen for events
 * useEffect(() => handlers.subscribe(), [handlers]);
 * ```
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useShortcutScope, useRegisterShortcuts, type KeyboardShortcut } from './useKeyboardShortcuts';

// ==================== Types ====================

export interface UseDocumentShortcutsOptions {
  /** Currently selected document IDs */
  selectedIds: string[];
  /** All document IDs in the current view */
  documentIds: string[];
  /** Handler for delete action */
  onDelete?: (ids: string[]) => void;
  /** Handler for move action */
  onMove?: (ids: string[]) => void;
  /** Handler for select all */
  onSelectAll?: () => void;
  /** Handler for clear selection */
  onClearSelection?: () => void;
  /** Handler for opening a document */
  onOpen?: (id: string) => void;
  /** Handler for toggling selection */
  onToggleSelect?: (id: string) => void;
  /** Handler for range selection (Shift+Click) */
  onRangeSelect?: (fromId: string, toId: string) => void;
  /** Currently focused document index */
  focusedIndex?: number;
  /** Set focused document index */
  onFocusChange?: (index: number) => void;
  /** Number of columns in grid view (1 for list) */
  columnCount?: number;
  /** Whether shortcuts are enabled */
  enabled?: boolean;
}

export interface UseDocumentShortcutsReturn {
  /** Event handlers for shortcut events */
  handlers: {
    subscribe: () => () => void;
  };
  /** Registered shortcuts for display in help modal */
  shortcuts: KeyboardShortcut[];
  /** Currently focused document index */
  focusedIndex: number;
  /** Set focused document index */
  setFocusedIndex: (index: number) => void;
  /** Move focus to next/previous item */
  moveFocus: (direction: 'up' | 'down' | 'left' | 'right') => void;
  /** Select the focused item */
  selectFocused: () => void;
  /** Open the focused item */
  openFocused: () => void;
}

// ==================== Hook ====================

export function useDocumentShortcuts(options: UseDocumentShortcutsOptions): UseDocumentShortcutsReturn {
  const {
    selectedIds,
    documentIds,
    onDelete,
    onMove,
    onSelectAll,
    onClearSelection,
    onOpen,
    onToggleSelect,
    onRangeSelect,
    focusedIndex: externalFocusedIndex = -1,
    onFocusChange,
    columnCount = 1,
    enabled = true,
  } = options;

  // Internal focused index if not controlled externally
  const internalFocusedIndexRef = useRef(externalFocusedIndex);
  const focusedIndex = externalFocusedIndex >= 0 ? externalFocusedIndex : internalFocusedIndexRef.current;

  // Ref for range selection start
  const rangeStartRef = useRef<number>(-1);

  // Set active scope
  useShortcutScope('list-view');

  // Set focused index
  const setFocusedIndex = useCallback((index: number) => {
    const clampedIndex = Math.max(-1, Math.min(index, documentIds.length - 1));
    if (onFocusChange) {
      onFocusChange(clampedIndex);
    } else {
      internalFocusedIndexRef.current = clampedIndex;
    }
  }, [documentIds.length, onFocusChange]);

  // Move focus in a direction
  const moveFocus = useCallback((direction: 'up' | 'down' | 'left' | 'right') => {
    if (documentIds.length === 0) return;

    let newIndex = focusedIndex;
    const isGrid = columnCount > 1;

    switch (direction) {
      case 'up':
        newIndex = isGrid ? focusedIndex - columnCount : focusedIndex - 1;
        break;
      case 'down':
        newIndex = isGrid ? focusedIndex + columnCount : focusedIndex + 1;
        break;
      case 'left':
        if (isGrid) {
          newIndex = focusedIndex - 1;
        }
        break;
      case 'right':
        if (isGrid) {
          newIndex = focusedIndex + 1;
        }
        break;
    }

    // Initialize to first item if nothing focused
    if (focusedIndex < 0) {
      newIndex = 0;
    }

    // Clamp to valid range
    newIndex = Math.max(0, Math.min(newIndex, documentIds.length - 1));
    setFocusedIndex(newIndex);
  }, [focusedIndex, documentIds.length, columnCount, setFocusedIndex]);

  // Select the focused item
  const selectFocused = useCallback(() => {
    if (focusedIndex >= 0 && focusedIndex < documentIds.length) {
      const id = documentIds[focusedIndex];
      onToggleSelect?.(id);
      rangeStartRef.current = focusedIndex;
    }
  }, [focusedIndex, documentIds, onToggleSelect]);

  // Open the focused item
  const openFocused = useCallback(() => {
    if (focusedIndex >= 0 && focusedIndex < documentIds.length) {
      const id = documentIds[focusedIndex];
      onOpen?.(id);
    }
  }, [focusedIndex, documentIds, onOpen]);

  // Handle delete shortcut event
  const handleDelete = useCallback(() => {
    if (selectedIds.length > 0 && onDelete) {
      onDelete(selectedIds);
    }
  }, [selectedIds, onDelete]);

  // Handle move shortcut event
  const handleMove = useCallback(() => {
    if (selectedIds.length > 0 && onMove) {
      onMove(selectedIds);
    }
  }, [selectedIds, onMove]);

  // Create event subscription
  const subscribe = useCallback(() => {
    const handleShortcutDelete = () => handleDelete();
    const handleShortcutMove = () => handleMove();
    const handleShortcutSelectAll = () => onSelectAll?.();
    const handleShortcutEscape = () => {
      if (selectedIds.length > 0) {
        onClearSelection?.();
      }
    };

    window.addEventListener('shortcut-delete', handleShortcutDelete);
    window.addEventListener('shortcut-move', handleShortcutMove);
    window.addEventListener('shortcut-select-all', handleShortcutSelectAll);
    window.addEventListener('shortcut-escape', handleShortcutEscape);

    return () => {
      window.removeEventListener('shortcut-delete', handleShortcutDelete);
      window.removeEventListener('shortcut-move', handleShortcutMove);
      window.removeEventListener('shortcut-select-all', handleShortcutSelectAll);
      window.removeEventListener('shortcut-escape', handleShortcutEscape);
    };
  }, [handleDelete, handleMove, onSelectAll, onClearSelection, selectedIds.length]);

  // Define shortcuts for registration and display
  const shortcuts = useMemo<KeyboardShortcut[]>(() => {
    if (!enabled) return [];

    return [
      // Arrow key navigation
      {
        id: 'doc-nav-up',
        description: 'Vorheriges Dokument',
        keys: 'arrowup',
        category: 'documents',
        scope: 'list-view',
        handler: () => moveFocus('up'),
      },
      {
        id: 'doc-nav-down',
        description: 'Nächstes Dokument',
        keys: 'arrowdown',
        category: 'documents',
        scope: 'list-view',
        handler: () => moveFocus('down'),
      },
      {
        id: 'doc-nav-left',
        description: 'Dokument links',
        keys: 'arrowleft',
        category: 'documents',
        scope: 'list-view',
        handler: () => moveFocus('left'),
        enabled: columnCount > 1,
      },
      {
        id: 'doc-nav-right',
        description: 'Dokument rechts',
        keys: 'arrowright',
        category: 'documents',
        scope: 'list-view',
        handler: () => moveFocus('right'),
        enabled: columnCount > 1,
      },
      {
        id: 'doc-nav-home',
        description: 'Erstes Dokument',
        keys: 'home',
        category: 'documents',
        scope: 'list-view',
        handler: () => setFocusedIndex(0),
      },
      {
        id: 'doc-nav-end',
        description: 'Letztes Dokument',
        keys: 'end',
        category: 'documents',
        scope: 'list-view',
        handler: () => setFocusedIndex(documentIds.length - 1),
      },
      // Selection
      {
        id: 'doc-select-toggle',
        description: 'Auswahl umschalten',
        keys: 'space',
        category: 'documents',
        scope: 'list-view',
        handler: selectFocused,
      },
      {
        id: 'doc-open',
        description: 'Dokument öffnen',
        keys: 'enter',
        category: 'documents',
        scope: 'list-view',
        handler: openFocused,
      },
    ];
  }, [enabled, moveFocus, setFocusedIndex, selectFocused, openFocused, columnCount, documentIds.length]);

  // Register shortcuts with the global context
  useRegisterShortcuts(shortcuts);

  return {
    handlers: { subscribe },
    shortcuts,
    focusedIndex,
    setFocusedIndex,
    moveFocus,
    selectFocused,
    openFocused,
  };
}

// ==================== Hook for Form Shortcuts ====================

export interface UseFormShortcutsOptions {
  /** Handler for save action */
  onSave?: () => void | Promise<void>;
  /** Handler for submit action */
  onSubmit?: () => void | Promise<void>;
  /** Handler for cancel action */
  onCancel?: () => void;
  /** Whether the form has unsaved changes */
  hasChanges?: boolean;
  /** Whether the form is valid */
  isValid?: boolean;
  /** Whether shortcuts are enabled */
  enabled?: boolean;
}

export interface UseFormShortcutsReturn {
  /** Event handlers for shortcut events */
  handlers: {
    subscribe: () => () => void;
  };
  /** Registered shortcuts for display in help modal */
  shortcuts: KeyboardShortcut[];
}

export function useFormShortcuts(options: UseFormShortcutsOptions): UseFormShortcutsReturn {
  const {
    onSave,
    onSubmit,
    onCancel,
    hasChanges = false,
    isValid = true,
    enabled = true,
  } = options;

  // Set active scope
  useShortcutScope('form');

  // Handle save
  const handleSave = useCallback(() => {
    if (hasChanges && onSave) {
      onSave();
    }
  }, [hasChanges, onSave]);

  // Handle submit
  const handleSubmit = useCallback(() => {
    if (isValid && onSubmit) {
      onSubmit();
    }
  }, [isValid, onSubmit]);

  // Create event subscription
  const subscribe = useCallback(() => {
    const handleShortcutSave = () => handleSave();
    const handleShortcutSubmit = () => handleSubmit();
    const handleShortcutEscape = () => onCancel?.();

    window.addEventListener('shortcut-save', handleShortcutSave);
    window.addEventListener('shortcut-submit', handleShortcutSubmit);
    window.addEventListener('shortcut-escape', handleShortcutEscape);

    return () => {
      window.removeEventListener('shortcut-save', handleShortcutSave);
      window.removeEventListener('shortcut-submit', handleShortcutSubmit);
      window.removeEventListener('shortcut-escape', handleShortcutEscape);
    };
  }, [handleSave, handleSubmit, onCancel]);

  // Define shortcuts for display
  const shortcuts = useMemo<KeyboardShortcut[]>(() => {
    if (!enabled) return [];

    return [
      {
        id: 'form-save-local',
        description: 'Formular speichern',
        keys: 'ctrl+s',
        category: 'forms',
        scope: 'form',
        handler: handleSave,
        enabled: hasChanges,
      },
      {
        id: 'form-submit-local',
        description: 'Formular absenden',
        keys: 'ctrl+enter',
        category: 'forms',
        scope: 'form',
        handler: handleSubmit,
        enabled: isValid,
      },
    ];
  }, [enabled, handleSave, handleSubmit, hasChanges, isValid]);

  return {
    handlers: { subscribe },
    shortcuts,
  };
}

// ==================== Exports ====================

export type { UseDocumentShortcutsOptions, UseDocumentShortcutsReturn, UseFormShortcutsOptions, UseFormShortcutsReturn };
export { useDocumentShortcuts, useFormShortcuts };
