/**
 * GlobalShortcutsProvider - Application-wide Keyboard Shortcuts Integration
 *
 * This component provides:
 * - Global shortcuts context for the entire application
 * - Default navigation and action shortcuts
 * - Help modal integration
 * - Undo/redo integration
 * - Key sequence indicator
 * - Integration with existing components
 *
 * Usage:
 * ```tsx
 * // In main.tsx or App.tsx
 * <GlobalShortcutsProvider>
 *   <App />
 * </GlobalShortcutsProvider>
 * ```
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  GlobalShortcutsProvider as ShortcutsContextProvider,
  useShortcutsContext,
  type KeyboardShortcut,
  type KeySequence,
} from '@/hooks/useKeyboardShortcuts';
import { useGlobalUndo } from '@/hooks/useUndoableAction';
import { KeyboardShortcutsHelp, PendingSequenceIndicator } from './KeyboardShortcutsHelp';

// ==================== Types ====================

interface GlobalShortcutsProviderProps {
  children: ReactNode;
}

// ==================== Default Shortcuts Hook ====================

/**
 * Create default application shortcuts with navigation and actions
 */
function useDefaultShortcuts(): { shortcuts: KeyboardShortcut[]; sequences: KeySequence[] } {
  const navigate = useNavigate();

  const shortcuts = useMemo<KeyboardShortcut[]>(() => [
    // Navigation Shortcuts
    {
      id: 'nav-home',
      description: 'Zur Startseite',
      keys: 'alt+h',
      category: 'navigation',
      scope: 'global',
      handler: () => navigate({ to: '/' }),
    },
    {
      id: 'nav-search',
      description: 'Suche fokussieren',
      keys: '/',
      category: 'navigation',
      scope: 'global',
      handler: () => {
        const searchInput = document.querySelector<HTMLInputElement>('[data-search-input]');
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        } else {
          // Fallback: look for any search input
          const fallbackInput = document.querySelector<HTMLInputElement>(
            'input[type="search"], input[placeholder*="Such"], input[placeholder*="such"]'
          );
          if (fallbackInput) {
            fallbackInput.focus();
            fallbackInput.select();
          }
        }
      },
    },
    {
      id: 'nav-command',
      description: 'Befehlspalette oeffnen',
      keys: 'ctrl+k',
      category: 'navigation',
      scope: 'global',
      handler: () => {
        window.dispatchEvent(new CustomEvent('open-command-dialog'));
      },
    },
    {
      id: 'nav-upload',
      description: 'Neuer Upload',
      keys: 'ctrl+u',
      category: 'navigation',
      scope: 'global',
      handler: () => navigate({ to: '/upload' }),
    },

    // Document Action Shortcuts (list-view scope)
    {
      id: 'action-delete',
      description: 'Ausgewaehlte Dokumente loeschen',
      keys: 'ctrl+d',
      category: 'actions',
      scope: 'list-view',
      handler: () => {
        window.dispatchEvent(new CustomEvent('shortcut-delete'));
      },
    },
    {
      id: 'action-move',
      description: 'Ausgewaehlte Dokumente verschieben',
      keys: 'ctrl+m',
      category: 'actions',
      scope: 'list-view',
      handler: () => {
        window.dispatchEvent(new CustomEvent('shortcut-move'));
      },
    },

    // Form Shortcuts
    {
      id: 'form-save',
      description: 'Formular speichern',
      keys: 'ctrl+s',
      category: 'forms',
      scope: 'form',
      handler: () => {
        window.dispatchEvent(new CustomEvent('shortcut-save'));
      },
    },
    {
      id: 'form-submit',
      description: 'Formular absenden',
      keys: 'ctrl+enter',
      category: 'forms',
      scope: 'form',
      handler: () => {
        window.dispatchEvent(new CustomEvent('shortcut-submit'));
      },
    },
  ], [navigate]);

  const sequences = useMemo<KeySequence[]>(() => [
    // g-* Navigation sequences (Gmail-style)
    {
      id: 'seq-go-dashboard',
      description: 'Zum Dashboard',
      sequence: ['g', 'd'],
      category: 'navigation',
      handler: () => navigate({ to: '/' }),
    },
    {
      id: 'seq-go-kunden',
      description: 'Zu Kunden',
      sequence: ['g', 'k'],
      category: 'navigation',
      handler: () => navigate({ to: '/kunden' }),
    },
    {
      id: 'seq-go-lieferanten',
      description: 'Zu Lieferanten',
      sequence: ['g', 'l'],
      category: 'navigation',
      handler: () => navigate({ to: '/lieferanten' }),
    },
    {
      id: 'seq-go-finanzen',
      description: 'Zu Finanzen',
      sequence: ['g', 'f'],
      category: 'navigation',
      handler: () => navigate({ to: '/finanzen' }),
    },
    {
      id: 'seq-go-upload',
      description: 'Zum Upload',
      sequence: ['g', 'u'],
      category: 'navigation',
      handler: () => navigate({ to: '/upload' }),
    },
    {
      id: 'seq-go-admin',
      description: 'Zur Administration',
      sequence: ['g', 'a'],
      category: 'navigation',
      handler: () => navigate({ to: '/admin' }),
    },
    {
      id: 'seq-go-privat',
      description: 'Zu Privat',
      sequence: ['g', 'p'],
      category: 'navigation',
      handler: () => navigate({ to: '/privat' }),
    },
  ], [navigate]);

  return { shortcuts, sequences };
}

