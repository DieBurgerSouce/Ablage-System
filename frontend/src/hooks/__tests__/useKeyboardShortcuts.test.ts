/**
 * Tests for useKeyboardShortcuts hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
// Note: The source file is useKeyboardShortcuts.tsx but TS resolves without extension
import {
  matchesShortcut,
  formatShortcutKeys,
  formatKeySequence,
  SHORTCUT_CATEGORY_LABELS,
  SHORTCUT_LABELS,
} from '../useKeyboardShortcuts';

describe('matchesShortcut', () => {
  const createKeyboardEvent = (
    key: string,
    options: { ctrlKey?: boolean; altKey?: boolean; shiftKey?: boolean; metaKey?: boolean } = {}
  ): KeyboardEvent => {
    return new KeyboardEvent('keydown', {
      key,
      ctrlKey: options.ctrlKey ?? false,
      altKey: options.altKey ?? false,
      shiftKey: options.shiftKey ?? false,
      metaKey: options.metaKey ?? false,
      bubbles: true,
    });
  };

  describe('simple keys', () => {
    it('should match single letter key', () => {
      const event = createKeyboardEvent('a');
      expect(matchesShortcut(event, 'a')).toBe(true);
    });

    it('should match question mark', () => {
      const event = createKeyboardEvent('?');
      expect(matchesShortcut(event, '?')).toBe(true);
    });

    it('should match forward slash', () => {
      const event = createKeyboardEvent('/');
      expect(matchesShortcut(event, '/')).toBe(true);
    });

    it('should not match wrong key', () => {
      const event = createKeyboardEvent('b');
      expect(matchesShortcut(event, 'a')).toBe(false);
    });
  });

  describe('special keys', () => {
    it('should match Escape', () => {
      const event = createKeyboardEvent('Escape');
      expect(matchesShortcut(event, 'escape')).toBe(true);
      expect(matchesShortcut(event, 'esc')).toBe(true);
    });

    it('should match Enter', () => {
      const event = createKeyboardEvent('Enter');
      expect(matchesShortcut(event, 'enter')).toBe(true);
    });

    it('should match arrow keys', () => {
      expect(matchesShortcut(createKeyboardEvent('ArrowUp'), 'arrowup')).toBe(true);
      expect(matchesShortcut(createKeyboardEvent('ArrowDown'), 'arrowdown')).toBe(true);
      expect(matchesShortcut(createKeyboardEvent('ArrowLeft'), 'arrowleft')).toBe(true);
      expect(matchesShortcut(createKeyboardEvent('ArrowRight'), 'arrowright')).toBe(true);
    });

    it('should match Home and End', () => {
      expect(matchesShortcut(createKeyboardEvent('Home'), 'home')).toBe(true);
      expect(matchesShortcut(createKeyboardEvent('End'), 'end')).toBe(true);
    });
  });

  describe('modifier keys', () => {
    it('should match Ctrl+K', () => {
      const event = createKeyboardEvent('k', { ctrlKey: true });
      expect(matchesShortcut(event, 'ctrl+k')).toBe(true);
    });

    it('should match Alt+H', () => {
      const event = createKeyboardEvent('h', { altKey: true });
      expect(matchesShortcut(event, 'alt+h')).toBe(true);
    });

    it('should match Shift+Z', () => {
      const event = createKeyboardEvent('z', { shiftKey: true });
      expect(matchesShortcut(event, 'shift+z')).toBe(true);
    });

    it('should match Ctrl+Shift+Z', () => {
      const event = createKeyboardEvent('z', { ctrlKey: true, shiftKey: true });
      expect(matchesShortcut(event, 'ctrl+shift+z')).toBe(true);
    });

    it('should match Cmd+K (meta key)', () => {
      const event = createKeyboardEvent('k', { metaKey: true });
      expect(matchesShortcut(event, 'ctrl+k')).toBe(true);
      expect(matchesShortcut(event, 'cmd+k')).toBe(true);
    });

    it('should not match when modifiers are missing', () => {
      const event = createKeyboardEvent('k'); // No Ctrl
      expect(matchesShortcut(event, 'ctrl+k')).toBe(false);
    });

    it('should not match when extra modifiers are present', () => {
      const event = createKeyboardEvent('k', { ctrlKey: true, altKey: true });
      expect(matchesShortcut(event, 'ctrl+k')).toBe(false);
    });
  });

  describe('complex combinations', () => {
    it('should match Ctrl+Enter', () => {
      const event = createKeyboardEvent('Enter', { ctrlKey: true });
      expect(matchesShortcut(event, 'ctrl+enter')).toBe(true);
    });

    it('should match Ctrl+Alt+Delete', () => {
      const event = createKeyboardEvent('Delete', { ctrlKey: true, altKey: true });
      expect(matchesShortcut(event, 'ctrl+alt+delete')).toBe(true);
    });
  });
});

describe('formatShortcutKeys', () => {
  // Note: These tests assume non-Mac platform
  // We can't easily mock navigator.platform in Vitest

  it('should format simple keys', () => {
    expect(formatShortcutKeys('a')).toBe('A');
    expect(formatShortcutKeys('?')).toBe('?');
    expect(formatShortcutKeys('/')).toBe('/');
  });

  it('should format special keys', () => {
    expect(formatShortcutKeys('escape')).toBe('Esc');
    expect(formatShortcutKeys('enter')).toBe('↵');
    expect(formatShortcutKeys('space')).toBe('Leertaste');
    expect(formatShortcutKeys('backspace')).toBe('⌫');
    expect(formatShortcutKeys('tab')).toBe('⇥');
  });

  it('should format arrow keys', () => {
    expect(formatShortcutKeys('arrowup')).toBe('↑');
    expect(formatShortcutKeys('arrowdown')).toBe('↓');
    expect(formatShortcutKeys('arrowleft')).toBe('←');
    expect(formatShortcutKeys('arrowright')).toBe('→');
  });

  it('should format German-specific keys', () => {
    expect(formatShortcutKeys('home')).toBe('Pos1');
    expect(formatShortcutKeys('end')).toBe('Ende');
  });

  it('should format modifier combinations', () => {
    const result = formatShortcutKeys('ctrl+k');
    expect(result).toContain('Ctrl');
    expect(result).toContain('K');
  });

  it('should format shift modifier', () => {
    const result = formatShortcutKeys('shift+z');
    expect(result).toContain('⇧');
    expect(result).toContain('Z');
  });
});

describe('formatKeySequence', () => {
  it('should format a simple sequence', () => {
    const result = formatKeySequence(['g', 'd']);
    expect(result).toContain('G');
    expect(result).toContain('D');
    expect(result).toContain('→');
  });

  it('should format a longer sequence', () => {
    const result = formatKeySequence(['g', 'g', 't']);
    expect(result).toContain('G');
    expect(result).toContain('T');
  });
});

describe('German labels', () => {
  it('should have all category labels in German', () => {
    expect(SHORTCUT_CATEGORY_LABELS.navigation).toBe('Navigation');
    expect(SHORTCUT_CATEGORY_LABELS.actions).toBe('Aktionen');
    expect(SHORTCUT_CATEGORY_LABELS.documents).toBe('Dokumente');
    expect(SHORTCUT_CATEGORY_LABELS.forms).toBe('Formulare');
    expect(SHORTCUT_CATEGORY_LABELS.help).toBe('Hilfe');
  });

  it('should have all shortcut labels in German', () => {
    expect(SHORTCUT_LABELS.delete).toBe('Löschen');
    expect(SHORTCUT_LABELS.move).toBe('Verschieben');
    expect(SHORTCUT_LABELS.undo).toBe('Rückgängig');
    expect(SHORTCUT_LABELS.redo).toBe('Wiederholen');
    expect(SHORTCUT_LABELS.search).toBe('Suche');
    expect(SHORTCUT_LABELS.help).toBe('Hilfe');
    expect(SHORTCUT_LABELS.save).toBe('Speichern');
    expect(SHORTCUT_LABELS.submit).toBe('Absenden');
    expect(SHORTCUT_LABELS.cancel).toBe('Abbrechen');
  });
});
