/**
 * useKeyboardShortcuts - Comprehensive Keyboard Shortcuts System
 *
 * Features:
 * - Modifier keys support (Ctrl, Alt, Shift, Meta)
 * - Context-aware shortcuts (global, document-view, list-view)
 * - Key sequence support (e.g., 'g' then 'd' for go to dashboard)
 * - Conflict detection and resolution
 * - Dynamic registration/unregistration
 * - Prevention of native browser shortcut conflicts
 * - Accessible and screen reader compatible
 *
 * WCAG 2.1 AA konform
 */

import { useEffect, useState, useCallback, useRef, createContext, useContext, type ReactNode } from 'react';
import { logger } from '@/lib/logger';
import { useNavigate } from '@tanstack/react-router';

// ==================== Types ====================

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
 * Shortcuts context state
 */
export interface ShortcutsContextState {
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
}

/**
 * Shortcuts context actions
 */
export interface ShortcutsContextActions {
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
  /** Clear pending sequence */
  clearSequence: () => void;
  /** Check if a shortcut key is registered */
  isShortcutRegistered: (keys: string) => boolean;
}

export type ShortcutsContextValue = ShortcutsContextState & ShortcutsContextActions;

// ==================== Constants ====================

/**
 * Browser shortcuts that should not be overridden
 */
const PROTECTED_SHORTCUTS = new Set([
  'ctrl+c', 'ctrl+v', 'ctrl+x', // Copy, paste, cut
  'ctrl+a',                      // Select all (context-dependent)
  'ctrl+f',                      // Find
  'ctrl+p',                      // Print
  'ctrl+t', 'ctrl+n', 'ctrl+w', // Browser tabs
  'ctrl+r', 'ctrl+shift+r',     // Reload
  'f5', 'f12',                   // Reload, DevTools
  'alt+f4',                      // Close window
]);

/**
 * Default sequence timeout in milliseconds
 */
const DEFAULT_SEQUENCE_TIMEOUT = 1000;

// ==================== Utilities ====================

/**
 * Normalize a key combination string for comparison
 */
function normalizeKeys(keys: string): string {
  return keys
    .toLowerCase()
    .split('+')
    .map(part => {
      const trimmed = part.trim();
      if (trimmed === 'cmd') return 'ctrl'; // Normalize cmd to ctrl
      if (trimmed === 'command') return 'ctrl';
      if (trimmed === 'meta') return 'ctrl';
      if (trimmed === 'esc') return 'escape';
      return trimmed;
    })
    .sort((a, b) => {
      // Sort modifiers first, then the main key
      const order: Record<string, number> = { ctrl: 1, alt: 2, shift: 3 };
      return (order[a] ?? 99) - (order[b] ?? 99);
    })
    .join('+');
}

/**
 * Parse key combination string into event matcher
 */
export function matchesShortcut(event: KeyboardEvent, keys: string): boolean {
  const parts = keys.toLowerCase().split('+');
  const mainKey = parts.filter(p => !['ctrl', 'cmd', 'alt', 'shift', 'meta'].includes(p.trim()))[0];
  const needsCtrl = parts.some(p => ['ctrl', 'cmd', 'meta'].includes(p.trim()));
  const needsAlt = parts.includes('alt');
  const needsShift = parts.includes('shift');

  // Check modifiers - must match exactly
  const ctrlMatch = needsCtrl ? (event.ctrlKey || event.metaKey) : !(event.ctrlKey || event.metaKey);
  const altMatch = needsAlt ? event.altKey : !event.altKey;

  // For question mark, shift is inherent to the key
  if (mainKey === '?') {
    const keyMatch = event.key === '?';
    return ctrlMatch && altMatch && keyMatch;
  }

  const shiftMatch = needsShift ? event.shiftKey : !event.shiftKey;

  // Handle special keys
  let keyMatch = false;
  const key = mainKey?.toLowerCase();

  if (!key) return false;

  switch (key) {
    case 'escape':
    case 'esc':
      keyMatch = event.key === 'Escape';
      break;
    case 'enter':
      keyMatch = event.key === 'Enter';
      break;
    case 'space':
      keyMatch = event.key === ' ' || event.code === 'Space';
      break;
    case 'backspace':
      keyMatch = event.key === 'Backspace';
      break;
    case 'delete':
      keyMatch = event.key === 'Delete';
      break;
    case 'tab':
      keyMatch = event.key === 'Tab';
      break;
    case 'arrowup':
    case 'up':
      keyMatch = event.key === 'ArrowUp';
      break;
    case 'arrowdown':
    case 'down':
      keyMatch = event.key === 'ArrowDown';
      break;
    case 'arrowleft':
    case 'left':
      keyMatch = event.key === 'ArrowLeft';
      break;
    case 'arrowright':
    case 'right':
      keyMatch = event.key === 'ArrowRight';
      break;
    case 'home':
      keyMatch = event.key === 'Home';
      break;
    case 'end':
      keyMatch = event.key === 'End';
      break;
    case '/':
      // Forward slash - check both key and code for keyboard layouts
      keyMatch = event.key === '/' || event.code === 'Slash';
      break;
    default:
      keyMatch = event.key.toLowerCase() === key;
  }

  return ctrlMatch && altMatch && shiftMatch && keyMatch;
}

