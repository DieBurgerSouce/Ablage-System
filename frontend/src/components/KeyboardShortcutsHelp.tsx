/**
 * KeyboardShortcutsHelp - Modal showing all available keyboard shortcuts
 *
 * Features:
 * - Grouped shortcuts by category
 * - German labels for all shortcuts
 * - Platform-aware key display (Mac vs Windows)
 * - Search/filter functionality
 * - Accessible (ARIA, keyboard navigation)
 * - Triggered by '?' key
 *
 * WCAG 2.1 AA konform
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Keyboard,
  Navigation,
  FileText,
  HelpCircle,
  Zap,
  FormInput,
  Search,
} from 'lucide-react';
import {
  type KeyboardShortcut,
  type KeySequence,
  type ShortcutCategory,
  formatShortcutKeys,
  formatKeySequence,
  SHORTCUT_CATEGORY_LABELS,
} from '@/hooks/useKeyboardShortcuts';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface KeyboardShortcutsHelpProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts: KeyboardShortcut[];
  sequences?: KeySequence[];
  /** Additional content to display in the modal */
  additionalContent?: React.ReactNode;
}

// ==================== Category Configuration ====================

const categoryConfig: Record<ShortcutCategory, {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  description: string;
}> = {
  navigation: {
    label: SHORTCUT_CATEGORY_LABELS.navigation,
    icon: Navigation,
    color: 'text-blue-500',
    description: 'Schnelle Navigation zwischen Seiten',
  },
  actions: {
    label: SHORTCUT_CATEGORY_LABELS.actions,
    icon: Zap,
    color: 'text-green-500',
    description: 'Aktionen für ausgewählte Dokumente',
  },
  documents: {
    label: SHORTCUT_CATEGORY_LABELS.documents,
    icon: FileText,
    color: 'text-orange-500',
    description: 'Dokumentenspezifische Aktionen',
  },
  forms: {
    label: SHORTCUT_CATEGORY_LABELS.forms,
    icon: FormInput,
    color: 'text-purple-500',
    description: 'Formulareingabe und -absendung',
  },
  help: {
    label: SHORTCUT_CATEGORY_LABELS.help,
    icon: HelpCircle,
    color: 'text-gray-500',
    description: 'Hilfe und Dialoge',
  },
};

// Category display order
const categoryOrder: ShortcutCategory[] = ['navigation', 'actions', 'documents', 'forms', 'help'];

// ==================== Components ====================

/**
 * Badge component for displaying keyboard shortcut keys
 */
export function ShortcutBadge({
  keys,
  className,
  variant = 'default',
}: {
  keys: string;
  className?: string;
  variant?: 'default' | 'compact';
}) {
  const formattedKeys = formatShortcutKeys(keys);
  const parts = formattedKeys.split(' + ');

  if (variant === 'compact') {
    return (
      <span className={cn('font-mono text-xs', className)}>
        {parts.join('+')}
      </span>
    );
  }

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 && <span className="text-muted-foreground mx-0.5">+</span>}
          <Badge
            variant="outline"
            className="px-1.5 py-0.5 text-xs font-mono bg-muted/50 whitespace-nowrap"
          >
            {part}
          </Badge>
        </span>
      ))}
    </div>
  );
}

/**
 * Badge component for displaying key sequences
 */
export function SequenceBadge({
  sequence,
  className,
}: {
  sequence: string[];
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      {sequence.map((key, index) => (
        <span key={index}>
          {index > 0 && <span className="text-muted-foreground mx-1">dann</span>}
          <Badge
            variant="outline"
            className="px-1.5 py-0.5 text-xs font-mono bg-muted/50"
          >
            {formatShortcutKeys(key)}
          </Badge>
        </span>
      ))}
    </div>
  );
}

/**
 * Shortcut row component
 */
function ShortcutRow({
  shortcut,
  highlighted = false,
}: {
  shortcut: KeyboardShortcut;
  highlighted?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between py-2 px-2 rounded-md transition-colors',
        highlighted && 'bg-accent/50',
        shortcut.enabled === false && 'opacity-50'
      )}
    >
      <span className="text-sm text-muted-foreground">
        {shortcut.description}
      </span>
      <ShortcutBadge keys={shortcut.keys} />
    </div>
  );
}

/**
 * Sequence row component
 */
function SequenceRow({
  sequence,
  highlighted = false,
}: {
  sequence: KeySequence;
  highlighted?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between py-2 px-2 rounded-md transition-colors',
        highlighted && 'bg-accent/50',
        sequence.enabled === false && 'opacity-50'
      )}
    >
      <span className="text-sm text-muted-foreground">
        {sequence.description}
      </span>
      <SequenceBadge sequence={sequence.sequence} />
    </div>
  );
}

// ==================== Main Component ====================

