/**
 * useHotkeys - Custom Hook for Keyboard Shortcuts
 *
 * Features:
 * - Support for key sequences like 'g d' (press g then d)
 * - Global shortcuts that work anywhere in the app
 * - Automatic disabling when user is typing in input fields
 * - Modifier key support (Ctrl, Alt, Shift, Meta/Cmd)
 * - Platform-aware key display (Mac vs Windows)
 * - Conflict detection
 *
 * Uses react-hotkeys-hook internally for efficient event handling
 *
 * WCAG 2.1 AA konform
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useHotkeys as useHotkeysHook, type Options } from 'react-hotkeys-hook';
import type { KeyboardShortcut, KeySequence, ShortcutScope } from '../types/shortcut-types';
import { DEFAULT_SEQUENCE_TIMEOUT, PROTECTED_SHORTCUTS } from '../types/shortcut-types';

// ==================== Utilities ====================

/**
 * Check if the target element is an input field where shortcuts should be disabled
 */
export function isInputElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  const tagName = target.tagName.toLowerCase();
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    tagName === 'select' ||
    target.isContentEditable ||
    target.getAttribute('role') === 'textbox' ||
    target.getAttribute('role') === 'combobox'
  );
}

/**
 * Normalize a key combination string for comparison
 */
export function normalizeKeys(keys: string): string {
  return keys
    .toLowerCase()
    .split('+')
    .map(part => {
      const trimmed = part.trim();
      if (trimmed === 'cmd' || trimmed === 'command' || trimmed === 'meta') return 'ctrl';
      if (trimmed === 'esc') return 'escape';
      return trimmed;
    })
    .sort((a, b) => {
      const order: Record<string, number> = { ctrl: 1, alt: 2, shift: 3 };
      return (order[a] ?? 99) - (order[b] ?? 99);
    })
    .join('+');
}

/**
 * Convert our key format to react-hotkeys-hook format
 */
function toHotkeyFormat(keys: string): string {
  return keys
    .toLowerCase()
    .replace(/cmd/g, 'meta')
    .replace(/command/g, 'meta')
    .trim();
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
      if (lower === 'ctrl' || lower === 'cmd' || lower === 'meta') return isMac ? '\u2318' : 'Strg';
      if (lower === 'alt') return isMac ? '\u2325' : 'Alt';
      if (lower === 'shift') return '\u21E7';
      if (lower === 'escape' || lower === 'esc') return 'Esc';
      if (lower === 'enter') return '\u21B5';
      if (lower === 'space') return 'Leertaste';
      if (lower === 'backspace') return '\u232B';
      if (lower === 'delete') return isMac ? '\u2326' : 'Entf';
      if (lower === 'tab') return '\u21E5';
      if (lower === 'arrowup' || lower === 'up') return '\u2191';
      if (lower === 'arrowdown' || lower === 'down') return '\u2193';
      if (lower === 'arrowleft' || lower === 'left') return '\u2190';
      if (lower === 'arrowright' || lower === 'right') return '\u2192';
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
  return sequence.map(key => formatShortcutKeys(key)).join(' \u2192 ');
}

/**
 * Check if shortcut matches keyboard event
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
    return ctrlMatch && altMatch && event.key === '?';
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
      keyMatch = event.key === '/' || event.code === 'Slash';
      break;
    default:
      keyMatch = event.key.toLowerCase() === key;
  }

  return ctrlMatch && altMatch && shiftMatch && keyMatch;
}

// ==================== Main Hook ====================

export interface UseHotkeysOptions {
  /** Whether to enable the shortcut */
  enabled?: boolean;
  /** Scope where shortcut is active */
  scope?: ShortcutScope;
  /** Current active scope */
  activeScope?: ShortcutScope;
  /** Whether to prevent default browser behavior */
  preventDefault?: boolean;
  /** Whether to stop event propagation */
  stopPropagation?: boolean;
  /** Whether shortcut should work when typing in inputs */
  enableOnFormTags?: boolean;
  /** Additional options for react-hotkeys-hook */
  hotkeyOptions?: Partial<Options>;
}

/**
 * Hook for registering a single keyboard shortcut
 */
