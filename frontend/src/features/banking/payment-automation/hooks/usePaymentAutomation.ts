/**
 * Payment Automation Hooks
 *
 * Hooks für automatisierte Zahlungsvorschläge und -batches.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// Types
// =============================================================================

export type PaymentPriority = 'critical' | 'high' | 'normal' | 'low';
export type PaymentStrategy = 'skonto_optimized' | 'cashflow_optimized' | 'deadline_based' | 'immediate';
export type PaymentBatchStatus = 'draft' | 'pending_approval' | 'approved' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type SuggestionReason = 'skonto_expiring' | 'due_date_near' | 'overdue' | 'approved_invoice' | 'recurring_payment' | 'manual_request';

export interface PaymentSuggestion {
  id: string;
  invoice_id: string;
  invoice_number: string;
  entity_id: string | null;
  entity_name: string;
  entity_iban: string | null;
  entity_bic: string | null;
  original_amount: number;
  skonto_amount: number;
  payment_amount: number;
  invoice_date: string | null;
  due_date: string | null;
  skonto_deadline: string | null;
  suggested_payment_date: string | null;
  priority: PaymentPriority;
  reason: SuggestionReason;
  days_until_due: number | null;
  days_until_skonto: number | null;
  skonto_percentage: number | null;
  skonto_savings: number;
  use_skonto: boolean;
  document_id: string | null;
  reference: string;
  notes: string;
  confidence: number;
}

export interface PaymentBatch {
  id: string;
  company_id: string | null;
  name: string;
  description: string;
  suggestions: PaymentSuggestion[];
  total_amount: number;
  total_skonto_savings: number;
  payment_count: number;
  status: PaymentBatchStatus;
  created_at: string;
  created_by_id: string | null;
  approved_at: string | null;
  approved_by_id: string | null;
  rejected_at: string | null;
  rejected_by_id: string | null;
  rejection_reason: string | null;
  executed_at: string | null;
  sepa_file_id: string | null;
  sepa_file_path: string | null;
  sepa_message_id: string | null;
  debtor_account_id: string | null;
  debtor_iban: string;
  debtor_bic: string;
  debtor_name: string;
}

export interface PaymentScheduleEntry {
  date: string;
  payment_count: number;
  total_amount: number;
  skonto_savings: number;
  payments: Array<{
    invoice_number: string;
    entity_name: string;
    amount: number;
    priority: string;
  }>;
}

export interface PaymentSchedule {
  company_id: string;
  period_start: string;
  period_end: string;
  entries: PaymentScheduleEntry[];
  total_amount: number;
  total_skonto_savings: number;
}

export interface AutomationConfig {
  auto_generate_on_approval: boolean;
  auto_approve_threshold: number;
  auto_execute: boolean;
  prioritize_skonto: boolean;
  skonto_alert_days: number;
  skonto_min_savings: number;
  preferred_payment_days: number[];
  advance_days: number;
  batch_window_days: number;
  max_batch_size: number;
  max_single_payment: number;
  daily_limit: number;
}

export interface AutomationStatistics {
  period_days: number;
  period_start: string;
  period_end: string;
  invoices_paid: number;
  total_paid: number;
  skonto_used_count: number;
  skonto_missed_count: number;
  skonto_savings: number;
  missed_savings: number;
  skonto_usage_rate: number;
  open_invoices: number;
  overdue_invoices: number;
  currency: string;
}

export interface SkontoAlert {
  invoice_id: string;
  invoice_number: string;
  entity_id: string | null;
  amount: number;
  skonto_percentage: number;
  skonto_deadline: string | null;
  days_remaining: number;
  potential_savings: number;
  urgency: 'critical' | 'warning' | 'info';
  message: string;
}

// =============================================================================
// Query Keys
// =============================================================================

export const paymentAutomationKeys = {
  all: ['payment-automation'] as const,
  suggestions: (strategy?: PaymentStrategy) => [...paymentAutomationKeys.all, 'suggestions', strategy] as const,
  batches: (status?: PaymentBatchStatus) => [...paymentAutomationKeys.all, 'batches', status] as const,
  batch: (id: string) => [...paymentAutomationKeys.all, 'batch', id] as const,
  schedule: (days?: number) => [...paymentAutomationKeys.all, 'schedule', days] as const,
  statistics: (days?: number) => [...paymentAutomationKeys.all, 'statistics', days] as const,
  config: () => [...paymentAutomationKeys.all, 'config'] as const,
  alerts: (days?: number) => [...paymentAutomationKeys.all, 'alerts', days] as const,
};

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook zum Abrufen von Zahlungsvorschlägen
 */
