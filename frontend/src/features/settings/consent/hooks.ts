/**
 * Consent Management Hooks
 *
 * TanStack Query Hooks für Einwilligungsverwaltung
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/hooks/use-toast';
import {
  getConsentStatus,
  grantConsent,
  withdrawConsent,
  getConsentHistory,
} from './api';
import type { ConsentScope, ConsentGrantRequest } from './types';

// Query Keys
export const consentKeys = {
  all: ['consent'] as const,
  status: () => [...consentKeys.all, 'status'] as const,
  history: (scope?: ConsentScope) => [...consentKeys.all, 'history', scope] as const,
};

/**
 * Hook für Einwilligungs-Status
 */
export function useConsentStatus() {
  return useQuery({
    queryKey: consentKeys.status(),
    queryFn: getConsentStatus,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook für Einwilligungs-Historie
 */
export function useConsentHistory(scope?: ConsentScope, limit: number = 50) {
  return useQuery({
    queryKey: consentKeys.history(scope),
    queryFn: () => getConsentHistory(scope, limit),
    staleTime: 2 * 60 * 1000, // 2 Minuten
  });
}

/**
 * Hook zum Erteilen/Aktualisieren einer Einwilligung
 */
export function useGrantConsent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ConsentGrantRequest) => grantConsent(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.all });
      toast({
        title: 'Einwilligung aktualisiert',
        description: data.nachricht,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Einwilligung konnte nicht aktualisiert werden.',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Widerrufen einer Einwilligung
 */
export function useWithdrawConsent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ scope, reason }: { scope: ConsentScope; reason?: string }) =>
      withdrawConsent(scope, reason),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: consentKeys.all });
      toast({
        title: 'Einwilligung widerrufen',
        description: data.nachricht,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler',
        description: error.message || 'Einwilligung konnte nicht widerrufen werden.',
        variant: 'destructive',
      });
    },
  });
}