export function useHotkey(
  keys: string,
  callback: (event: KeyboardEvent) => void,
  options: UseHotkeysOptions = {}
) {
  const {
    enabled = true,
    scope,
    activeScope = 'global',
    preventDefault = true,
    stopPropagation = false,
    enableOnFormTags = false,
    hotkeyOptions = {},
  } = options;

  // Check if scope matches
  const isActive = !scope || scope === 'global' || scope === activeScope;

  // Convert keys to react-hotkeys-hook format
  const hotkeyKeys = toHotkeyFormat(keys);

  // Check for protected shortcuts
  const isProtected = PROTECTED_SHORTCUTS.has(normalizeKeys(keys));

  useHotkeysHook(
    hotkeyKeys,
    (event: KeyboardEvent) => {
      // Skip protected browser shortcuts
      if (isProtected) return;

      // Check if typing in input
      if (!enableOnFormTags && isInputElement(event.target)) {
        // Allow ? and Escape even in inputs
        const allowInInput = keys === '?' || keys.toLowerCase() === 'escape';
        if (!allowInInput) return;
      }

      if (preventDefault) {
        event.preventDefault();
      }

      if (stopPropagation) {
        event.stopPropagation();
      }

      callback(event);
    },
    {
      enabled: enabled && isActive,
      enableOnFormTags: enableOnFormTags
        ? ['INPUT', 'TEXTAREA', 'SELECT']
        : undefined,
      ...hotkeyOptions,
    },
    [callback, enabled, isActive, preventDefault, stopPropagation, enableOnFormTags]
  );
}

/**
 * Hook for registering multiple shortcuts at once
 */
export function useHotkeys(
  shortcuts: KeyboardShortcut[],
  options: Omit<UseHotkeysOptions, 'enableOnFormTags'> = {}
) {
  const { activeScope = 'global' } = options;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isTyping = isInputElement(event.target);

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

          // Allow ? and Escape even when typing
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
  }, [shortcuts, activeScope]);
}

// ==================== Key Sequence Hook ====================

export interface UseKeySequenceOptions {
  /** Whether sequence is enabled */
  enabled?: boolean;
  /** Timeout for sequence completion (ms) */
  timeout?: number;
  /** Whether sequence should work when typing in inputs */
  enableOnFormTags?: boolean;
}

/**
 * Hook for handling key sequences (e.g., 'g d' for go to dashboard)
 */
export function useKeySequence(
  sequences: KeySequence[],
  options: UseKeySequenceOptions = {}
) {
  const { enabled = true, timeout = DEFAULT_SEQUENCE_TIMEOUT, enableOnFormTags = false } = options;

  const [pendingSequence, setPendingSequence] = useState<string[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear sequence and timeout
  const clearSequence = useCallback(() => {
    setPendingSequence([]);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || sequences.length === 0) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      const isTyping = isInputElement(event.target);

      // Skip if typing (unless enabled)
      if (!enableOnFormTags && isTyping) return;

      const eventKey = event.key.toLowerCase();

      // Ignore modifier keys on their own
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

        // Set timeout to clear sequence
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }
        timeoutRef.current = setTimeout(clearSequence, timeout);
      } else if (pendingSequence.length > 0) {
        // No match - clear pending sequence
        clearSequence();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enabled, sequences, pendingSequence, timeout, enableOnFormTags, clearSequence]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return {
    pendingSequence,
    clearSequence,
    isSequencePending: pendingSequence.length > 0,
  };
}

// ==================== Combined Hook ====================

export interface UseCombinedHotkeysResult {
  pendingSequence: string[];
  clearSequence: () => void;
  isSequencePending: boolean;
}

/**
 * Combined hook for both shortcuts and sequences
 */
export function useCombinedHotkeys(
  shortcuts: KeyboardShortcut[],
  sequences: KeySequence[],
  options: UseHotkeysOptions & UseKeySequenceOptions = {}
): UseCombinedHotkeysResult {
  const { activeScope = 'global', timeout = DEFAULT_SEQUENCE_TIMEOUT, enabled = true } = options;

  const [pendingSequence, setPendingSequence] = useState<string[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearSequence = useCallback(() => {
    setPendingSequence([]);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

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
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
          timeoutRef.current = setTimeout(clearSequence, timeout);
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
  }, [enabled, shortcuts, sequences, pendingSequence, activeScope, timeout, clearSequence]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return {
    pendingSequence,
    clearSequence,
    isSequencePending: pendingSequence.length > 0,
  };
}

// ==================== Scoped Shortcut Hook ====================

/**
 * Hook to register shortcuts for a specific scope
 * Useful for components that need their own shortcuts
 */
export function useScopedHotkeys(
  scope: ShortcutScope,
  shortcuts: KeyboardShortcut[],
  options: Omit<UseHotkeysOptions, 'scope' | 'activeScope'> = {}
) {
  useHotkeys(
    shortcuts.map(s => ({ ...s, scope })),
    { ...options, activeScope: scope }
  );
}

// ==================== Exports ====================

export {
  type KeyboardShortcut,
  type KeySequence,
  type ShortcutScope,
} from '../types/shortcut-types';