export function usePaymentSuggestions(
  strategy: PaymentStrategy = 'skonto_optimized',
  lookaheadDays: number = 30,
  includeOverdue: boolean = true
) {
  return useQuery({
    queryKey: paymentAutomationKeys.suggestions(strategy),
    queryFn: async () => {
      const params = new URLSearchParams({
        strategy,
        lookahead_days: String(lookaheadDays),
        include_overdue: String(includeOverdue),
      });
      const response = await api.get<PaymentSuggestion[]>(
        `/api/v1/banking/payment-automation/suggestions?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 60_000, // 1 Minute
    refetchInterval: 300_000, // 5 Minuten
  });
}

/**
 * Hook zum Abrufen von Payment-Batches
 */
export function usePaymentBatches(status?: PaymentBatchStatus, limit = 50) {
  return useQuery({
    queryKey: paymentAutomationKeys.batches(status),
    queryFn: async () => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status) params.set('status', status);
      const response = await api.get<PaymentBatch[]>(
        `/api/v1/banking/payment-automation/batches?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 30_000,
  });
}

/**
 * Hook zum Abrufen eines einzelnen Batches
 */
export function usePaymentBatch(batchId: string) {
  return useQuery({
    queryKey: paymentAutomationKeys.batch(batchId),
    queryFn: async () => {
      const response = await api.get<PaymentBatch>(
        `/api/v1/banking/payment-automation/batches/${batchId}`
      );
      return response.data;
    },
    enabled: !!batchId,
  });
}

/**
 * Hook zum Abrufen des Zahlungskalenders
 */
export function usePaymentSchedule(periodDays: number = 30, strategy: PaymentStrategy = 'skonto_optimized') {
  return useQuery({
    queryKey: paymentAutomationKeys.schedule(periodDays),
    queryFn: async () => {
      const params = new URLSearchParams({
        period_days: String(periodDays),
        strategy,
      });
      const response = await api.get<PaymentSchedule>(
        `/api/v1/banking/payment-automation/schedule?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Abrufen von Statistiken
 */
export function useAutomationStatistics(days: number = 30) {
  return useQuery({
    queryKey: paymentAutomationKeys.statistics(days),
    queryFn: async () => {
      const response = await api.get<AutomationStatistics>(
        `/api/v1/banking/payment-automation/statistics?days=${days}`
      );
      return response.data;
    },
    staleTime: 300_000, // 5 Minuten
  });
}

/**
 * Hook zum Abrufen der Konfiguration
 */
export function useAutomationConfig() {
  return useQuery({
    queryKey: paymentAutomationKeys.config(),
    queryFn: async () => {
      const response = await api.get<AutomationConfig>(
        '/api/v1/banking/payment-automation/config'
      );
      return response.data;
    },
    staleTime: 600_000, // 10 Minuten
  });
}

/**
 * Hook zum Abrufen von Skonto-Alerts
 */
export function useSkontoAlerts(days: number = 7) {
  return useQuery({
    queryKey: paymentAutomationKeys.alerts(days),
    queryFn: async () => {
      const response = await api.get<SkontoAlert[]>(
        `/api/v1/banking/payment-automation/skonto-alerts?days=${days}`
      );
      return response.data;
    },
    staleTime: 60_000,
    refetchInterval: 300_000,
  });
}

/**
 * Hook zum Erstellen eines Batches aus Vorschlägen
 */
export function useCreateBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      invoiceIds,
      name,
      debtorAccountId,
    }: {
      invoiceIds: string[];
      name?: string;
      debtorAccountId?: string;
    }) => {
      const response = await api.post<PaymentBatch>(
        '/api/v1/banking/payment-automation/batches',
        {
          invoice_ids: invoiceIds,
          name,
          debtor_account_id: debtorAccountId,
        }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batches() });
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.suggestions() });
    },
  });
}

/**
 * Hook zum Erstellen eines optimierten Batches
 */
export function useCreateOptimizedBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      strategy,
      maxAmount,
      debtorAccountId,
    }: {
      strategy?: PaymentStrategy;
      maxAmount?: number;
      debtorAccountId?: string;
    }) => {
      const response = await api.post<PaymentBatch>(
        '/api/v1/banking/payment-automation/batches/optimized',
        {
          strategy,
          max_amount: maxAmount,
          debtor_account_id: debtorAccountId,
        }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batches() });
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.suggestions() });
    },
  });
}

/**
 * Hook zum Freigeben eines Batches
 */
export function useApproveBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (batchId: string) => {
      const response = await api.post<PaymentBatch>(
        `/api/v1/banking/payment-automation/batches/${batchId}/approve`
      );
      return response.data;
    },
    onSuccess: (_, batchId) => {
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batches() });
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batch(batchId) });
    },
  });
}

/**
 * Hook zum Ablehnen eines Batches
 */
export function useRejectBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ batchId, reason }: { batchId: string; reason: string }) => {
      const response = await api.post<PaymentBatch>(
        `/api/v1/banking/payment-automation/batches/${batchId}/reject`,
        { reason }
      );
      return response.data;
    },
    onSuccess: (_, { batchId }) => {
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batches() });
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.batch(batchId) });
    },
  });
}

/**
 * Hook zum Generieren einer SEPA-Datei
 */
export function useGenerateSepaFile() {
  return useMutation({
    mutationFn: async ({
      batchId,
      executionDate,
    }: {
      batchId: string;
      executionDate?: string;
    }) => {
      const params = new URLSearchParams();
      if (executionDate) params.set('execution_date', executionDate);
      const response = await api.post<{ xml_content: string; message_id: string; file_name: string }>(
        `/api/v1/banking/payment-automation/batches/${batchId}/sepa?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Hook zum Aktualisieren der Konfiguration
 */
export function useUpdateAutomationConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: Partial<AutomationConfig>) => {
      const response = await api.patch<AutomationConfig>(
        '/api/v1/banking/payment-automation/config',
        config
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paymentAutomationKeys.config() });
    },
  });
}