// ==================== Inner Provider with Context Access ====================

function GlobalShortcutsInner({ children }: { children: ReactNode }) {
  const { shortcuts: defaultShortcuts, sequences } = useDefaultShortcuts();
  const context = useShortcutsContext();
  const { undo, redo, canUndo, canRedo } = useGlobalUndo();
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  // Register default shortcuts and sequences
  useEffect(() => {
    // Register shortcuts with proper handlers
    const shortcutsWithHandlers: KeyboardShortcut[] = [
      ...defaultShortcuts,
      // Help shortcut
      {
        id: 'help-show',
        description: 'Tastenkuerzel anzeigen',
        keys: '?',
        category: 'help',
        scope: 'global',
        handler: () => setIsHelpOpen(true),
      },
      // Modal close shortcut
      {
        id: 'modal-close',
        description: 'Dialog schliessen',
        keys: 'escape',
        category: 'help',
        scope: 'global',
        handler: () => {
          if (isHelpOpen) {
            setIsHelpOpen(false);
          } else {
            window.dispatchEvent(new CustomEvent('shortcut-escape'));
            window.dispatchEvent(new CustomEvent('close-modal'));
          }
        },
      },
    ];

    shortcutsWithHandlers.forEach(shortcut => {
      context.registerShortcut(shortcut);
    });

    sequences.forEach(seq => {
      context.registerSequence(seq);
    });

    return () => {
      shortcutsWithHandlers.forEach(s => context.unregisterShortcut(s.id));
      sequences.forEach(s => context.unregisterSequence(s.id));
    };
  }, [defaultShortcuts, sequences, context, isHelpOpen]);

  // Global Ctrl+Z for undo and Ctrl+Shift+Z/Ctrl+Y for redo
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const target = event.target as HTMLElement;
      const isTyping =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable;

      if (isTyping) return;

      // Ctrl+Shift+Z or Cmd+Shift+Z for redo
      if ((event.ctrlKey || event.metaKey) && event.key === 'z' && event.shiftKey) {
        if (canRedo) {
          event.preventDefault();
          redo();
        }
        return;
      }

      // Ctrl+Y for redo (Windows style)
      if ((event.ctrlKey || event.metaKey) && event.key === 'y') {
        if (canRedo) {
          event.preventDefault();
          redo();
        }
        return;
      }

      // Ctrl+Z or Cmd+Z for undo
      if ((event.ctrlKey || event.metaKey) && event.key === 'z' && !event.shiftKey) {
        if (canUndo) {
          event.preventDefault();
          undo();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undo, redo, canUndo, canRedo]);

  // Get all shortcuts for the help modal (including undo/redo)
  const allShortcuts = useMemo<KeyboardShortcut[]>(() => {
    const baseShortcuts = context.shortcuts;

    // Add undo/redo shortcuts for display
    const undoRedoShortcuts: KeyboardShortcut[] = [
      {
        id: 'undo-action',
        description: 'Letzte Aktion rueckgaengig',
        keys: 'ctrl+z',
        category: 'actions',
        handler: () => canUndo && undo(),
        enabled: canUndo,
      },
      {
        id: 'redo-action',
        description: 'Aktion wiederholen',
        keys: 'ctrl+shift+z',
        category: 'actions',
        handler: () => canRedo && redo(),
        enabled: canRedo,
      },
      {
        id: 'redo-action-alt',
        description: 'Aktion wiederholen (alternativ)',
        keys: 'ctrl+y',
        category: 'actions',
        handler: () => canRedo && redo(),
        enabled: canRedo,
      },
    ];

    // Filter out duplicates
    const existingIds = new Set(baseShortcuts.map(s => s.id));
    const uniqueUndoRedo = undoRedoShortcuts.filter(s => !existingIds.has(s.id));

    return [...baseShortcuts, ...uniqueUndoRedo];
  }, [context.shortcuts, undo, redo, canUndo, canRedo]);

  return (
    <>
      {children}

      {/* Keyboard Shortcuts Help Modal */}
      <KeyboardShortcutsHelp
        open={isHelpOpen}
        onOpenChange={setIsHelpOpen}
        shortcuts={allShortcuts}
        sequences={context.sequences}
      />

      {/* Pending Sequence Indicator */}
      <PendingSequenceIndicator sequence={context.pendingSequence} />
    </>
  );
}

// ==================== Main Provider ====================

/**
 * Global shortcuts provider that wraps the entire application.
 *
 * Provides:
 * - Keyboard shortcuts context
 * - Undo/redo integration (requires UndoProvider to be parent)
 * - Help modal
 * - Key sequence indicator
 *
 * Must be used within a Router context and UndoProvider.
 */
export function GlobalShortcutsProvider({ children }: GlobalShortcutsProviderProps) {
  return (
    <ShortcutsContextProvider>
      <GlobalShortcutsInner>{children}</GlobalShortcutsInner>
    </ShortcutsContextProvider>
  );
}

// ==================== Exports ====================

export default GlobalShortcutsProvider;
