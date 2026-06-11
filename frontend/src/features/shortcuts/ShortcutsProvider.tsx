/**
 * ShortcutsProvider - Main Provider for Keyboard Shortcuts System
 *
 * This component provides:
 * - Global shortcuts context for the entire application
 * - Default navigation and action shortcuts
 * - Command palette integration
 * - Help modal integration
 * - Undo/redo integration
 * - Key sequence indicator
 *
 * Usage:
 * ```tsx
 * // In main.tsx or App.tsx
 * <ShortcutsProvider>
 *   <App />
 * </ShortcutsProvider>
 * ```
 *
 * WCAG 2.1 AA konform - Alle Labels auf Deutsch
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import { Users, Truck, Home, Settings, Upload, Search, HelpCircle, Keyboard, Wallet, Building2, RefreshCw, FolderOpen } from 'lucide-react';

import { ShortcutsContextProvider, useShortcutsContext } from './context/ShortcutsContext';
import { CommandPalette } from './components/CommandPalette';
import { ShortcutsHelpModal, PendingSequenceIndicator } from './components/ShortcutsHelpModal';
import type {
  KeyboardShortcut,
  KeySequence,
  CommandItem,
} from './types/shortcut-types';

// ==================== Types ====================

interface ShortcutsProviderProps {
  children: ReactNode;
  /** Disable default shortcuts (for custom implementations) */
  disableDefaults?: boolean;
  /** Additional initial shortcuts */
  additionalShortcuts?: KeyboardShortcut[];
  /** Additional initial sequences */
  additionalSequences?: KeySequence[];
  /** Additional initial commands */
  additionalCommands?: CommandItem[];
}

// ==================== Default Shortcuts ====================