/**
 * Check if the target element is an input field
 */
function isInputElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  const tagName = target.tagName.toLowerCase();
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    tagName === 'select' ||
    target.isContentEditable ||
    target.getAttribute('role') === 'textbox'
  );
}

/**
 * Format shortcut keys for display
 */
export function formatShortcutKeys(keys: string): string {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform);

  return keys
    .split('+')
    .map(part => {
      const lower = part.toLowerCase().trim();
      if (lower === 'ctrl' || lower === 'cmd' || lower === 'meta') return isMac ? '⌘' : 'Ctrl';
      if (lower === 'alt') return isMac ? '⌥' : 'Alt';
      if (lower === 'shift') return '⇧';
      if (lower === 'escape' || lower === 'esc') return 'Esc';
      if (lower === 'enter') return '↵';
      if (lower === 'space') return 'Leertaste';
      if (lower === 'backspace') return '⌫';
      if (lower === 'delete') return isMac ? '⌦' : 'Entf';
      if (lower === 'tab') return '⇥';
      if (lower === 'arrowup' || lower === 'up') return '↑';
      if (lower === 'arrowdown' || lower === 'down') return '↓';
      if (lower === 'arrowleft' || lower === 'left') return '←';
      if (lower === 'arrowright' || lower === 'right') return '→';
      if (lower === 'home') return 'Pos1';
      if (lower === 'end') return 'Ende';
      if (lower === '/') return '/';
      return part.toUpperCase();
    })
    .join(' + ');
}

/**
 * Format key sequence for display
 */
export function formatKeySequence(sequence: string[]): string {
  return sequence.map(key => formatShortcutKeys(key)).join(' → ');
}

// ==================== Context ====================

const ShortcutsContext = createContext<ShortcutsContextValue | null>(null);

// ==================== Provider ====================

interface GlobalShortcutsProviderProps {
  children: ReactNode;
  /** Initial shortcuts to register */
  initialShortcuts?: KeyboardShortcut[];
  /** Initial sequences to register */
  initialSequences?: KeySequence[];
}

