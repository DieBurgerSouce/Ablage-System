/**
 * useSessionResume - Verfolgt die zuletzt besuchte Route
 *
 * Ermöglicht "Weiter wo Sie aufgehört haben"-Funktionalität.
 * Sitzungsdaten verfallen automatisch nach 24 Stunden.
 *
 * @example
 * ```tsx
 * const { lastRoute, isResumeAvailable, recordVisit } = useSessionResume();
 * if (isResumeAvailable && lastRoute) {
 *   navigate(lastRoute);
 * }
 * ```
 */

import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './use-local-storage';

// ==================== Types ====================

interface SessionState {
  lastRoute: string;
  lastVisitedAt: number;
}

interface UseSessionResumeReturn {
  /** Zuletzt besuchter Routenpfad */
  lastRoute: string | null;
  /** Zeitpunkt des letzten Besuchs */
  lastVisitedAt: Date | null;
  /** Aktuellen Routenbesuch aufzeichnen */
  recordVisit: (pathname: string) => void;
  /** Sitzungsdaten löschen */
  clearSession: () => void;
  /** Ob eine fortsetzbare Sitzung existiert (nicht abgelaufen, Route vorhanden) */
  isResumeAvailable: boolean;
}

// ==================== Constants ====================

const STORAGE_KEY = 'ablage-session-resume';

/** 24 Stunden in Millisekunden */
const EXPIRY_MS = 24 * 60 * 60 * 1000;

/** Statische Pfade die nicht aufgezeichnet werden */
const IGNORED_PATHS = new Set(['/', '/login', '/404', '/logout', '/register']);

// ==================== Hook ====================

export function useSessionResume(): UseSessionResumeReturn {
  const [state, setState] = useLocalStorage<SessionState | null>(STORAGE_KEY, null);

  const isExpired = useMemo(() => {
    if (!state) return true;
    return Date.now() - state.lastVisitedAt > EXPIRY_MS;
  }, [state]);

  const isResumeAvailable = state !== null && !isExpired;

  const lastRoute = useMemo(() => {
    if (!state || isExpired) return null;
    return state.lastRoute;
  }, [state, isExpired]);

  const lastVisitedAt = useMemo(() => {
    if (!state || isExpired) return null;
    return new Date(state.lastVisitedAt);
  }, [state, isExpired]);

  const recordVisit = useCallback(
    (pathname: string) => {
      if (IGNORED_PATHS.has(pathname)) return;
      setState({
        lastRoute: pathname,
        lastVisitedAt: Date.now(),
      });
    },
    [setState]
  );

  const clearSession = useCallback(() => {
    setState(null);
  }, [setState]);

  return {
    lastRoute,
    lastVisitedAt,
    recordVisit,
    clearSession,
    isResumeAvailable,
  };
}