function useDefaultShortcuts(): {
  shortcuts: KeyboardShortcut[];
  sequences: KeySequence[];
  commands: CommandItem[];
} {
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
      description: 'Befehlspalette öffnen',
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
    {
      id: 'nav-new',
      description: 'Neu erstellen',
      keys: 'n',
      category: 'actions',
      scope: 'global',
      handler: () => {
        // Dispatch event for context-aware new action
        window.dispatchEvent(new CustomEvent('shortcut-new'));
      },
    },
    {
      id: 'nav-edit',
      description: 'Bearbeiten',
      keys: 'e',
      category: 'actions',
      scope: 'global',
      handler: () => {
        // Dispatch event for context-aware edit action
        window.dispatchEvent(new CustomEvent('shortcut-edit'));
      },
    },

    // Document Action Shortcuts (list-view scope)
    {
      id: 'action-delete',
      description: 'Ausgewaehlte Dokumente löschen',
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
      handler: () => navigate({ to: '/admin/settings' }),
    },
    {
      id: 'seq-go-privat',
      description: 'Zu Privat',
      sequence: ['g', 'p'],
      category: 'navigation',
      handler: () => navigate({ to: '/privat' }),
    },
    {
      id: 'seq-go-banking',
      description: 'Zum Banking',
      sequence: ['g', 'b'],
      category: 'navigation',
      handler: () => navigate({ to: '/admin/banking' }),
    },
  ], [navigate]);

  const commands = useMemo<CommandItem[]>(() => [
    // Navigation Commands
    {
      id: 'cmd-go-home',
      label: 'Zur Startseite',
      description: 'Dashboard öffnen',
      category: 'navigation',
      icon: Home,
      keys: 'alt+h',
      keywords: ['home', 'dashboard', 'start', 'startseite'],
      priority: 100,
      onSelect: () => navigate({ to: '/' }),
    },
    {
      id: 'cmd-go-kunden',
      label: 'Zu Kunden',
      description: 'Kundenübersicht öffnen',
      category: 'navigation',
      icon: Users,
      sequence: ['g', 'k'],
      keywords: ['kunden', 'customers', 'partner'],
      priority: 90,
      onSelect: () => navigate({ to: '/kunden' }),
    },
    {
      id: 'cmd-go-lieferanten',
      label: 'Zu Lieferanten',
      description: 'Lieferantenübersicht öffnen',
      category: 'navigation',
      icon: Truck,
      sequence: ['g', 'l'],
      keywords: ['lieferanten', 'suppliers', 'vendor'],
      priority: 90,
      onSelect: () => navigate({ to: '/lieferanten' }),
    },
    {
      id: 'cmd-go-finanzen',
      label: 'Zu Finanzen',
      description: 'Finanzen öffnen',
      category: 'navigation',
      icon: Wallet,
      sequence: ['g', 'f'],
      keywords: ['finanzen', 'finance', 'geld', 'buchhaltung'],
      priority: 85,
      onSelect: () => navigate({ to: '/finanzen' }),
    },
    {
      id: 'cmd-go-upload',
      label: 'Neuer Upload',
      description: 'Dokumente hochladen',
      category: 'navigation',
      icon: Upload,
      keys: 'ctrl+u',
      sequence: ['g', 'u'],
      keywords: ['upload', 'hochladen', 'dokument', 'neu'],
      priority: 95,
      onSelect: () => navigate({ to: '/upload' }),
    },
    {
      id: 'cmd-go-banking',
      label: 'Zum Banking',
      description: 'Banking-Übersicht öffnen',
      category: 'navigation',
      icon: Building2,
      sequence: ['g', 'b'],
      keywords: ['banking', 'bank', 'konto', 'transaktionen'],
      priority: 80,
      onSelect: () => navigate({ to: '/admin/banking' }),
    },
    {
      id: 'cmd-go-privat',
      label: 'Zu Privat',
      description: 'Privatbereich öffnen',
      category: 'navigation',
      icon: FolderOpen,
      sequence: ['g', 'p'],
      keywords: ['privat', 'private', 'persönlich'],
      priority: 75,
      onSelect: () => navigate({ to: '/privat' }),
    },
    {
      id: 'cmd-go-admin',
      label: 'Einstellungen',
      description: 'Einstellungen öffnen',
      category: 'navigation',
      icon: Settings,
      sequence: ['g', 'a'],
      keywords: ['admin', 'settings', 'einstellungen', 'konfiguration'],
      priority: 70,
      onSelect: () => navigate({ to: '/admin/settings' }),
    },

    // Action Commands
    {
      id: 'cmd-search-focus',
      label: 'Suche fokussieren',
      description: 'Suchfeld aktivieren',
      category: 'actions',
      icon: Search,
      keys: '/',
      keywords: ['suche', 'search', 'finden', 'filter'],
      priority: 100,
      onSelect: () => {
        const searchInput = document.querySelector<HTMLInputElement>('[data-search-input]');
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      },
    },
    {
      id: 'cmd-refresh',
      label: 'Seite aktualisieren',
      description: 'Aktuelle Daten neu laden',
      category: 'actions',
      icon: RefreshCw,
      keywords: ['refresh', 'reload', 'aktualisieren', 'neu laden'],
      priority: 50,
      onSelect: () => {
        window.dispatchEvent(new CustomEvent('shortcut-refresh'));
        toast.success('Daten werden aktualisiert...');
      },
    },

    // Help Commands
    {
      id: 'cmd-show-shortcuts',
      label: 'Tastenkürzel anzeigen',
      description: 'Alle Tastenkürzel anzeigen',
      category: 'help',
      icon: Keyboard,
      keys: '?',
      keywords: ['shortcuts', 'keyboard', 'tastatur', 'hilfe', 'help'],
      priority: 90,
      onSelect: () => {
        window.dispatchEvent(new CustomEvent('open-shortcuts-help'));
      },
    },
    {
      id: 'cmd-show-help',
      label: 'Hilfe',
      description: 'Hilfezentrum öffnen',
      category: 'help',
      icon: HelpCircle,
      keywords: ['hilfe', 'help', 'support', 'dokumentation'],
      priority: 80,
      onSelect: () => {
        // Open help center or documentation
        window.dispatchEvent(new CustomEvent('open-help-center'));
      },
    },
  ], [navigate]);

  return { shortcuts, sequences, commands };
}

// ==================== Inner Provider ====================

