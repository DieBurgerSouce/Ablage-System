/**
 * Delegation Management Hooks
 *
 * TanStack Query hooks for delegation operations
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getDelegations,
  getDelegation,
  createDelegation,
  updateDelegation,
  acceptDelegation,
  declineDelegation,
  revokeDelegation,
  extendDelegation,
  getDelegationTemplates,
  getDelegationAuditLog,
  searchDelegateUsers,
} from './api';
import type {
  DelegationFilters,
  DelegationCreateRequest,
  DelegationUpdateRequest,
} from './types';

// Query key factory
export const delegationKeys = {
  all: ['delegations'] as const,
  lists: () => [...delegationKeys.all, 'list'] as const,
  list: (filters?: DelegationFilters) => [...delegationKeys.lists(), filters] as const,
  details: () => [...delegationKeys.all, 'detail'] as const,
  detail: (id: string) => [...delegationKeys.details(), id] as const,
  templates: () => [...delegationKeys.all, 'templates'] as const,
  auditLog: (id: string) => [...delegationKeys.all, 'audit', id] as const,
  userSearch: (query: string) => [...delegationKeys.all, 'users', query] as const,
};

/**
 * Hook to fetch delegations list
 */
export function useDelegations(
  filters?: DelegationFilters,
  page: number = 1,
  pageSize: number = 20
) {
  return useQuery({
    queryKey: delegationKeys.list(filters),
    queryFn: () => getDelegations(filters, page, pageSize),
  });
}

/**
 * Hook to fetch a single delegation
 */
export function useDelegation(delegationId: string) {
  return useQuery({
    queryKey: delegationKeys.detail(delegationId),
    queryFn: () => getDelegation(delegationId),
    enabled: !!delegationId,
  });
}

/**
 * Hook to fetch delegation templates
 */
export function useDelegationTemplates() {
  return useQuery({
    queryKey: delegationKeys.templates(),
    queryFn: getDelegationTemplates,
  });
}

/**
 * Hook to fetch delegation audit log
 */
export function useDelegationAuditLog(delegationId: string, limit: number = 50) {
  return useQuery({
    queryKey: delegationKeys.auditLog(delegationId),
    queryFn: () => getDelegationAuditLog(delegationId, limit),
    enabled: !!delegationId,
  });
}

/**
 * Hook to search for users to delegate to
 */
export function useUserSearch(query: string, enabled: boolean = true) {
  return useQuery({
    queryKey: delegationKeys.userSearch(query),
    queryFn: () => searchDelegateUsers(query),
    enabled: enabled && query.length >= 2,
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to create a new delegation
 */
export function useCreateDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: DelegationCreateRequest) => createDelegation(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      toast.success(data.nachricht || 'Vertretung erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen der Vertretung: ${error.message}`);
    },
  });
}

/**
 * Hook to update a delegation
 */
export function useUpdateDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      delegationId,
      request,
    }: {
      delegationId: string;
      request: DelegationUpdateRequest;
    }) => updateDelegation(delegationId, request),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: delegationKeys.detail(variables.delegationId),
      });
      toast.success(data.nachricht || 'Vertretung aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook to accept a delegation
 */
export function useAcceptDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (delegationId: string) => acceptDelegation(delegationId),
    onSuccess: (data, delegationId) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: delegationKeys.detail(delegationId),
      });
      toast.success(data.nachricht || 'Vertretung angenommen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Annehmen: ${error.message}`);
    },
  });
}

/**
 * Hook to decline a delegation
 */
export function useDeclineDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      delegationId,
      reason,
    }: {
      delegationId: string;
      reason?: string;
    }) => declineDelegation(delegationId, reason),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: delegationKeys.detail(variables.delegationId),
      });
      toast.success(data.nachricht || 'Vertretung abgelehnt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Ablehnen: ${error.message}`);
    },
  });
}

/**
 * Hook to revoke a delegation
 */
export function useRevokeDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      delegationId,
      reason,
    }: {
      delegationId: string;
      reason?: string;
    }) => revokeDelegation(delegationId, reason),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: delegationKeys.detail(variables.delegationId),
      });
      toast.success(data.nachricht || 'Vertretung widerrufen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Widerrufen: ${error.message}`);
    },
  });
}

/**
 * Hook to extend a delegation
 */
export function useExtendDelegation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      delegationId,
      newEndDate,
    }: {
      delegationId: string;
      newEndDate: string;
    }) => extendDelegation(delegationId, newEndDate),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: delegationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: delegationKeys.detail(variables.delegationId),
      });
      toast.success(data.nachricht || 'Vertretung verlängert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Verlängern: ${error.message}`);
    },
  });
}
