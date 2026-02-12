/**
 * CommandPalette - VS Code-style Command Palette
 *
 * Features:
 * - Cmd+K / Ctrl+K to open
 * - Fuzzy search for commands
 * - Recent commands shown first
 * - Keyboard navigation (arrow keys, enter)
 * - German labels for all commands
 * - Grouped by category
 *
 * WCAG 2.1 AA konform
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  FileText,
  Users,
  Truck,
  Home,
  Settings,
  Upload,
  Search,
  HelpCircle,
  Plus,
  Edit,
  Clock,
  Star,
  Navigation,
  Zap,
  FormInput,
  Keyboard,
  Wallet,
  Building2,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useShortcutsContext } from '../context/ShortcutsContext';
import { formatShortcutKeys, formatKeySequence } from '../hooks/useHotkeys';
import type {
  CommandItem as CommandItemType,
  ShortcutCategory,
  RecentCommand,
} from '../types/shortcut-types';
import { SHORTCUT_CATEGORY_LABELS } from '../types/shortcut-types';

// ==================== Types ====================

interface CommandPaletteProps {
  /** Override open state (optional, uses context by default) */
  open?: boolean;
  /** Override onOpenChange (optional, uses context by default) */
  onOpenChange?: (open: boolean) => void;
  /** Additional commands (merged with context commands) */
  additionalCommands?: CommandItemType[];
  /** Placeholder text */
  placeholder?: string;
  /** Empty state text */
  emptyText?: string;
}

// ==================== Category Icons ====================

const categoryIcons: Record<ShortcutCategory, LucideIcon> = {
  navigation: Navigation,
  actions: Zap,
  documents: FileText,
  forms: FormInput,
  help: HelpCircle,
};

const categoryColors: Record<ShortcutCategory, string> = {
  navigation: 'text-blue-500',
  actions: 'text-green-500',
  documents: 'text-orange-500',
  forms: 'text-purple-500',
  help: 'text-gray-500',
};

// ==================== Fuzzy Search ====================

function fuzzyMatch(query: string, text: string): boolean {
  if (!query) return true;

  const queryLower = query.toLowerCase();
  const textLower = text.toLowerCase();

  // Direct substring match
  if (textLower.includes(queryLower)) return true;

  // Fuzzy match (all characters in order)
  let queryIndex = 0;
  for (let i = 0; i < textLower.length && queryIndex < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIndex]) {
      queryIndex++;
    }
  }
  return queryIndex === queryLower.length;
}

function matchScore(query: string, text: string): number {
  if (!query) return 0;

  const queryLower = query.toLowerCase();
  const textLower = text.toLowerCase();

  // Exact match
  if (textLower === queryLower) return 100;

  // Starts with query
  if (textLower.startsWith(queryLower)) return 80;

  // Contains query
  if (textLower.includes(queryLower)) return 60;

  // Fuzzy match score based on proximity
  let score = 0;
  let queryIndex = 0;
  let lastMatchIndex = -1;

  for (let i = 0; i < textLower.length && queryIndex < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIndex]) {
      // Bonus for consecutive matches
      if (lastMatchIndex === i - 1) {
        score += 10;
      }
      score += 5;
      lastMatchIndex = i;
      queryIndex++;
    }
  }

  return queryIndex === queryLower.length ? score : 0;
}

// ==================== Shortcut Display ====================

function ShortcutDisplay({ keys, sequence }: { keys?: string; sequence?: string[] }) {
  if (sequence && sequence.length > 0) {
    return (
      <span className="text-xs text-muted-foreground font-mono">
        {sequence.map((key, i) => (
          <span key={i}>
            {i > 0 && <span className="mx-1">\u2192</span>}
            <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">
              {formatShortcutKeys(key)}
            </Badge>
          </span>
        ))}
      </span>
    );
  }

  if (keys) {
    return (
      <CommandShortcut className="font-mono text-xs">
        {formatShortcutKeys(keys)}
      </CommandShortcut>
    );
  }

  return null;
}

// ==================== Main Component ====================

