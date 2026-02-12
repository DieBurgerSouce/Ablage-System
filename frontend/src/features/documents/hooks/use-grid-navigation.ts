/**
 * useGridNavigation - Keyboard Navigation Hook für DocumentGrid
 *
 * Features:
 * - Pfeiltasten-Navigation in Grid/Liste
 * - Space zum Togglen der Auswahl
 * - Enter zum Öffnen des Dokuments
 * - Shift+Pfeil für Range-Selektion
 * - Ctrl/Cmd+A für Alle auswählen
 * - Escape zum Aufheben der Auswahl
 * - Home/End für erstes/letztes Element
 *
 * WCAG 2.1 AA konform mit Fokus-Management
 */

import { useState, useCallback, useEffect, useRef } from 'react';

// ==================== Types ====================

interface UseGridNavigationOptions {
  /** Anzahl der Items im Grid */
  itemCount: number;

  /** Anzahl der Spalten im Grid (1 für List-View) */
  columnCount: number;

  /** IDs aller Dokumente */
  documentIds: string[];

  /** Aktuell ausgewählte IDs */
  selectedIds: string[];

  /** Callback wenn ein Item ausgewählt/abgewählt wird */
  onSelect: (id: string, selected: boolean) => void;

  /** Callback wenn ein Dokument geöffnet werden soll */
  onOpen: (id: string) => void;

  /** Callback um alle auszuwählen */
  onSelectAll?: () => void;

  /** Callback um Auswahl aufzuheben */
  onClearSelection?: () => void;

  /** Referenz zum Container-Element */
  containerRef: React.RefObject<HTMLElement>;

  /** Ist das Grid aktiv/fokussiert? */
  isEnabled?: boolean;
}

interface UseGridNavigationReturn {
  /** Aktuell fokussierter Index (-1 wenn keiner) */
  focusedIndex: number;

  /** Setzt den fokussierten Index */
  setFocusedIndex: (index: number) => void;

  /** Event-Handler für Tastatur-Events */
  handleKeyDown: (event: React.KeyboardEvent) => void;

  /** Props zum Anwenden auf Items */
  getItemProps: (index: number) => {
    tabIndex: number;
    'data-focused': boolean;
    'aria-selected': boolean;
    onFocus: () => void;
  };

  /** Scrollt das fokussierte Element in den sichtbaren Bereich */
  scrollFocusedIntoView: () => void;
}

// ==================== Hook ====================

