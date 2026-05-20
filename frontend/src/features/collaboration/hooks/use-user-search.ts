/**
 * useUserSearch - Debounced Benutzersuche mit TanStack Query
 *
 * Verwendet die User Search API mit 300ms Debounce.
 * Suche wird erst ab 2 Zeichen ausgeloest.
 */

import { useQuery } from '@tanstack/react-query';
import { useDebounce } from '@/hooks/use-debounce';
import { searchUsers } from '../api/user-search-api';
import type { UserSuggestion } from '../types/collaboration.types';

export function useUserSearch(query: string) {
  const debouncedQuery = useDebounce(query, 300);

  const result = useQuery<UserSuggestion[]>({
    queryKey: ['user-search', debouncedQuery],
    queryFn: () => searchUsers(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30000,
    placeholderData: [],
  });

  return {
    users: result.data ?? [],
    isLoading: result.isLoading && debouncedQuery.length >= 2,
  };
}
