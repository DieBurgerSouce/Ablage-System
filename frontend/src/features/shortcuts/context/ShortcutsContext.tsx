/**
 * ShortcutsContext - Context for managing keyboard shortcuts state
 *
 * Features:
 * - Register/unregister shortcuts dynamically
 * - Key sequence support
 * - Command palette integration
 * - User customizations stored in localStorage
 * - Recent commands tracking
 *
 * WCAG 2.1 AA konform
 */

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from 'react';
import type { ShortcutsContextValue, KeyboardShortcut, KeySequence, CommandItem, ShortcutScope, ShortcutsUserPreferences, RecentCommand } from '../types/shortcut-types';
import {
  SHORTCUTS_STORAGE_KEY,
  MAX_RECENT_COMMANDS,
  DEFAULT_SEQUENCE_TIMEOUT,
  PROTECTED_SHORTCUTS,
} from '../types/shortcut-types';
import { matchesShortcut, normalizeKeys, isInputElement } from '../hooks/useHotkeys';
import { logger } from '@/lib/logger';

// ==================== Default Preferences ====================

const defaultPreferences: ShortcutsUserPreferences = {
  recentCommands: [],
  customizations: [],
  showHints: true,
};

// ==================== LocalStorage Helpers ====================

function loadPreferences(): ShortcutsUserPreferences {
  try {
    const stored = localStorage.getItem(SHORTCUTS_STORAGE_KEY);
    if (stored) {
      return { ...defaultPreferences, ...JSON.parse(stored) };
    }
  } catch (e) {
    logger.warn('[Shortcuts] Fehler beim Laden der Einstellungen:', e);
  }
  return defaultPreferences;
}

function savePreferences(preferences: ShortcutsUserPreferences): void {
  try {
    localStorage.setItem(SHORTCUTS_STORAGE_KEY, JSON.stringify(preferences));
  } catch (e) {
    logger.warn('[Shortcuts] Fehler beim Speichern der Einstellungen:', e);
  }
}

// ==================== Context ====================

const ShortcutsContext = createContext<ShortcutsContextValue | null>(null);

// ==================== Provider ====================

interface ShortcutsContextProviderProps {
  children: ReactNode;
  /** Initial shortcuts to register */
  initialShortcuts?: KeyboardShortcut[];
  /** Initial sequences to register */
  initialSequences?: KeySequence[];
  /** Initial commands to register */
  initialCommands?: CommandItem[];
}

