/**
 * User Search API Client - Benutzersuche fuer @mention Vorschlaege
 *
 * Backend-Endpunkt:
 * - GET /users?search=&limit=&is_active=true
 */

import { apiClient } from '@/lib/api/client';
import type { UserSuggestion } from '../types/collaboration.types';

/**
 * Sucht aktive Benutzer anhand eines Suchbegriffs.
 *
 * @param query - Suchbegriff (Name oder E-Mail)
 * @param limit - Maximale Anzahl Ergebnisse (Standard: 10)
 * @returns Liste passender Benutzer
 */
export async function searchUsers(query: string, limit: number = 10): Promise<UserSuggestion[]> {
  const response = await apiClient.get<UserSuggestion[]>('/users', {
    params: { search: query, limit, is_active: true },
  });
  return response.data;
}
