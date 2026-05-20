/**
 * Shortcuts Feature - Keyboard Shortcuts System
 *
 * Provides a comprehensive keyboard shortcuts system including:
 * - Global shortcuts that work anywhere
 * - Key sequences (e.g., 'g d' for go to dashboard)
 * - Command palette (Cmd+K / Ctrl+K)
 * - Help modal showing all shortcuts
 * - User customizations stored in localStorage
 *
 * Usage:
 * ```tsx
 * // Wrap your app with ShortcutsProvider
 * import { ShortcutsProvider } from '@/features/shortcuts';
 *
 * <ShortcutsProvider>
 *   <App />
 * </ShortcutsProvider>
 *
 * // Use shortcuts context anywhere
 * import { useShortcutsContext } from '@/features/shortcuts';
 *
 * const { isCommandPaletteOpen, setCommandPaletteOpen } = useShortcutsContext();
 *
 * // Register custom shortcuts
 * import { useRegisterShortcut } from '@/features/shortcuts';
 *
 * useRegisterShortcut({
 *   id: 'my-shortcut',
 *   description: 'Mein Shortcut',
 *   keys: 'ctrl+shift+m',
 *   category: 'actions',
 *   handler: () => console.log('Triggered!'),
 * });
 * ```
 *
 * WCAG 2.1 AA konform - Alle Labels auf Deutsch
 */

// ==================== Main Provider ====================

export { ShortcutsProvider } from './ShortcutsProvider';
export { default as ShortcutsProviderDefault } from './ShortcutsProvider';

// ==================== Context ====================

export {
  ShortcutsContextProvider,
  useShortcutsContext,
  useRegisterShortcut,
  useRegisterShortcuts,
  useRegisterSequence,
  useRegisterSequences,
  useRegisterCommand,
  useRegisterCommands,
  useShortcutScope,
} from './context/ShortcutsContext';

// ==================== Hooks ====================

export {
  useHotkey,
  useHotkeys,
  useKeySequence,
  useCombinedHotkeys,
  useScopedHotkeys,
  formatShortcutKeys,
  formatKeySequence,
  normalizeKeys,
  matchesShortcut,
  isInputElement,
} from './hooks/useHotkeys';

// ==================== Components ====================

export { CommandPalette } from './components/CommandPalette';
export {
  ShortcutsHelpModal,
  ShortcutBadge,
  SequenceBadge,
  ShortcutHint,
  PendingSequenceIndicator,
} from './components/ShortcutsHelpModal';

// ==================== Types ====================

export type {
  KeyboardShortcut,
  KeySequence,
  CommandItem,
  ShortcutScope,
  ShortcutCategory,
  ShortcutsContextValue,
  ShortcutsContextState,
  ShortcutsContextActions,
  ShortcutsUserPreferences,
  RecentCommand,
  ShortcutCustomization,
} from './types/shortcut-types';

export {
  SHORTCUT_CATEGORY_LABELS,
  SHORTCUT_LABELS,
  DEFAULT_SEQUENCE_TIMEOUT,
  MAX_RECENT_COMMANDS,
  SHORTCUTS_STORAGE_KEY,
  PROTECTED_SHORTCUTS,
} from './types/shortcut-types';