export function useGridNavigation({
  itemCount,
  columnCount,
  documentIds,
  selectedIds,
  onSelect,
  onOpen,
  onSelectAll,
  onClearSelection,
  containerRef,
  isEnabled = true,
}: UseGridNavigationOptions): UseGridNavigationReturn {
  const [focusedIndex, setFocusedIndex] = useState(-1);

  // Referenz für Range-Selektion Startpunkt
  const rangeStartRef = useRef<number>(-1);

  // Hilfsfunktion: Berechnet den neuen Index basierend auf Richtung
  const calculateNewIndex = useCallback(
    (currentIndex: number, direction: 'up' | 'down' | 'left' | 'right'): number => {
      if (itemCount === 0) return -1;

      // Wenn noch nichts fokussiert, starte bei 0
      if (currentIndex < 0) return 0;

      switch (direction) {
        case 'up':
          return Math.max(0, currentIndex - columnCount);
        case 'down':
          return Math.min(itemCount - 1, currentIndex + columnCount);
        case 'left':
          return Math.max(0, currentIndex - 1);
        case 'right':
          return Math.min(itemCount - 1, currentIndex + 1);
        default:
          return currentIndex;
      }
    },
    [columnCount, itemCount]
  );

  // Range-Selektion zwischen zwei Indizes
  const selectRange = useCallback(
    (startIndex: number, endIndex: number) => {
      const minIndex = Math.min(startIndex, endIndex);
      const maxIndex = Math.max(startIndex, endIndex);

      for (let i = minIndex; i <= maxIndex; i++) {
        const id = documentIds[i];
        if (id && !selectedIds.includes(id)) {
          onSelect(id, true);
        }
      }
    },
    [documentIds, selectedIds, onSelect]
  );

  // Tastatur-Handler
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (!isEnabled || itemCount === 0) return;

      const { key, shiftKey, ctrlKey, metaKey } = event;
      const isModifierPressed = ctrlKey || metaKey;

      switch (key) {
        case 'ArrowUp':
          event.preventDefault();
          const upIndex = calculateNewIndex(focusedIndex, 'up');
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, upIndex);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, upIndex);
          }
          setFocusedIndex(upIndex);
          break;

        case 'ArrowDown':
          event.preventDefault();
          const downIndex = calculateNewIndex(focusedIndex, 'down');
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, downIndex);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, downIndex);
          }
          setFocusedIndex(downIndex);
          break;

        case 'ArrowLeft':
          event.preventDefault();
          const leftIndex = calculateNewIndex(focusedIndex, 'left');
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, leftIndex);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, leftIndex);
          }
          setFocusedIndex(leftIndex);
          break;

        case 'ArrowRight':
          event.preventDefault();
          const rightIndex = calculateNewIndex(focusedIndex, 'right');
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, rightIndex);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, rightIndex);
          }
          setFocusedIndex(rightIndex);
          break;

        case ' ': // Space
          event.preventDefault();
          if (focusedIndex >= 0 && focusedIndex < documentIds.length) {
            const id = documentIds[focusedIndex];
            const isSelected = selectedIds.includes(id);
            onSelect(id, !isSelected);
            // Setze Range-Start für Shift-Klick
            rangeStartRef.current = focusedIndex;
          }
          break;

        case 'Enter':
          event.preventDefault();
          if (focusedIndex >= 0 && focusedIndex < documentIds.length) {
            const id = documentIds[focusedIndex];
            onOpen(id);
          }
          break;

        case 'Home':
          event.preventDefault();
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, 0);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, 0);
          }
          setFocusedIndex(0);
          break;

        case 'End':
          event.preventDefault();
          const lastIndex = itemCount - 1;
          if (shiftKey && rangeStartRef.current >= 0) {
            selectRange(rangeStartRef.current, lastIndex);
          } else if (shiftKey) {
            rangeStartRef.current = focusedIndex >= 0 ? focusedIndex : 0;
            selectRange(rangeStartRef.current, lastIndex);
          }
          setFocusedIndex(lastIndex);
          break;

        case 'a':
        case 'A':
          if (isModifierPressed) {
            event.preventDefault();
            onSelectAll?.();
          }
          break;

        case 'Escape':
          event.preventDefault();
          onClearSelection?.();
          rangeStartRef.current = -1;
          break;

        default:
          // Ignoriere andere Tasten
          break;
      }
    },
    [
      isEnabled,
      itemCount,
      focusedIndex,
      documentIds,
      selectedIds,
      calculateNewIndex,
      selectRange,
      onSelect,
      onOpen,
      onSelectAll,
      onClearSelection,
    ]
  );

  // Props für Items
  const getItemProps = useCallback(
    (index: number) => {
      const id = documentIds[index];
      const isFocused = focusedIndex === index;
      const isSelected = selectedIds.includes(id);

      return {
        tabIndex: isFocused ? 0 : -1,
        'data-focused': isFocused,
        'aria-selected': isSelected,
        onFocus: () => setFocusedIndex(index),
      };
    },
    [focusedIndex, documentIds, selectedIds]
  );

  // Scrolle fokussiertes Element in den sichtbaren Bereich
  const scrollFocusedIntoView = useCallback(() => {
    if (focusedIndex < 0 || !containerRef.current) return;

    const container = containerRef.current;
    const focusedElement = container.querySelector(`[data-focused="true"]`);

    if (focusedElement) {
      focusedElement.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'nearest',
      });
    }
  }, [focusedIndex, containerRef]);

  // Auto-scroll wenn sich der fokussierte Index ändert
  useEffect(() => {
    scrollFocusedIntoView();
  }, [focusedIndex, scrollFocusedIntoView]);

  // Setze Fokus zurück wenn Items sich ändern
  useEffect(() => {
    if (focusedIndex >= itemCount) {
      setFocusedIndex(Math.max(0, itemCount - 1));
    }
  }, [itemCount, focusedIndex]);

  return {
    focusedIndex,
    setFocusedIndex,
    handleKeyDown,
    getItemProps,
    scrollFocusedIntoView,
  };
}

export default useGridNavigation;
