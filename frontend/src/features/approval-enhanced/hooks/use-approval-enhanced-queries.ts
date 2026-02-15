/**
 * React Query hooks for Approval Enhanced
 */

import { useQuery, useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getConditionalRules,
  createConditionalRule,
  updateConditionalRule,
  deleteConditionalRule,
  getEscalationRules,
  createEscalationRule,
  deleteEscalationRule,
  getSubstitutionRules,
  createSubstitutionRule,
  deleteSubstitutionRule,
  getSLAMetrics,
  getSLAReport,
  triggerAutoFile,
  getAutoFileStats,
  triggerAutoMatch,
  getAutoMatchResults,
} from '../api/approval-enhanced-api';
import {
  ConditionalRule,
  EscalationRule,
  SubstitutionRule,
  SLAMetrics,
  SLAReport,
  AutoFileStats,
  AutoMatchResult,
  transformConditionalRule,
  transformEscalationRule,
  transformSubstitutionRule,
  transformSLAMetrics,
  transformSLAReport,
  transformAutoFileStats,
  transformAutoMatchResult,
  CreateConditionalRuleDTO,
  UpdateConditionalRuleDTO,
  CreateEscalationRuleDTO,
  CreateSubstitutionRuleDTO,
} from '../types/approval-enhanced-types';

// ==================== Query Keys ====================

export const approvalKeys = {
  all: ['approval-enhanced'] as const,
  conditionalRules: () => [...approvalKeys.all, 'conditional-rules'] as const,
  escalationRules: () => [...approvalKeys.all, 'escalation-rules'] as const,
  substitutionRules: () => [...approvalKeys.all, 'substitution-rules'] as const,
  slaMetrics: () => [...approvalKeys.all, 'sla-metrics'] as const,
  slaReport: (startDate?: string, endDate?: string) =>
    [...approvalKeys.all, 'sla-report', { startDate, endDate }] as const,
  autoFileStats: () => [...approvalKeys.all, 'auto-file-stats'] as const,
  autoMatchResults: (documentId: number) =>
    [...approvalKeys.all, 'auto-match-results', documentId] as const,
};

// ==================== Conditional Rules Queries ====================

export function useConditionalRules(): UseQueryResult<ConditionalRule[]> {
  return useQuery({
    queryKey: approvalKeys.conditionalRules(),
    queryFn: async () => {
      const data = await getConditionalRules();
      return data.map(transformConditionalRule);
    },
  });
}

export function useCreateConditionalRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateConditionalRuleDTO) => createConditionalRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.conditionalRules() });
      toast.success('Bedingte Regel erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Erstellen der bedingten Regel');
    },
  });
}

export function useUpdateConditionalRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ruleId, data }: { ruleId: number; data: UpdateConditionalRuleDTO }) =>
      updateConditionalRule(ruleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.conditionalRules() });
      toast.success('Bedingte Regel erfolgreich aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Aktualisieren der bedingten Regel');
    },
  });
}

export function useDeleteConditionalRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: number) => deleteConditionalRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.conditionalRules() });
      toast.success('Bedingte Regel erfolgreich gelöscht');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Löschen der bedingten Regel');
    },
  });
}

// ==================== Escalation Rules Queries ====================

export function useEscalationRules(): UseQueryResult<EscalationRule[]> {
  return useQuery({
    queryKey: approvalKeys.escalationRules(),
    queryFn: async () => {
      const data = await getEscalationRules();
      return data.map(transformEscalationRule);
    },
  });
}

export function useCreateEscalationRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateEscalationRuleDTO) => createEscalationRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.escalationRules() });
      toast.success('Eskalationsregel erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Erstellen der Eskalationsregel');
    },
  });
}

export function useDeleteEscalationRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: number) => deleteEscalationRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.escalationRules() });
      toast.success('Eskalationsregel erfolgreich gelöscht');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Löschen der Eskalationsregel');
    },
  });
}

// ==================== Substitution Rules Queries ====================

export function useSubstitutionRules(): UseQueryResult<SubstitutionRule[]> {
  return useQuery({
    queryKey: approvalKeys.substitutionRules(),
    queryFn: async () => {
      const data = await getSubstitutionRules();
      return data.map(transformSubstitutionRule);
    },
  });
}

export function useCreateSubstitutionRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateSubstitutionRuleDTO) => createSubstitutionRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.substitutionRules() });
      toast.success('Stellvertretung erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Erstellen der Stellvertretung');
    },
  });
}

export function useDeleteSubstitutionRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: number) => deleteSubstitutionRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.substitutionRules() });
      toast.success('Stellvertretung erfolgreich gelöscht');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Löschen der Stellvertretung');
    },
  });
}

// ==================== SLA Queries ====================

export function useSLAMetrics(): UseQueryResult<SLAMetrics> {
  return useQuery({
    queryKey: approvalKeys.slaMetrics(),
    queryFn: async () => {
      const data = await getSLAMetrics();
      return transformSLAMetrics(data);
    },
    refetchInterval: 60000, // Refresh every minute
  });
}

export function useSLAReport(
  startDate?: string,
  endDate?: string
): UseQueryResult<SLAReport> {
  return useQuery({
    queryKey: approvalKeys.slaReport(startDate, endDate),
    queryFn: async () => {
      const data = await getSLAReport(startDate, endDate);
      return transformSLAReport(data);
    },
    enabled: Boolean(startDate && endDate),
  });
}

// ==================== Auto-Filing Queries ====================

export function useAutoFileStats(): UseQueryResult<AutoFileStats> {
  return useQuery({
    queryKey: approvalKeys.autoFileStats(),
    queryFn: async () => {
      const data = await getAutoFileStats();
      return transformAutoFileStats(data);
    },
  });
}

export function useTriggerAutoFile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => triggerAutoFile(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.autoFileStats() });
      toast.success('Automatische Ablage wurde erfolgreich ausgelöst');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Auslösen der automatischen Ablage');
    },
  });
}

// ==================== Auto-Matching Queries ====================

export function useAutoMatchResults(
  documentId: number,
  enabled = false
): UseQueryResult<AutoMatchResult> {
  return useQuery({
    queryKey: approvalKeys.autoMatchResults(documentId),
    queryFn: async () => {
      const data = await getAutoMatchResults(documentId);
      return transformAutoMatchResult(data);
    },
    enabled: enabled && documentId > 0,
  });
}

export function useTriggerAutoMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (documentId: number) => triggerAutoMatch(documentId),
    onSuccess: (_, documentId) => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.autoMatchResults(documentId) });
      toast.success('Automatische Zuordnung wurde erfolgreich ausgelöst');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Fehler beim Auslösen der automatischen Zuordnung');
    },
  });
}
