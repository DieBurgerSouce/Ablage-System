/**
 * Spotlight Hook
 *
 * Haupthook fuer das Spotlight (Cmd+K) Feature.
 * Verwaltet Dialog-State, Suche mit Debouncing und Ergebnisse.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { spotlightService, SpotlightApiError } from '../api/spotlight-api';
import { QUERY_VOLATILE } from '@/lib/api/query-config';
import type { SpotlightResultsResponse } from '../types/spotlight-types';

// ==================== Query Keys ====================

export const spotlightQueryKeys = {
  all: ['spotlight'] as const,
  search: (query: string) => [...spotlightQueryKeys.all, 'search', query] as const,
};

// ==================== Debounce Hook ====================

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delayMs);

    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debouncedValue;
}

// ==================== Retry Config ====================

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    if (error instanceof SpotlightApiError && error.statusCode) {
      if (error.statusCode >= 400 && error.statusCode < 500) {
        return false;
      }
    }
    return failureCount < 2;
  },
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 10000),
} as const;

// ==================== Main Hook ====================

export interface UseSpotlightReturn {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  query: string;
  setQuery: (query: string) => void;
  debouncedQuery: string;
  results: SpotlightResultsResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
}

export function useSpotlight(): UseSpotlightReturn {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const previousOpenRef = useRef(false);

  const debouncedQuery = useDebouncedValue(query, 300);

  // Reset query und index beim Oeffnen/Schliessen
  useEffect(() => {
    if (isOpen && !previousOpenRef.current) {
      setQuery('');
      setSelectedIndex(0);
    }
    previousOpenRef.current = isOpen;
  }, [isOpen]);

  // Reset selectedIndex bei Query-Aenderung
  useEffect(() => {
    setSelectedIndex(0);
  }, [debouncedQuery]);

  // Suche nur ausfuehren wenn Query mindestens 2 Zeichen hat
  const searchEnabled = isOpen && debouncedQuery.length >= 2;

  const {
    data: results,
    isLoading,
    isError,
  } = useQuery({
    queryKey: spotlightQueryKeys.search(debouncedQuery),
    queryFn: () => spotlightService.search(debouncedQuery),
    enabled: searchEnabled,
    staleTime: QUERY_VOLATILE.staleTime,
    gcTime: QUERY_VOLATILE.gcTime,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  // Globaler Keyboard Shortcut: Cmd+K / Ctrl+K
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        toggle();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [toggle]);

  return {
    isOpen,
    open,
    close,
    toggle,
    query,
    setQuery,
    debouncedQuery,
    results: searchEnabled ? results : undefined,
    isLoading: searchEnabled && isLoading,
    isError,
    selectedIndex,
    setSelectedIndex,
  };
}