export function KeyboardShortcutsHelp({
  open,
  onOpenChange,
  shortcuts,
  sequences = [],
  additionalContent,
}: KeyboardShortcutsHelpProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Focus search input when modal opens
  useEffect(() => {
    if (open && searchInputRef.current) {
      // Small delay to ensure modal is fully rendered
      const timer = setTimeout(() => {
        searchInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Clear search when modal closes
  useEffect(() => {
    if (!open) {
      setSearchQuery('');
    }
  }, [open]);

  // Filter shortcuts based on search
  const filteredShortcuts = useMemo(() => {
    if (!searchQuery.trim()) return shortcuts;

    const query = searchQuery.toLowerCase();
    return shortcuts.filter(s =>
      s.description.toLowerCase().includes(query) ||
      s.keys.toLowerCase().includes(query) ||
      s.id.toLowerCase().includes(query)
    );
  }, [shortcuts, searchQuery]);

  // Filter sequences based on search
  const filteredSequences = useMemo(() => {
    if (!searchQuery.trim()) return sequences;

    const query = searchQuery.toLowerCase();
    return sequences.filter(s =>
      s.description.toLowerCase().includes(query) ||
      s.sequence.join(' ').toLowerCase().includes(query) ||
      s.id.toLowerCase().includes(query)
    );
  }, [sequences, searchQuery]);

  // Group shortcuts by category
  const groupedShortcuts = useMemo(() => {
    const groups: Record<ShortcutCategory, KeyboardShortcut[]> = {
      navigation: [],
      actions: [],
      documents: [],
      forms: [],
      help: [],
    };

    filteredShortcuts.forEach(shortcut => {
      const category = shortcut.category || 'help';
      if (groups[category]) {
        groups[category].push(shortcut);
      }
    });

    return groups;
  }, [filteredShortcuts]);

  // Group sequences by category
  const groupedSequences = useMemo(() => {
    const groups: Record<ShortcutCategory, KeySequence[]> = {
      navigation: [],
      actions: [],
      documents: [],
      forms: [],
      help: [],
    };

    filteredSequences.forEach(seq => {
      const category = seq.category || 'navigation';
      if (groups[category]) {
        groups[category].push(seq);
      }
    });

    return groups;
  }, [filteredSequences]);

  // Categories with content
  const activeCategories = categoryOrder.filter(
    cat => groupedShortcuts[cat].length > 0 || groupedSequences[cat].length > 0
  );

  const hasResults = filteredShortcuts.length > 0 || filteredSequences.length > 0;
  const isSearching = searchQuery.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg max-h-[85vh] flex flex-col"
        aria-describedby="keyboard-shortcuts-description"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="w-5 h-5" aria-hidden="true" />
            Tastenkürzel
          </DialogTitle>
          <DialogDescription id="keyboard-shortcuts-description">
            Nutzen Sie diese Tastenkürzel für schnellere Navigation und Aktionen.
          </DialogDescription>
        </DialogHeader>

        {/* Search Input */}
        <div className="relative">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            ref={searchInputRef}
            type="search"
            placeholder="Tastenkürzel suchen..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="pl-9"
            aria-label="Tastenkürzel suchen"
          />
        </div>

        {/* Shortcuts List */}
        <ScrollArea className="flex-1 -mx-6 px-6">
          <div className="space-y-6 py-4">
            {hasResults ? (
              activeCategories.map(category => {
                const config = categoryConfig[category];
                const Icon = config.icon;
                const categoryShortcuts = groupedShortcuts[category];
                const categorySequences = groupedSequences[category];

                if (categoryShortcuts.length === 0 && categorySequences.length === 0) {
                  return null;
                }

                return (
                  <div key={category} className="space-y-3">
                    {/* Category Header */}
                    <div className="flex items-center gap-2">
                      <Icon className={cn('w-4 h-4', config.color)} aria-hidden="true" />
                      <h3 className="font-medium text-sm">{config.label}</h3>
                    </div>

                    {/* Category Description */}
                    <p className="text-xs text-muted-foreground pl-6">
                      {config.description}
                    </p>

                    {/* Shortcuts List */}
                    <div className="space-y-1 pl-6">
                      {categoryShortcuts.map(shortcut => (
                        <ShortcutRow
                          key={shortcut.id}
                          shortcut={shortcut}
                          highlighted={isSearching}
                        />
                      ))}
                      {categorySequences.map(seq => (
                        <SequenceRow
                          key={seq.id}
                          sequence={seq}
                          highlighted={isSearching}
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="py-8 text-center">
                <Search className="w-10 h-10 mx-auto mb-3 text-muted-foreground/50" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">
                  Keine Tastenkürzel gefunden für "{searchQuery}"
                </p>
              </div>
            )}

            {/* Additional Content */}
            {additionalContent && (
              <div className="pt-4 border-t border-border">
                {additionalContent}
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Footer */}
        <div className="pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground text-center">
            Drücken Sie <ShortcutBadge keys="?" className="mx-1 inline-flex" /> jederzeit, um diese Hilfe anzuzeigen.
            <br />
            <span className="mt-1 block">
              <ShortcutBadge keys="escape" className="mx-1 inline-flex" /> zum Schließen
            </span>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ==================== Inline Shortcut Hint ====================

/**
 * Inline shortcut hint for tooltips and buttons
 */
export function ShortcutHint({
  keys,
  className,
}: {
  keys: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'ml-2 text-xs text-muted-foreground opacity-75',
        className
      )}
    >
      ({formatShortcutKeys(keys)})
    </span>
  );
}

/**
 * Keyboard indicator component for showing pending sequence
 */
export function PendingSequenceIndicator({
  sequence,
  className,
}: {
  sequence: string[];
  className?: string;
}) {
  if (sequence.length === 0) return null;

  return (
    <div
      className={cn(
        'fixed bottom-4 right-4 z-50',
        'bg-popover border rounded-lg shadow-lg p-3',
        'animate-in fade-in slide-in-from-bottom-2',
        className
      )}
      role="status"
      aria-live="polite"
      aria-label="Tastenkombination in Bearbeitung"
    >
      <div className="flex items-center gap-2">
        <Keyboard className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
        <span className="text-sm">Tastenkombination:</span>
        <SequenceBadge sequence={sequence} />
      </div>
    </div>
  );
}

// ==================== Exports ====================

export default KeyboardShortcutsHelp;
