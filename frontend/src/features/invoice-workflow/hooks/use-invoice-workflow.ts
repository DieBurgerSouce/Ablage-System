/**
 * Invoice Workflow Hooks - TanStack Query Integration
 *
 * React Hooks für den vollautomatischen Rechnungsworkflow
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPipelineStatus,
  getApprovalQueue,
  getAutomationStats,
  approveInvoice,
  rejectInvoice,
  invoiceWorkflowKeys,
} from '../api/invoice-workflow-api';
import { toast } from 'sonner';

/**
 * Hook für den Pipeline-Status
 */
export function usePipelineStatus() {
  return useQuery({
    queryKey: invoiceWorkflowKeys.pipeline(),
    queryFn: getPipelineStatus,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  });
}

/**
 * Hook für die Freigabe-Warteschlange
 */
export function useApprovalQueue() {
  return useQuery({
    queryKey: invoiceWorkflowKeys.queue(),
    queryFn: getApprovalQueue,
    staleTime: 15000,
    refetchInterval: 30000,
    retry: 2,
  });
}

/**
 * Hook für Automatisierungsstatistiken
 */
export function useAutomationStats() {
  return useQuery({
    queryKey: invoiceWorkflowKeys.stats(),
    queryFn: getAutomationStats,
    staleTime: 60000,
    refetchInterval: 120000,
    retry: 2,
  });
}

/**
 * Mutation zum Genehmigen einer Rechnung
 */
export function useApproveInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => approveInvoice(id),
    onSuccess: (data) => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.queue() });
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.pipeline() });
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.stats() });

      toast.success('Rechnung genehmigt', {
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast.error('Genehmigung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}

/**
 * Mutation zum Ablehnen einer Rechnung
 */
export function useRejectInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => rejectInvoice(id),
    onSuccess: (data) => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.queue() });
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.pipeline() });
      queryClient.invalidateQueries({ queryKey: invoiceWorkflowKeys.stats() });

      toast.success('Rechnung abgelehnt', {
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast.error('Ablehnung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}
