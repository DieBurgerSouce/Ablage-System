/**
 * Workflow Versioning Hooks
 *
 * React Query Hooks fuer Workflow-Versionierung.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import * as versionsApi from '@/lib/api/services/workflow-versions';
import type {
  VersionListParams,
  CreateVersionRequest,
  RollbackRequest,
  CreateABTestRequest,
} from '../types/version-types';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const versionKeys = {
  all: ['workflow-versions'] as const,
  lists: () => [...versionKeys.all, 'list'] as const,
  list: (workflowId: string, params?: VersionListParams) =>
    [...versionKeys.lists(), workflowId, params] as const,
  details: () => [...versionKeys.all, 'detail'] as const,
  detail: (workflowId: string, versionId: string) =>
    [...versionKeys.details(), workflowId, versionId] as const,
  active: (workflowId: string) =>
    [...versionKeys.all, 'active', workflowId] as const,
  diff: (workflowId: string, versionId: string, compareToId?: string) =>
    [...versionKeys.all, 'diff', workflowId, versionId, compareToId] as const,
  compare: (workflowId: string, versionIds?: string[]) =>
    [...versionKeys.all, 'compare', workflowId, versionIds] as const,
  abTests: (workflowId: string) =>
    [...versionKeys.all, 'ab-tests', workflowId] as const,
  abTest: (workflowId: string, testId: string) =>
    [...versionKeys.abTests(workflowId), testId] as const,
};

// =============================================================================
// VERSION QUERIES
// =============================================================================

/**
 * Hook fuer Version-Liste.
 */
export function useWorkflowVersions(
  workflowId: string,
  params: VersionListParams = {},
  enabled = true
) {
  return useQuery({
    queryKey: versionKeys.list(workflowId, params),
    queryFn: () => versionsApi.listVersions(workflowId, params),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook fuer einzelne Version.
 */
export function useWorkflowVersion(
  workflowId: string,
  versionId: string,
  enabled = true
) {
  return useQuery({
    queryKey: versionKeys.detail(workflowId, versionId),
    queryFn: () => versionsApi.getVersion(workflowId, versionId),
    enabled: enabled && !!workflowId && !!versionId,
  });
}

/**
 * Hook fuer aktive Version.
 */
export function useActiveVersion(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: versionKeys.active(workflowId),
    queryFn: () => versionsApi.getActiveVersion(workflowId),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook fuer Version-Diff.
 */
export function useVersionDiff(
  workflowId: string,
  versionId: string,
  compareToId?: string,
  enabled = true
) {
  return useQuery({
    queryKey: versionKeys.diff(workflowId, versionId, compareToId),
    queryFn: () => versionsApi.getVersionDiff(workflowId, versionId, compareToId),
    enabled: enabled && !!workflowId && !!versionId,
  });
}

/**
 * Hook fuer Versions-Vergleich.
 */
export function useVersionComparison(
  workflowId: string,
  versionIds?: string[],
  enabled = true
) {
  return useQuery({
    queryKey: versionKeys.compare(workflowId, versionIds),
    queryFn: () => versionsApi.compareVersions(workflowId, versionIds),
    enabled: enabled && !!workflowId,
  });
}

// =============================================================================
// VERSION MUTATIONS
// =============================================================================

/**
 * Hook fuer Version-Erstellung.
 */
export function useCreateVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: CreateVersionRequest;
    }) => versionsApi.createVersion(workflowId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.list(workflowId) });
      queryClient.invalidateQueries({ queryKey: versionKeys.active(workflowId) });
      toast.success('Version erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook fuer Version-Veroeffentlichung.
 */
export function usePublishVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      versionId,
    }: {
      workflowId: string;
      versionId: string;
    }) => versionsApi.publishVersion(workflowId, versionId),
    onSuccess: (_, { workflowId, versionId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.list(workflowId) });
      queryClient.invalidateQueries({ queryKey: versionKeys.active(workflowId) });
      queryClient.invalidateQueries({
        queryKey: versionKeys.detail(workflowId, versionId),
      });
      toast.success('Version erfolgreich veroeffentlicht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Veroeffentlichen: ${error.message}`);
    },
  });
}

/**
 * Hook fuer Version-Deprecation.
 */
export function useDeprecateVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      versionId,
    }: {
      workflowId: string;
      versionId: string;
    }) => versionsApi.deprecateVersion(workflowId, versionId),
    onSuccess: (_, { workflowId, versionId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.list(workflowId) });
      queryClient.invalidateQueries({
        queryKey: versionKeys.detail(workflowId, versionId),
      });
      toast.success('Version als veraltet markiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Markieren: ${error.message}`);
    },
  });
}

/**
 * Hook fuer Version-Archivierung.
 */
export function useArchiveVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      versionId,
    }: {
      workflowId: string;
      versionId: string;
    }) => versionsApi.archiveVersion(workflowId, versionId),
    onSuccess: (_, { workflowId, versionId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.list(workflowId) });
      queryClient.invalidateQueries({
        queryKey: versionKeys.detail(workflowId, versionId),
      });
      toast.success('Version archiviert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Archivieren: ${error.message}`);
    },
  });
}

/**
 * Hook fuer Rollback.
 */
export function useRollback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: RollbackRequest;
    }) => versionsApi.rollbackToVersion(workflowId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.list(workflowId) });
      queryClient.invalidateQueries({ queryKey: versionKeys.active(workflowId) });
      toast.success('Rollback erfolgreich durchgefuehrt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Rollback: ${error.message}`);
    },
  });
}

// =============================================================================
// A/B TEST QUERIES & MUTATIONS
// =============================================================================

/**
 * Hook fuer A/B Test Liste.
 */
export function useABTests(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: versionKeys.abTests(workflowId),
    queryFn: () => versionsApi.listABTests(workflowId),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook fuer einzelnen A/B Test.
 */
export function useABTest(workflowId: string, testId: string, enabled = true) {
  return useQuery({
    queryKey: versionKeys.abTest(workflowId, testId),
    queryFn: () => versionsApi.getABTest(workflowId, testId),
    enabled: enabled && !!workflowId && !!testId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 10000 : false,
  });
}

/**
 * Hook fuer A/B Test Erstellung.
 */
export function useCreateABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: CreateABTestRequest;
    }) => versionsApi.createABTest(workflowId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.abTests(workflowId) });
      toast.success('A/B Test erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook fuer A/B Test Start.
 */
export function useStartABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      testId,
    }: {
      workflowId: string;
      testId: string;
    }) => versionsApi.startABTest(workflowId, testId),
    onSuccess: (_, { workflowId, testId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.abTests(workflowId) });
      queryClient.invalidateQueries({
        queryKey: versionKeys.abTest(workflowId, testId),
      });
      toast.success('A/B Test gestartet');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Starten: ${error.message}`);
    },
  });
}

/**
 * Hook fuer A/B Test Stop.
 */
export function useStopABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      testId,
      winner,
    }: {
      workflowId: string;
      testId: string;
      winner?: 'control' | 'treatment' | 'inconclusive';
    }) => versionsApi.stopABTest(workflowId, testId, winner),
    onSuccess: (_, { workflowId, testId }) => {
      queryClient.invalidateQueries({ queryKey: versionKeys.abTests(workflowId) });
      queryClient.invalidateQueries({
        queryKey: versionKeys.abTest(workflowId, testId),
      });
      toast.success('A/B Test beendet');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Beenden: ${error.message}`);
    },
  });
}
