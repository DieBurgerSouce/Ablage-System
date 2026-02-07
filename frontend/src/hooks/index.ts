/**
 * Hooks barrel export file
 *
 * Central export point for all custom hooks in the application.
 */

// Keyboard shortcuts
export {
  useKeyboardShortcuts,
  useGlobalShortcuts,
  useShortcutsContext,
  useShortcutsState,
  useRegisterShortcut,
  useRegisterShortcuts,
  useRegisterSequence,
  useShortcutScope,
  GlobalShortcutsProvider,
  formatShortcutKeys,
  formatKeySequence,
  matchesShortcut,
  getShortcutsState,
  SHORTCUT_CATEGORY_LABELS,
  SHORTCUT_LABELS,
  type KeyboardShortcut,
  type KeySequence,
  type ShortcutScope,
  type ShortcutCategory,
  type ShortcutsContextValue,
} from './useKeyboardShortcuts';

// Document shortcuts
export {
  useDocumentShortcuts,
  useFormShortcuts,
  type UseDocumentShortcutsOptions,
  type UseDocumentShortcutsReturn,
  type UseFormShortcutsOptions,
  type UseFormShortcutsReturn,
} from './useDocumentShortcuts';

// Undo/Redo
export {
  useUndoRedo,
  useGlobalUndoRedo,
  UndoRedoProvider,
  type UndoableAction,
  type ActionDefinition,
  type UseUndoRedoOptions,
  type UseUndoRedoReturn,
} from './useUndoRedo';

// Undoable action (legacy)
export {
  useUndoableAction,
  useGlobalUndo,
  UndoProvider,
} from './useUndoableAction';

// Other hooks
export { useDebounce } from './use-debounce';
export { useToast } from './use-toast';
export { useBulkSelection, useBatchProgress, executeBatch } from './use-bulk-selection';
export { useUnsavedChanges } from './useUnsavedChanges';
export { useOptimisticMutation } from './useOptimisticMutation';
export { useStatusBadge } from './useStatusBadge';
export { useAppInstallPrompt } from './use-app-install-prompt';
export { useResponsiveGrid } from './use-responsive-grid';
export { useSwipeGesture } from './use-swipe-gesture';
export { useMobileGestures } from './use-mobile-gestures';
export { useWidgetSubscription } from './use-widget-subscription';

// Drag and Drop
export {
  useDragAndDrop,
  useSortableDrag,
  useDroppable,
  useDraggable,
  type DragItemType,
  type DragItem,
  type DropTarget,
  type DragState,
  type UseDragAndDropOptions,
  type UseDragAndDropReturn,
  type SortableItem,
  type UseSortableDragOptions,
  type UseSortableDragReturn,
  type UseDroppableOptions,
  type UseDroppableReturn,
  type UseDraggableOptions,
  type UseDraggableReturn,
  type DocumentDragData,
  type FolderDropData,
  type WidgetDragData,
} from './useDragAndDrop';

// Notification Navigation (Phase 8)
export {
  useNotificationNavigation,
  type NotificationClickData,
  type UseNotificationNavigationOptions,
} from './use-notification-navigation';

// Online/Offline Status
export {
  useOnlineStatus,
  type OnlineStatus,
} from './use-online-status';
