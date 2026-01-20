/**
 * DLP React Query Hooks
 *
 * TanStack Query Hooks fuer DLP-Policies und Scanning.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  dlpApi,
  PolicyCreateRequest,
  PolicyUpdateRequest,
  AccessCheckRequest,
  ScanRequest,
} from '../api/dlp-api';

// ==================== Query Keys ====================

export const dlpKeys = {
  all: ['dlp'] as const,
  policies: () => [...dlpKeys.all, 'policies'] as const,
  policy: (id: string) => [...dlpKeys.policies(), id] as const,
  sensitiveDataTypes: () => [...dlpKeys.all, 'sensitive-data-types'] as const,
};

// ==================== Queries ====================

/**
 * Alle DLP-Policies laden
 */
export function useDLPPolicies() {
  return useQuery({
    queryKey: dlpKeys.policies(),
    queryFn: dlpApi.listPolicies,
  });
}

/**
 * Einzelne Policy laden
 */
export function useDLPPolicy(policyId: string) {
  return useQuery({
    queryKey: dlpKeys.policy(policyId),
    queryFn: () => dlpApi.getPolicy(policyId),
    enabled: !!policyId,
  });
}

/**
 * Verfuegbare Typen sensibler Daten
 */
export function useSensitiveDataTypes() {
  return useQuery({
    queryKey: dlpKeys.sensitiveDataTypes(),
    queryFn: dlpApi.getSensitiveDataTypes,
    staleTime: 24 * 60 * 60 * 1000, // 24 Stunden
  });
}

// ==================== Mutations ====================

/**
 * Neue Policy erstellen
 */
export function useCreatePolicy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PolicyCreateRequest) => dlpApi.createPolicy(data),
    onSuccess: (policy) => {
      queryClient.invalidateQueries({ queryKey: dlpKeys.policies() });
      toast.success(`Policy "${policy.name}" wurde erstellt`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Policy aktualisieren
 */
export function useUpdatePolicy(policyId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PolicyUpdateRequest) => dlpApi.updatePolicy(policyId, data),
    onSuccess: (policy) => {
      queryClient.invalidateQueries({ queryKey: dlpKeys.policies() });
      queryClient.invalidateQueries({ queryKey: dlpKeys.policy(policyId) });
      toast.success(`Policy "${policy.name}" wurde aktualisiert`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Policy loeschen
 */
export function useDeletePolicy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (policyId: string) => dlpApi.deletePolicy(policyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dlpKeys.policies() });
      toast.success('Policy wurde geloescht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Loeschen: ${error.message}`);
    },
  });
}

/**
 * Zugriffspruefung durchfuehren
 */
export function useCheckAccess() {
  return useMutation({
    mutationFn: (data: AccessCheckRequest) => dlpApi.checkAccess(data),
  });
}

/**
 * Sensible Daten scannen
 */
export function useScanSensitiveData() {
  return useMutation({
    mutationFn: (data: ScanRequest) => dlpApi.scanSensitiveData(data),
  });
}

/**
 * Policy aktivieren/deaktivieren
 */
export function useTogglePolicyEnabled(policyId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (enabled: boolean) => dlpApi.updatePolicy(policyId, { enabled }),
    onSuccess: (policy) => {
      queryClient.invalidateQueries({ queryKey: dlpKeys.policies() });
      queryClient.invalidateQueries({ queryKey: dlpKeys.policy(policyId) });
      toast.success(
        policy.enabled
          ? `Policy "${policy.name}" wurde aktiviert`
          : `Policy "${policy.name}" wurde deaktiviert`
      );
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}
