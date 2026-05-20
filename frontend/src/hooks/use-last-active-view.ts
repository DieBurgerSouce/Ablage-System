/**
 * useLastActiveView - Merkt sich den zuletzt aktiven Tab/View pro Seite
 *
 * Dünner Wrapper um useLocalStorage, der den zuletzt ausgewählten
 * View-Modus (z.B. 'grid' / 'list' / 'kanban') pro Seite speichert.
 *
 * @example
 * ```tsx
 * const [activeView, setActiveView] = useLastActiveView('documents', 'grid');
 * ```
 */

import { useCallback } from 'react';
import { useLocalStorage } from './use-local-storage';

export function useLastActiveView(
  pageKey: string,
  defaultView: string
): [string, (view: string) => void] {
  const storageKey = `ablage-last-view-${pageKey}`;
  const [storedView, setStoredView] = useLocalStorage<string>(storageKey, defaultView);

  const setView = useCallback(
    (view: string) => {
      setStoredView(view);
    },
    [setStoredView]
  );

  return [storedView, setView];
}