export function GlobalShortcutsProvider({
  children,
  initialShortcuts = [],
  initialSequences = [],
}: GlobalShortcutsProviderProps) {
  const [isHelpOpen, setHelpOpen] = useState(false);
  const [activeScope, setActiveScope] = useState<ShortcutScope>('global');
  const [shortcuts, setShortcuts] = useState<KeyboardShortcut[]>(initialShortcuts);
  const [sequences, setSequences] = useState<KeySequence[]>(initialSequences);
  const [pendingSequence, setPendingSequence] = useState<string[]>([]);

  const sequenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear sequence timeout
  const clearSequence = useCallback(() => {
    setPendingSequence([]);
    if (sequenceTimeoutRef.current) {
      clearTimeout(sequenceTimeoutRef.current);
      sequenceTimeoutRef.current = null;
    }
  }, []);

  // Register a new shortcut
  const registerShortcut = useCallback((shortcut: KeyboardShortcut) => {
    setShortcuts(prev => {
      // Check for conflicts
      const normalizedKeys = normalizeKeys(shortcut.keys);
      const conflict = prev.find(s =>
        normalizeKeys(s.keys) === normalizedKeys &&
        s.id !== shortcut.id &&
        (s.scope === shortcut.scope || s.scope === 'global' || shortcut.scope === 'global')
      );

      if (conflict) {
        // Keep the one with higher priority
        const conflictPriority = conflict.priority ?? 0;
        const newPriority = shortcut.priority ?? 0;

        if (newPriority <= conflictPriority) {
          logger.warn(`[Shortcuts] Conflict: ${shortcut.id} vs ${conflict.id} for keys ${shortcut.keys}. Keeping ${conflict.id}`);
          return prev;
        }

        // Remove the old one
        logger.warn(`[Shortcuts] Conflict: ${shortcut.id} vs ${conflict.id} for keys ${shortcut.keys}. Replacing with ${shortcut.id}`);
        return [...prev.filter(s => s.id !== conflict.id), shortcut];
      }

      // Remove existing if same ID (update case)
      const filtered = prev.filter(s => s.id !== shortcut.id);
      return [...filtered, shortcut];
    });
  }, []);

  // Unregister a shortcut
  const unregisterShortcut = useCallback((id: string) => {
    setShortcuts(prev => prev.filter(s => s.id !== id));
  }, []);

  // Register a sequence
  const registerSequence = useCallback((sequence: KeySequence) => {
    setSequences(prev => {
      const filtered = prev.filter(s => s.id !== sequence.id);
      return [...filtered, sequence];
    });
  }, []);

  // Unregister a sequence
  const unregisterSequence = useCallback((id: string) => {
    setSequences(prev => prev.filter(s => s.id !== id));
  }, []);

  // Check if a shortcut is registered
  const isShortcutRegistered = useCallback((keys: string) => {
    const normalizedKeys = normalizeKeys(keys);
    return shortcuts.some(s => normalizeKeys(s.keys) === normalizedKeys);
  }, [shortcuts]);

  // Handle keyboard events
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const isTyping = isInputElement(target);

      // Process sequences first (only when not typing)
      if (!isTyping && sequences.length > 0) {
        const eventKey = event.key.toLowerCase();
        const newSequence = [...pendingSequence, eventKey];

        // Check for matching sequence
        const matchedSequence = sequences.find(seq => {
          if (seq.enabled === false) return false;
          if (seq.sequence.length !== newSequence.length) return false;
          return seq.sequence.every((k, i) => k.toLowerCase() === newSequence[i]);
        });

        if (matchedSequence) {
          event.preventDefault();
          clearSequence();
          matchedSequence.handler();
          return;
        }

        // Check for partial match
        const partialMatch = sequences.some(seq => {
          if (seq.enabled === false) return false;
          if (seq.sequence.length <= newSequence.length) return false;
          return seq.sequence.slice(0, newSequence.length).every((k, i) => k.toLowerCase() === newSequence[i]);
        });

        if (partialMatch) {
          setPendingSequence(newSequence);

          // Set timeout to clear sequence
          if (sequenceTimeoutRef.current) {
            clearTimeout(sequenceTimeoutRef.current);
          }
          const timeout = sequences[0]?.timeout ?? DEFAULT_SEQUENCE_TIMEOUT;
          sequenceTimeoutRef.current = setTimeout(clearSequence, timeout);

          // Don't prevent default for first key of sequence (allows typing)
          return;
        }

        // No match - clear pending sequence
        if (pendingSequence.length > 0) {
          clearSequence();
        }
      }

      // Process single-key shortcuts
      for (const shortcut of shortcuts) {
        if (shortcut.enabled === false) continue;

        // Skip if scope doesn't match
        if (shortcut.scope && shortcut.scope !== 'global' && shortcut.scope !== activeScope) {
          continue;
        }

        if (matchesShortcut(event, shortcut.keys)) {
          // Skip protected browser shortcuts
          if (PROTECTED_SHORTCUTS.has(normalizeKeys(shortcut.keys))) {
            continue;
          }

          // Special handling for ? - allow even when typing (for help)
          // Special handling for Escape - allow in forms/modals
          const allowInInput = shortcut.keys === '?' || shortcut.keys.toLowerCase() === 'escape';

          if (isTyping && !allowInInput) {
            continue;
          }

          if (shortcut.preventDefault !== false) {
            event.preventDefault();
          }

          if (shortcut.stopPropagation) {
            event.stopPropagation();
          }

          shortcut.handler();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts, sequences, pendingSequence, activeScope, clearSequence]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (sequenceTimeoutRef.current) {
        clearTimeout(sequenceTimeoutRef.current);
      }
    };
  }, []);

  const value: ShortcutsContextValue = {
    isHelpOpen,
    activeScope,
    pendingSequence,
    shortcuts,
    sequences,
    setHelpOpen,
    setActiveScope,
    registerShortcut,
    unregisterShortcut,
    registerSequence,
    unregisterSequence,
    clearSequence,
    isShortcutRegistered,
  };

  return (
    <ShortcutsContext.Provider value={value}>
      {children}
    </ShortcutsContext.Provider>
  );
}

// ==================== Hooks ====================

/**
 * Hook to access the shortcuts context
 */
export function useShortcutsContext(): ShortcutsContextValue {
  const context = useContext(ShortcutsContext);
  if (!context) {
    throw new Error('useShortcutsContext must be used within GlobalShortcutsProvider');
  }
  return context;
}

/**
 * Hook to register and handle keyboard shortcuts
 * Can be used standalone or within the GlobalShortcutsProvider
 */
