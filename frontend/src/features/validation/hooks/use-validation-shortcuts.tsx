/**
 * Validation Queue Keyboard Shortcuts Hook
 *
 * Stellt Keyboard-Shortcuts fuer die Validierungs-Queue bereit.
 * Shortcuts:
 * - A: Genehmigen (Approve)
 * - R: Ablehnen (Reject)
 * - J: Naechstes Item
 * - K: Vorheriges Item
 * - Enter/Space: Item oeffnen
 * - Escape: Auswahl aufheben
 */

import { useHotkeys } from 'react-hotkeys-hook';
import { useCallback, useRef } from 'react';
import type { Options as HotkeysOptions } from 'react-hotkeys-hook';

export interface ValidationShortcutHandlers {
  /** Genehmigt das aktuell ausgewaehlte Item */
  onApprove?: () => void;
  /** Lehnt das aktuell ausgewaehlte Item ab */
  onReject?: () => void;
  /** Geht zum naechsten Item */
  onNext?: () => void;
  /** Geht zum vorherigen Item */
  onPrev?: () => void;
  /** Oeffnet das aktuelle Item */
  onOpen?: () => void;
  /** Hebt die Auswahl auf */
  onClear?: () => void;
  /** Markiert alle Items */
  onSelectAll?: () => void;
}

export interface UseValidationShortcutsOptions {
  /** Ob Shortcuts aktiviert sind (z.B. deaktivieren wenn Dialog offen) */
  enabled?: boolean;
  /** Scope fuer die Shortcuts (default: 'validation-queue') */
  scope?: string;
}

/**
 * Hook fuer Validation Queue Keyboard Shortcuts.
 *
 * @example
 * ```tsx
 * useValidationShortcuts({
 *   onApprove: () => handleApprove(selectedItem),
 *   onReject: () => handleReject(selectedItem),
 *   onNext: () => selectNext(),
 *   onPrev: () => selectPrev(),
 * }, { enabled: !dialogOpen });
 * ```
 */
export function useValidationShortcuts(
  handlers: ValidationShortcutHandlers,
  options: UseValidationShortcutsOptions = {}
) {
  const { enabled = true, scope = 'validation-queue' } = options;

  // Refs fuer Handler um unnoetige Re-registrierungen zu vermeiden
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  // Gemeinsame Hotkeys-Optionen
  const baseOptions: HotkeysOptions = {
    enabled,
    enableOnFormTags: false, // Nicht in Input/Textarea aktiv
    preventDefault: true,
    scopes: [scope],
  };

  // A - Approve (Genehmigen)
  useHotkeys(
    'a',
    useCallback(() => {
      handlersRef.current.onApprove?.();
    }, []),
    { ...baseOptions, description: 'Item genehmigen' }
  );

  // R - Reject (Ablehnen)
  useHotkeys(
    'r',
    useCallback(() => {
      handlersRef.current.onReject?.();
    }, []),
    { ...baseOptions, description: 'Item ablehnen' }
  );

  // J - Next (Naechstes)
  useHotkeys(
    'j',
    useCallback(() => {
      handlersRef.current.onNext?.();
    }, []),
    { ...baseOptions, description: 'Naechstes Item' }
  );

  // K - Previous (Vorheriges)
  useHotkeys(
    'k',
    useCallback(() => {
      handlersRef.current.onPrev?.();
    }, []),
    { ...baseOptions, description: 'Vorheriges Item' }
  );

  // Enter/Space - Open (Oeffnen)
  useHotkeys(
    'enter, space',
    useCallback(() => {
      handlersRef.current.onOpen?.();
    }, []),
    { ...baseOptions, description: 'Item oeffnen' }
  );

  // Escape - Clear selection (Auswahl aufheben)
  useHotkeys(
    'escape',
    useCallback(() => {
      handlersRef.current.onClear?.();
    }, []),
    { ...baseOptions, description: 'Auswahl aufheben' }
  );

  // Ctrl/Cmd + A - Select all (Alle auswaehlen)
  useHotkeys(
    'mod+a',
    useCallback(() => {
      handlersRef.current.onSelectAll?.();
    }, []),
    { ...baseOptions, description: 'Alle auswaehlen' }
  );
}

/**
 * Konstanten fuer Shortcut-Labels in der UI
 */
export const VALIDATION_SHORTCUTS = {
  approve: { key: 'A', label: 'Genehmigen' },
  reject: { key: 'R', label: 'Ablehnen' },
  next: { key: 'J', label: 'Naechstes' },
  prev: { key: 'K', label: 'Vorheriges' },
  open: { key: 'Enter', label: 'Oeffnen' },
  clear: { key: 'Esc', label: 'Abbrechen' },
  selectAll: { key: 'Ctrl+A', label: 'Alle' },
} as const;

/**
 * Komponente zum Anzeigen der Keyboard-Shortcuts Hilfe
 */
export function ShortcutHelpText() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1">
        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">A</kbd>
        <span>Genehmigen</span>
      </span>
      <span className="flex items-center gap-1">
        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">R</kbd>
        <span>Ablehnen</span>
      </span>
      <span className="flex items-center gap-1">
        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">J</kbd>
        /
        <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">K</kbd>
        <span>Navigation</span>
      </span>
    </div>
  );
}
