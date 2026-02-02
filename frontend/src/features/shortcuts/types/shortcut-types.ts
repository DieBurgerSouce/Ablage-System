/**
 * Shortcut Types - Type definitions for the keyboard shortcuts system
 *
 * WCAG 2.1 AA konform - Alle Labels auf Deutsch
 */

import type { LucideIcon } from 'lucide-react';

// ==================== Core Types ====================

/**
 * Shortcut scope - determines where shortcuts are active
 */
export type ShortcutScope =
  | 'global'           // Available everywhere
  | 'document-view'    // Active in document detail views
  | 'list-view'        // Active in list/grid views
  | 'form'             // Active in forms
  | 'modal';           // Active when modals are open

/**
 * Shortcut category for grouping in help modal
 */
export type ShortcutCategory =
  | 'navigation'       // Navigation shortcuts
  | 'actions'          // Action shortcuts (delete, move, etc.)
  | 'documents'        // Document-specific shortcuts
  | 'forms'            // Form shortcuts
  | 'help';            // Help and meta shortcuts

/**
 * Command item for the command palette
 */
export interface CommandItem {
  /** Unique identifier */
  id: string;
  /** Display label (German) */
  label: string;
  /** Short description (German) */
  description?: string;
  /** Category for grouping */
  category: ShortcutCategory;
  /** Keyboard shortcut keys */
  keys?: string;
  /** Key sequence (e.g., ['g', 'd']) */
  sequence?: string[];
  /** Icon component */
  icon?: LucideIcon;
  /** Handler function */
  onSelect: () => void;
  /** Whether command is enabled */
  enabled?: boolean;
  /** Keywords for fuzzy search */
  keywords?: string[];
  /** Priority for sorting (higher = earlier) */
  priority?: number;
}

/**
 * Keyboard shortcut definition
 */
export interface KeyboardShortcut {
  /** Unique identifier for the shortcut */
  id: string;
  /** Human-readable description (German) */
  description: string;
  /**
   * Key combination (e.g., 'ctrl+k', 'alt+s', '?')
   * Supports: ctrl, alt, shift, meta/cmd, and any key
   */
  keys: string;
  /** Category for grouping in help modal */
  category: ShortcutCategory;
  /** Scope where this shortcut is active */
  scope?: ShortcutScope;
  /** Handler function */
  handler: () => void;
  /** Whether shortcut is enabled */
  enabled?: boolean;
  /** Priority for conflict resolution (higher wins) */
  priority?: number;
  /** Whether to prevent default browser behavior */
  preventDefault?: boolean;
  /** Whether to stop event propagation */
  stopPropagation?: boolean;
}

/**
 * Key sequence for multi-key shortcuts (e.g., 'g d' for go to dashboard)
 */
export interface KeySequence {
  /** Unique identifier */
  id: string;
  /** Description (German) */
  description: string;
  /** Array of keys in sequence (e.g., ['g', 'd']) */
  sequence: string[];
  /** Category for help modal */
  category: ShortcutCategory;
  /** Handler function */
  handler: () => void;
  /** Whether sequence is enabled */
  enabled?: boolean;
  /** Timeout in ms for sequence completion (default: 1000) */
  timeout?: number;
}

/**
 * Recent command entry for command palette history
 */
export interface RecentCommand {
  /** Command ID */
  commandId: string;
  /** Last used timestamp */
  lastUsed: number;
  /** Usage count */
  useCount: number;
}

/**
 * User shortcut customization
 */
export interface ShortcutCustomization {
  /** Original shortcut ID */
  shortcutId: string;
  /** Custom key binding (null = disabled) */
  customKeys: string | null;
  /** Whether customization is enabled */
  enabled: boolean;
}

/**
 * Shortcuts user preferences stored in localStorage
 */
export interface ShortcutsUserPreferences {
  /** Recently used commands (max 10) */
  recentCommands: RecentCommand[];
  /** Custom key bindings */
  customizations: ShortcutCustomization[];
  /** Whether to show shortcut hints in UI */
  showHints: boolean;
  /** Last shown help timestamp */
  lastHelpShown?: number;
}

// ==================== Context Types ====================

/**
 * Shortcuts context state
 */
