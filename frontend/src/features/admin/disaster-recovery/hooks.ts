/**
 * Disaster Recovery Hooks
 *
 * TanStack Query hooks für Disaster Recovery.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getBackupStatus, listBackups, validateBackup, validateAllBackups, createFullBackup, runRestoreTest, getRestoreTestHistory, getRTOMetrics, generateRecoveryPlaybook } from './api';

// ==================== Query Keys ====================

export const disasterRecoveryKeys = {
  all: ['disaster-recovery'] as const,
  status: () => [...disasterRecoveryKeys.all, 'status'] as const,
  backups: () => [...disasterRecoveryKeys.all, 'backups'] as const,
  testHistory: (days: number) =>
    [...disasterRecoveryKeys.all, 'test-history', days] as const,
  rtoMetrics: () => [...disasterRecoveryKeys.all, 'rto-metrics'] as const,
};

// ==================== Queries ====================

/**
 * Hole Backup-Status
 */
export function useBackupStatus() {
  return useQuery({
    queryKey: disasterRecoveryKeys.status(),
    queryFn: getBackupStatus,
    refetchInterval: 30000, // Alle 30 Sekunden
  });
}

/**
 * Hole Backup-Liste
 */
export function useBackups() {
  return useQuery({
    queryKey: disasterRecoveryKeys.backups(),
    queryFn: listBackups,
    refetchInterval: 60000, // Jede Minute
  });
}

/**
 * Hole Restore-Test History
 */
export function useRestoreTestHistory(days = 90) {
  return useQuery({
    queryKey: disasterRecoveryKeys.testHistory(days),
    queryFn: () => getRestoreTestHistory(days),
    refetchInterval: 60000,
  });
}

/**
 * Hole RTO/RPO Metriken
 */
export function useRTOMetrics() {
  return useQuery({
    queryKey: disasterRecoveryKeys.rtoMetrics(),
    queryFn: getRTOMetrics,
    refetchInterval: 300000, // Alle 5 Minuten
  });
}

// ==================== Mutations ====================

/**
 * Validiere einzelnes Backup
 */
export function useValidateBackup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: validateBackup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.backups() });
    },
  });
}

/**
 * Validiere alle Backups
 */
export function useValidateAllBackups() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: validateAllBackups,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.backups() });
    },
  });
}

/**
 * Erstelle vollständiges Backup
 */
export function useCreateFullBackup() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createFullBackup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.backups() });
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.status() });
    },
  });
}

/**
 * Führe Restore-Test durch
 */
export function useRunRestoreTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: runRestoreTest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.testHistory(90) });
      queryClient.invalidateQueries({ queryKey: disasterRecoveryKeys.rtoMetrics() });
    },
  });
}

/**
 * Generiere Recovery-Playbook
 */
export function useGeneratePlaybook() {
  return useMutation({
    mutationFn: generateRecoveryPlaybook,
  });
}