export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const isTyping = isInputElement(target);

      for (const shortcut of shortcuts) {
        if (shortcut.enabled === false) continue;

        if (matchesShortcut(event, shortcut.keys)) {
          // Allow ? shortcut even when typing (for help)
          const allowInInput = shortcut.keys === '?' || shortcut.keys.toLowerCase() === 'escape';

          if (isTyping && !allowInInput) continue;

          event.preventDefault();
          shortcut.handler();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}

/**
 * Hook to register a single shortcut dynamically
 */
export function useRegisterShortcut(shortcut: KeyboardShortcut | null) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!shortcut || !context) return;

    context.registerShortcut(shortcut);
    return () => context.unregisterShortcut(shortcut.id);
  }, [shortcut, context]);
}

/**
 * Hook to register multiple shortcuts dynamically
 */
export function useRegisterShortcuts(shortcutsToRegister: KeyboardShortcut[]) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!context || shortcutsToRegister.length === 0) return;

    shortcutsToRegister.forEach(s => context.registerShortcut(s));
    return () => shortcutsToRegister.forEach(s => context.unregisterShortcut(s.id));
  }, [shortcutsToRegister, context]);
}

/**
 * Hook to register a key sequence dynamically
 */
export function useRegisterSequence(sequence: KeySequence | null) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!sequence || !context) return;

    context.registerSequence(sequence);
    return () => context.unregisterSequence(sequence.id);
  }, [sequence, context]);
}

/**
 * Hook to set the active shortcut scope
 */
export function useShortcutScope(scope: ShortcutScope) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!context) return;

    const previousScope = context.activeScope;
    context.setActiveScope(scope);

    return () => {
      // Only reset if we're still the current scope
      if (context.activeScope === scope) {
        context.setActiveScope(previousScope);
      }
    };
  }, [scope, context]);
}

/**
 * Hook to manage global shortcuts state (legacy compatibility)
 */
export function useShortcutsState() {
  const [isHelpOpen, setHelpOpen] = useState(false);
  return { isHelpOpen, setHelpOpen };
}

/**
 * Get current shortcuts state (for use in handlers - legacy compatibility)
 */
let globalState: { isHelpOpen: boolean; setHelpOpen: (open: boolean) => void } | null = null;

export function getShortcutsState() {
  return globalState;
}

/**
 * Hook providing default application shortcuts
 */
export function useGlobalShortcuts() {
  const navigate = useNavigate();
  const [isHelpOpen, setHelpOpen] = useState(false);

  // Store in global state for access from shortcuts
  globalState = { isHelpOpen, setHelpOpen };

  const shortcuts: KeyboardShortcut[] = [
    // Navigation
    {
      id: 'go-home',
      description: 'Zur Startseite',
      keys: 'alt+h',
      category: 'navigation',
      handler: () => navigate({ to: '/' }),
    },
    {
      id: 'go-search',
      description: 'Suche fokussieren',
      keys: '/',
      category: 'navigation',
      handler: () => {
        const searchInput = document.querySelector('[data-search-input]') as HTMLInputElement;
        if (searchInput) {
          searchInput.focus();
        }
      },
    },
    {
      id: 'go-command',
      description: 'Befehlspalette öffnen',
      keys: 'ctrl+k',
      category: 'navigation',
      handler: () => {
        // Dispatch custom event to open command dialog
        window.dispatchEvent(new CustomEvent('open-command-dialog'));
      },
    },
    {
      id: 'go-upload',
      description: 'Zum Upload',
      keys: 'ctrl+u',
      category: 'navigation',
      handler: () => navigate({ to: '/upload' }),
    },

    // Help
    {
      id: 'show-help',
      description: 'Tastenkürzel anzeigen',
      keys: '?',
      category: 'help',
      handler: () => setHelpOpen(true),
    },
    {
      id: 'close-modal',
      description: 'Dialog schließen',
      keys: 'escape',
      category: 'help',
      handler: () => {
        // Close help modal if open
        if (isHelpOpen) {
          setHelpOpen(false);
          return;
        }
        // Dispatch close event for other modals
        window.dispatchEvent(new CustomEvent('close-modal'));
      },
    },
  ];

  useKeyboardShortcuts(shortcuts);

  return {
    shortcuts,
    isHelpOpen,
    setHelpOpen,
  };
}

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
  delete: 'Löschen',
  move: 'Verschieben',
  undo: 'Rückgängig',
  redo: 'Wiederholen',
  search: 'Suche',
  help: 'Hilfe',
  save: 'Speichern',
  submit: 'Absenden',
  cancel: 'Abbrechen',
  navigation: 'Navigation',
  actions: 'Aktionen',
  close: 'Schließen',
  select_all: 'Alle auswählen',
  deselect: 'Auswahl aufheben',
  copy: 'Kopieren',
  paste: 'Einfügen',
  cut: 'Ausschneiden',
} as const;

// Typen sind bereits an ihrer Deklaration exportiert (kein Re-Export noetig).