export function CommandPalette({
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  additionalCommands = [],
  placeholder = 'Befehl suchen...',
  emptyText = 'Keine Befehle gefunden.',
}: CommandPaletteProps) {
  const context = useShortcutsContext();
  const inputRef = useRef<HTMLInputElement>(null);

  // Use controlled or context state
  const isOpen = controlledOpen ?? context.isCommandPaletteOpen;
  const setOpen = controlledOnOpenChange ?? context.setCommandPaletteOpen;

  const [searchQuery, setSearchQuery] = useState('');

  // Merge commands from context and additional
  const allCommands = useMemo(() => {
    return [...context.commands, ...additionalCommands];
  }, [context.commands, additionalCommands]);

  // Get recent commands
  const recentCommands = useMemo(() => {
    return context.preferences.recentCommands
      .map(recent => allCommands.find(c => c.id === recent.commandId))
      .filter((c): c is CommandItemType => c !== undefined)
      .slice(0, 5);
  }, [context.preferences.recentCommands, allCommands]);

  // Filter and sort commands based on search
  const filteredCommands = useMemo(() => {
    if (!searchQuery.trim()) {
      return allCommands.filter(c => c.enabled !== false);
    }

    return allCommands
      .filter(c => c.enabled !== false)
      .map(command => {
        // Calculate match score
        const labelScore = matchScore(searchQuery, command.label);
        const descScore = command.description
          ? matchScore(searchQuery, command.description) * 0.5
          : 0;
        const keywordScore = command.keywords
          ? Math.max(...command.keywords.map(k => matchScore(searchQuery, k))) * 0.3
          : 0;

        const totalScore = Math.max(labelScore, descScore, keywordScore);

        return { command, score: totalScore };
      })
      .filter(({ score }) => score > 0)
      .sort((a, b) => {
        // Sort by score, then by priority, then by label
        if (b.score !== a.score) return b.score - a.score;
        const priorityDiff = (b.command.priority ?? 0) - (a.command.priority ?? 0);
        if (priorityDiff !== 0) return priorityDiff;
        return a.command.label.localeCompare(b.command.label);
      })
      .map(({ command }) => command);
  }, [allCommands, searchQuery]);

  // Group commands by category
  const groupedCommands = useMemo(() => {
    const groups: Record<ShortcutCategory, CommandItemType[]> = {
      navigation: [],
      actions: [],
      documents: [],
      forms: [],
      help: [],
    };

    filteredCommands.forEach(command => {
      const category = command.category || 'actions';
      if (groups[category]) {
        groups[category].push(command);
      }
    });

    return groups;
  }, [filteredCommands]);

  // Handle command selection
  const handleSelect = useCallback((command: CommandItemType) => {
    // Track usage
    context.trackCommandUsage(command.id);

    // Close palette
    setOpen(false);
    setSearchQuery('');

    // Execute command (with small delay for closing animation)
    requestAnimationFrame(() => {
      command.onSelect();
    });
  }, [context, setOpen]);

  // Clear search when closing
  useEffect(() => {
    if (!isOpen) {
      setSearchQuery('');
    }
  }, [isOpen]);

  // Focus input when opening
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Listen for custom event to open palette
  useEffect(() => {
    const handleOpenCommand = () => setOpen(true);
    window.addEventListener('open-command-dialog', handleOpenCommand);
    return () => window.removeEventListener('open-command-dialog', handleOpenCommand);
  }, [setOpen]);

  const hasResults = filteredCommands.length > 0;
  const showRecent = !searchQuery.trim() && recentCommands.length > 0;

  // Category order for display
  const categoryOrder: ShortcutCategory[] = ['navigation', 'actions', 'documents', 'forms', 'help'];

  return (
    <CommandDialog open={isOpen} onOpenChange={setOpen}>
      <Command
        className="rounded-lg border shadow-md"
        shouldFilter={false} // We handle filtering ourselves
      >
        <CommandInput
          ref={inputRef}
          placeholder={placeholder}
          value={searchQuery}
          onValueChange={setSearchQuery}
        />
        <CommandList className="max-h-[400px]">
          <CommandEmpty>{emptyText}</CommandEmpty>

          {/* Recent Commands */}
          {showRecent && (
            <>
              <CommandGroup heading="Zuletzt verwendet">
                {recentCommands.map(command => {
                  const Icon = command.icon || Zap;
                  return (
                    <CommandItem
                      key={`recent-${command.id}`}
                      value={command.id}
                      onSelect={() => handleSelect(command)}
                      className="flex items-center gap-2"
                    >
                      <Clock className="w-4 h-4 text-muted-foreground" />
                      <Icon className="w-4 h-4" />
                      <span className="flex-1">{command.label}</span>
                      <ShortcutDisplay keys={command.keys} sequence={command.sequence} />
                    </CommandItem>
                  );
                })}
              </CommandGroup>
              <CommandSeparator />
            </>
          )}

          {/* Grouped Commands */}
          {hasResults && categoryOrder.map(category => {
            const commands = groupedCommands[category];
            if (commands.length === 0) return null;

            const CategoryIcon = categoryIcons[category];

            return (
              <CommandGroup
                key={category}
                heading={
                  <span className="flex items-center gap-2">
                    <CategoryIcon className={cn('w-3 h-3', categoryColors[category])} />
                    {SHORTCUT_CATEGORY_LABELS[category]}
                  </span>
                }
              >
                {commands.map(command => {
                  const Icon = command.icon || Zap;
                  return (
                    <CommandItem
                      key={command.id}
                      value={command.id}
                      onSelect={() => handleSelect(command)}
                      className="flex items-center gap-2"
                    >
                      <Icon className="w-4 h-4" />
                      <div className="flex flex-col flex-1 gap-0.5">
                        <span>{command.label}</span>
                        {command.description && (
                          <span className="text-xs text-muted-foreground">
                            {command.description}
                          </span>
                        )}
                      </div>
                      <ShortcutDisplay keys={command.keys} sequence={command.sequence} />
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            );
          })}
        </CommandList>

        {/* Footer */}
        <div className="border-t p-2 text-xs text-muted-foreground flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">\u2191</Badge>
              <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">\u2193</Badge>
              Navigieren
            </span>
            <span className="flex items-center gap-1">
              <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">\u21B5</Badge>
              Ausführen
            </span>
            <span className="flex items-center gap-1">
              <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">Esc</Badge>
              Schließen
            </span>
          </div>
          <span className="flex items-center gap-1">
            <Badge variant="outline" className="px-1 py-0 text-[10px] font-mono">?</Badge>
            für Tastenkürzel
          </span>
        </div>
      </Command>
    </CommandDialog>
  );
}

// ==================== Exports ====================

export default CommandPalette;