function ShortcutsProviderInner({
  children,
  disableDefaults = false,
  additionalShortcuts = [],
  additionalSequences = [],
  additionalCommands = [],
}: Omit<ShortcutsProviderProps, 'children'> & { children: ReactNode }) {
  const context = useShortcutsContext();
  const { shortcuts: defaultShortcuts, sequences: defaultSequences, commands: defaultCommands } = useDefaultShortcuts();

  const [isHelpOpen, setIsHelpOpen] = useState(false);

  // Register default shortcuts and sequences
  useEffect(() => {
    if (disableDefaults) return;

    // Help and escape shortcuts
    const helpShortcuts: KeyboardShortcut[] = [
      {
        id: 'help-show',
        description: 'Tastenkürzel anzeigen',
        keys: '?',
        category: 'help',
        scope: 'global',
        handler: () => setIsHelpOpen(true),
      },
      {
        id: 'modal-close',
        description: 'Dialog schließen',
        keys: 'escape',
        category: 'help',
        scope: 'global',
        handler: () => {
          if (context.isCommandPaletteOpen) {
            context.setCommandPaletteOpen(false);
          } else if (isHelpOpen) {
            setIsHelpOpen(false);
          } else {
            window.dispatchEvent(new CustomEvent('shortcut-escape'));
            window.dispatchEvent(new CustomEvent('close-modal'));
          }
        },
      },
    ];

    const allShortcuts = [...defaultShortcuts, ...helpShortcuts, ...additionalShortcuts];
    const allSequences = [...defaultSequences, ...additionalSequences];
    const allCommands = [...defaultCommands, ...additionalCommands];

    allShortcuts.forEach(shortcut => context.registerShortcut(shortcut));
    allSequences.forEach(seq => context.registerSequence(seq));
    allCommands.forEach(cmd => context.registerCommand(cmd));

    return () => {
      allShortcuts.forEach(s => context.unregisterShortcut(s.id));
      allSequences.forEach(s => context.unregisterSequence(s.id));
      allCommands.forEach(c => context.unregisterCommand(c.id));
    };
  }, [
    disableDefaults,
    defaultShortcuts,
    defaultSequences,
    defaultCommands,
    additionalShortcuts,
    additionalSequences,
    additionalCommands,
    context,
    isHelpOpen,
  ]);

  // Listen for help open event
  useEffect(() => {
    const handleOpenHelp = () => setIsHelpOpen(true);
    window.addEventListener('open-shortcuts-help', handleOpenHelp);
    return () => window.removeEventListener('open-shortcuts-help', handleOpenHelp);
  }, []);

  // Combine all shortcuts and sequences for help modal
  const allShortcutsForHelp = useMemo(() => {
    return context.shortcuts;
  }, [context.shortcuts]);

  const allSequencesForHelp = useMemo(() => {
    return context.sequences;
  }, [context.sequences]);

  return (
    <>
      {children}

      {/* Command Palette */}
      <CommandPalette />

      {/* Keyboard Shortcuts Help Modal */}
      <ShortcutsHelpModal
        open={isHelpOpen}
        onOpenChange={setIsHelpOpen}
        shortcuts={allShortcutsForHelp}
        sequences={allSequencesForHelp}
      />

      {/* Pending Sequence Indicator */}
      <PendingSequenceIndicator sequence={context.pendingSequence} />
    </>
  );
}

// ==================== Main Provider ====================

/**
 * ShortcutsProvider - Wraps the application with keyboard shortcuts functionality
 *
 * Features:
 * - Keyboard shortcuts context
 * - Command palette (Cmd+K / Ctrl+K)
 * - Help modal (?)
 * - Key sequence indicator
 * - Default navigation shortcuts
 *
 * Must be used within a Router context.
 */
export function ShortcutsProvider({
  children,
  disableDefaults = false,
  additionalShortcuts = [],
  additionalSequences = [],
  additionalCommands = [],
}: ShortcutsProviderProps) {
  return (
    <ShortcutsContextProvider>
      <ShortcutsProviderInner
        disableDefaults={disableDefaults}
        additionalShortcuts={additionalShortcuts}
        additionalSequences={additionalSequences}
        additionalCommands={additionalCommands}
      >
        {children}
      </ShortcutsProviderInner>
    </ShortcutsContextProvider>
  );
}

// ==================== Exports ====================

export default ShortcutsProvider;

// Re-export useful components and hooks
export { useShortcutsContext } from './context/ShortcutsContext';
export { CommandPalette } from './components/CommandPalette';
export { ShortcutsHelpModal, PendingSequenceIndicator } from './components/ShortcutsHelpModal';
export {
  useHotkey,
  useHotkeys,
  useKeySequence,
  useCombinedHotkeys,
  formatShortcutKeys,
  formatKeySequence,
} from './hooks/useHotkeys';
export type {
  KeyboardShortcut,
  KeySequence,
  CommandItem,
  ShortcutScope,
  ShortcutCategory,
} from './types/shortcut-types';