export function ShortcutsContextProvider({
  children,
  initialShortcuts = [],
  initialSequences = [],
  initialCommands = [],
}: ShortcutsContextProviderProps) {
  // State
  const [isCommandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [isHelpOpen, setHelpOpen] = useState(false);
  const [activeScope, setActiveScope] = useState<ShortcutScope>('global');
  const [shortcuts, setShortcuts] = useState<KeyboardShortcut[]>(initialShortcuts);
  const [sequences, setSequences] = useState<KeySequence[]>(initialSequences);
  const [commands, setCommands] = useState<CommandItem[]>(initialCommands);
  const [pendingSequence, setPendingSequence] = useState<string[]>([]);
  const [preferences, setPreferences] = useState<ShortcutsUserPreferences>(loadPreferences);

  const sequenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ==================== Sequence Management ====================

  const clearSequence = useCallback(() => {
    setPendingSequence([]);
    if (sequenceTimeoutRef.current) {
      clearTimeout(sequenceTimeoutRef.current);
      sequenceTimeoutRef.current = null;
    }
  }, []);

  // ==================== Shortcut Registration ====================

  const registerShortcut = useCallback((shortcut: KeyboardShortcut) => {
    setShortcuts(prev => {
      const normalizedKeys = normalizeKeys(shortcut.keys);
      const conflict = prev.find(s =>
        normalizeKeys(s.keys) === normalizedKeys &&
        s.id !== shortcut.id &&
        (s.scope === shortcut.scope || s.scope === 'global' || shortcut.scope === 'global')
      );

      if (conflict) {
        const conflictPriority = conflict.priority ?? 0;
        const newPriority = shortcut.priority ?? 0;

        if (newPriority <= conflictPriority) {
          logger.warn(`[Shortcuts] Konflikt: ${shortcut.id} vs ${conflict.id}. Behalte ${conflict.id}`);
          return prev;
        }

        logger.warn(`[Shortcuts] Konflikt: ${shortcut.id} vs ${conflict.id}. Ersetze mit ${shortcut.id}`);
        return [...prev.filter(s => s.id !== conflict.id), shortcut];
      }

      return [...prev.filter(s => s.id !== shortcut.id), shortcut];
    });
  }, []);

  const unregisterShortcut = useCallback((id: string) => {
    setShortcuts(prev => prev.filter(s => s.id !== id));
  }, []);

  // ==================== Sequence Registration ====================

  const registerSequence = useCallback((sequence: KeySequence) => {
    setSequences(prev => [...prev.filter(s => s.id !== sequence.id), sequence]);
  }, []);

  const unregisterSequence = useCallback((id: string) => {
    setSequences(prev => prev.filter(s => s.id !== id));
  }, []);

  // ==================== Command Registration ====================

  const registerCommand = useCallback((command: CommandItem) => {
    setCommands(prev => [...prev.filter(c => c.id !== command.id), command]);
  }, []);

  const unregisterCommand = useCallback((id: string) => {
    setCommands(prev => prev.filter(c => c.id !== id));
  }, []);

  // ==================== Command Execution ====================

  const executeCommand = useCallback((commandId: string) => {
    const command = commands.find(c => c.id === commandId);
    if (command && command.enabled !== false) {
      command.onSelect();
    }
  }, [commands]);

  const trackCommandUsage = useCallback((commandId: string) => {
    setPreferences(prev => {
      const now = Date.now();
      const existingIndex = prev.recentCommands.findIndex(r => r.commandId === commandId);

      let newRecent: RecentCommand[];

      if (existingIndex >= 0) {
        // Update existing
        newRecent = prev.recentCommands.map((r, i) =>
          i === existingIndex
            ? { ...r, lastUsed: now, useCount: r.useCount + 1 }
            : r
        );
      } else {
        // Add new
        newRecent = [
          { commandId, lastUsed: now, useCount: 1 },
          ...prev.recentCommands,
        ];
      }

      // Sort by last used and limit
      newRecent = newRecent
        .sort((a, b) => b.lastUsed - a.lastUsed)
        .slice(0, MAX_RECENT_COMMANDS);

      const updated = { ...prev, recentCommands: newRecent };
      savePreferences(updated);
      return updated;
    });
  }, []);

  // ==================== Preferences Management ====================

  const updatePreferences = useCallback((updates: Partial<ShortcutsUserPreferences>) => {
    setPreferences(prev => {
      const updated = { ...prev, ...updates };
      savePreferences(updated);
      return updated;
    });
  }, []);

  const customizeShortcut = useCallback((shortcutId: string, customKeys: string | null) => {
    setPreferences(prev => {
      const customizations = prev.customizations.filter(c => c.shortcutId !== shortcutId);

      if (customKeys !== null) {
        customizations.push({
          shortcutId,
          customKeys,
          enabled: true,
        });
      }

      const updated = { ...prev, customizations };
      savePreferences(updated);
      return updated;
    });
  }, []);

  const resetCustomizations = useCallback(() => {
    setPreferences(prev => {
      const updated = { ...prev, customizations: [] };
      savePreferences(updated);
      return updated;
    });
  }, []);

  // ==================== Check Shortcut Registration ====================

  const isShortcutRegistered = useCallback((keys: string) => {
    const normalizedKeys = normalizeKeys(keys);
    return shortcuts.some(s => normalizeKeys(s.keys) === normalizedKeys);
  }, [shortcuts]);

  // ==================== Keyboard Event Handling ====================

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isTyping = isInputElement(event.target);

      // Process sequences first (only when not typing)
      if (!isTyping && sequences.length > 0) {
        const eventKey = event.key.toLowerCase();

        // Ignore modifier keys
        if (['control', 'alt', 'shift', 'meta'].includes(eventKey)) return;

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

          if (sequenceTimeoutRef.current) {
            clearTimeout(sequenceTimeoutRef.current);
          }
          const timeout = sequences[0]?.timeout ?? DEFAULT_SEQUENCE_TIMEOUT;
          sequenceTimeoutRef.current = setTimeout(clearSequence, timeout);
          return;
        }

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
          if (PROTECTED_SHORTCUTS.has(normalizeKeys(shortcut.keys))) continue;

          const allowInInput = shortcut.keys === '?' || shortcut.keys.toLowerCase() === 'escape';
          if (isTyping && !allowInInput) continue;

          if (shortcut.preventDefault !== false) event.preventDefault();
          if (shortcut.stopPropagation) event.stopPropagation();

          shortcut.handler();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts, sequences, pendingSequence, activeScope, clearSequence]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (sequenceTimeoutRef.current) {
        clearTimeout(sequenceTimeoutRef.current);
      }
    };
  }, []);

  // ==================== Context Value ====================

  const value: ShortcutsContextValue = {
    // State
    isCommandPaletteOpen,
    isHelpOpen,
    activeScope,
    pendingSequence,
    shortcuts,
    sequences,
    commands,
    preferences,
    // Actions
    setCommandPaletteOpen,
    setHelpOpen,
    setActiveScope,
    registerShortcut,
    unregisterShortcut,
    registerSequence,
    unregisterSequence,
    registerCommand,
    unregisterCommand,
    clearSequence,
    isShortcutRegistered,
    executeCommand,
    trackCommandUsage,
    updatePreferences,
    customizeShortcut,
    resetCustomizations,
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
    throw new Error('useShortcutsContext muss innerhalb von ShortcutsContextProvider verwendet werden');
  }
  return context;
}

/**
 * Hook to register a shortcut dynamically
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
 * Hook to register a sequence dynamically
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
 * Hook to register multiple sequences dynamically
 */
export function useRegisterSequences(sequencesToRegister: KeySequence[]) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!context || sequencesToRegister.length === 0) return;

    sequencesToRegister.forEach(s => context.registerSequence(s));
    return () => sequencesToRegister.forEach(s => context.unregisterSequence(s.id));
  }, [sequencesToRegister, context]);
}

/**
 * Hook to register a command dynamically
 */
export function useRegisterCommand(command: CommandItem | null) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!command || !context) return;

    context.registerCommand(command);
    return () => context.unregisterCommand(command.id);
  }, [command, context]);
}

/**
 * Hook to register multiple commands dynamically
 */
export function useRegisterCommands(commandsToRegister: CommandItem[]) {
  const context = useContext(ShortcutsContext);

  useEffect(() => {
    if (!context || commandsToRegister.length === 0) return;

    commandsToRegister.forEach(c => context.registerCommand(c));
    return () => commandsToRegister.forEach(c => context.unregisterCommand(c.id));
  }, [commandsToRegister, context]);
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
      if (context.activeScope === scope) {
        context.setActiveScope(previousScope);
      }
    };
  }, [scope, context]);
}

// ==================== Exports ====================

export { ShortcutsContext };
