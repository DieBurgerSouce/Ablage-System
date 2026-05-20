/**
 * Progressive Disclosure - User Mode Hook
 *
 * Persistiert Einsteiger/Experte-Modus in localStorage.
 * Im Einsteiger-Modus werden zusaetzliche Hilfe-Tooltips angezeigt.
 */

import { useLocalStorage } from '@/hooks/use-local-storage';
import { useCallback } from 'react';

export type UserMode = 'beginner' | 'expert';

const USER_MODE_STORAGE_KEY = 'ablage-user-mode';

export function useUserMode() {
  const [mode, setModeRaw] = useLocalStorage<UserMode>(
    USER_MODE_STORAGE_KEY,
    'beginner',
  );

  const setMode = useCallback(
    (newMode: UserMode) => {
      setModeRaw(newMode);
    },
    [setModeRaw],
  );

  return {
    mode,
    setMode,
    isBeginner: mode === 'beginner',
    isExpert: mode === 'expert',
  };
}