export interface ShortcutsContextState {
  /** Whether command palette is open */
  isCommandPaletteOpen: boolean;
  /** Whether help modal is open */
  isHelpOpen: boolean;
  /** Current active scope */
  activeScope: ShortcutScope;
  /** Currently pressed sequence keys */
  pendingSequence: string[];
  /** Registered shortcuts */
  shortcuts: KeyboardShortcut[];
  /** Registered sequences */
  sequences: KeySequence[];
  /** Available commands for command palette */
  commands: CommandItem[];
  /** User preferences */
  preferences: ShortcutsUserPreferences;
}

/**
 * Shortcuts context actions
 */
export interface ShortcutsContextActions {
  /** Open/close command palette */
  setCommandPaletteOpen: (open: boolean) => void;
  /** Open/close help modal */
  setHelpOpen: (open: boolean) => void;
  /** Set active scope */
  setActiveScope: (scope: ShortcutScope) => void;
  /** Register a new shortcut */
  registerShortcut: (shortcut: KeyboardShortcut) => void;
  /** Unregister a shortcut by ID */
  unregisterShortcut: (id: string) => void;
  /** Register a key sequence */
  registerSequence: (sequence: KeySequence) => void;
  /** Unregister a sequence by ID */
  unregisterSequence: (id: string) => void;
  /** Register a command */
  registerCommand: (command: CommandItem) => void;
  /** Unregister a command by ID */
  unregisterCommand: (id: string) => void;
  /** Clear pending sequence */
  clearSequence: () => void;
  /** Check if a shortcut key is registered */
  isShortcutRegistered: (keys: string) => boolean;
  /** Execute a command */
  executeCommand: (commandId: string) => void;
  /** Track command usage */
  trackCommandUsage: (commandId: string) => void;
  /** Update user preferences */
  updatePreferences: (updates: Partial<ShortcutsUserPreferences>) => void;
  /** Customize a shortcut */
  customizeShortcut: (shortcutId: string, customKeys: string | null) => void;
  /** Reset all customizations */
  resetCustomizations: () => void;
}

export type ShortcutsContextValue = ShortcutsContextState & ShortcutsContextActions;

// ==================== German Labels ====================

/**
 * German labels for shortcut categories
 */
export const SHORTCUT_CATEGORY_LABELS: Record<ShortcutCategory, string> = {
  navigation: 'Navigation',
  actions: 'Aktionen',
  documents: 'Dokumente',
  forms: 'Formulare',
  help: 'Hilfe',
};

/**
 * German labels for common shortcuts
 */
export const SHORTCUT_LABELS = {
  delete: 'Loeschen',
  move: 'Verschieben',
  undo: 'Rueckgaengig',
  redo: 'Wiederholen',
  search: 'Suche',
  help: 'Hilfe',
  save: 'Speichern',
  submit: 'Absenden',
  cancel: 'Abbrechen',
  navigation: 'Navigation',
  actions: 'Aktionen',
  close: 'Schliessen',
  select_all: 'Alle auswaehlen',
  deselect: 'Auswahl aufheben',
  copy: 'Kopieren',
  paste: 'Einfuegen',
  cut: 'Ausschneiden',
  new: 'Neu erstellen',
  edit: 'Bearbeiten',
  open_command_palette: 'Befehlspalette oeffnen',
  focus_search: 'Suche fokussieren',
  show_shortcuts: 'Tastenkuerzel anzeigen',
} as const;

// ==================== Default Constants ====================

/**
 * Default sequence timeout in milliseconds
 */
export const DEFAULT_SEQUENCE_TIMEOUT = 1000;

/**
 * Maximum recent commands to store
 */
export const MAX_RECENT_COMMANDS = 10;

/**
 * LocalStorage key for user preferences
 */
export const SHORTCUTS_STORAGE_KEY = 'ablage-shortcuts-preferences';

/**
 * Browser shortcuts that should not be overridden
 */
export const PROTECTED_SHORTCUTS = new Set([
  'ctrl+c', 'ctrl+v', 'ctrl+x', // Copy, paste, cut
  'ctrl+a',                      // Select all (context-dependent)
  'ctrl+f',                      // Find
  'ctrl+p',                      // Print
  'ctrl+t', 'ctrl+n', 'ctrl+w', // Browser tabs
  'ctrl+r', 'ctrl+shift+r',     // Reload
  'f5', 'f12',                   // Reload, DevTools
  'alt+f4',                      // Close window
]);
