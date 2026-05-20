/**
 * TanStack Query Hooks für Budget Management
 *
 * Zentrale Hooks für Budget-Verwaltung mit Kostenstellen
 * Konsistente Query-Keys und wiederverwendbare Hooks
 *
 * Phase 2.1 der Feature-Roadmap (Januar 2026)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  budgetService,
  type BudgetFilter,
  type BudgetCreateRequest,
  type BudgetLineCreateRequest,
  type AllocationCreateRequest,
  type KostenstelleCreateRequest,
  type AllocationSource,
  type AlertSeverity,
} from '@/lib/api/services/budgets';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_SEMI_STATIC } from '@/lib/api/query-config';

// ==================== Stale Time Konfiguration ====================

const STALE_TIMES = {
  kostenstellen: QUERY_SEMI_STATIC.staleTime, // 5min - Kostenstellen ändern sich selten
  budgets: QUERY_STANDARD.staleTime,          // 60s - Budgets können sich durch Buchungen ändern
  budgetList: QUERY_STANDARD.staleTime,       // 60s - Liste kann sich durch neue Budgets ändern
  summary: QUERY_VOLATILE.staleTime,          // 30s - Summary ändert sich mit Buchungen
  lines: QUERY_STANDARD.staleTime,            // 60s - Positionen ändern sich selten
  allocations: QUERY_VOLATILE.staleTime,      // 30s - Zuweisungen können schnell kommen
  variance: QUERY_STANDARD.staleTime,         // 60s - Report muss nicht realtime sein
  alerts: QUERY_VOLATILE.staleTime,           // 30s - Alerts sollten schnell angezeigt werden
} as const;

// ==================== Query Keys ====================

export const budgetQueryKeys = {
  all: ['budgets'] as const,

  // Kostenstellen
  kostenstellen: () => [...budgetQueryKeys.all, 'kostenstellen'] as const,
  kostenstellenList: (parentId?: string, activeOnly?: boolean) =>
    [...budgetQueryKeys.kostenstellen(), 'list', parentId, activeOnly] as const,
  kostenstellenTree: () => [...budgetQueryKeys.kostenstellen(), 'tree'] as const,

  // Budgets
  budgets: () => [...budgetQueryKeys.all, 'budgets'] as const,
  budgetList: (filter?: BudgetFilter, page?: number, pageSize?: number) =>
    [...budgetQueryKeys.budgets(), 'list', filter, page, pageSize] as const,
  budgetDetail: (id: string, includeLines?: boolean) =>
    [...budgetQueryKeys.budgets(), 'detail', id, includeLines] as const,
  budgetSummary: (id: string) =>
    [...budgetQueryKeys.budgets(), 'summary', id] as const,

  // Budget Lines
  lines: (budgetId: string) =>
    [...budgetQueryKeys.all, 'lines', budgetId] as const,
  lineList: (budgetId: string, kostenstelleId?: string, category?: string) =>
    [...budgetQueryKeys.lines(budgetId), 'list', kostenstelleId, category] as const,

  // Allocations
  allocations: (budgetId: string) =>
    [...budgetQueryKeys.all, 'allocations', budgetId] as const,
  allocationList: (budgetId: string, params?: { budgetLineId?: string; source?: AllocationSource }) =>
    [...budgetQueryKeys.allocations(budgetId), 'list', params?.budgetLineId, params?.source] as const,

  // Variance Report
  varianceReport: (budgetId: string) =>
    [...budgetQueryKeys.all, 'variance', budgetId] as const,

  // Alerts
  alerts: () => [...budgetQueryKeys.all, 'alerts'] as const,
  alertList: (params?: { budgetId?: string; severity?: AlertSeverity }) =>
    [...budgetQueryKeys.alerts(), 'list', params?.budgetId, params?.severity] as const,
};

// ==================== Kostenstellen Hooks ====================

/**
 * Kostenstellen-Liste abrufen
 */
export function useKostenstellen(params?: { parentId?: string; activeOnly?: boolean }) {
  return useQuery({
    queryKey: budgetQueryKeys.kostenstellenList(params?.parentId, params?.activeOnly),
    queryFn: () => budgetService.listKostenstellen(params),
    staleTime: STALE_TIMES.kostenstellen,
  });
}

/**
 * Kostenstellen-Baum abrufen
 */
export function useKostenstellenTree() {
  return useQuery({
    queryKey: budgetQueryKeys.kostenstellenTree(),
    queryFn: () => budgetService.getKostenstelleTree(),
    staleTime: STALE_TIMES.kostenstellen,
  });
}

/**
 * Kostenstelle erstellen
 */
export function useCreateKostenstelle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: KostenstelleCreateRequest) => budgetService.createKostenstelle(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.kostenstellen() });
    },
  });
}

// ==================== Budget Hooks ====================

/**
 * Budget-Liste abrufen
 */
export function useBudgets(filter?: BudgetFilter, page = 0, pageSize = 20) {
  return useQuery({
    queryKey: budgetQueryKeys.budgetList(filter, page, pageSize),
    queryFn: () => budgetService.listBudgets(filter, page, pageSize),
    staleTime: STALE_TIMES.budgetList,
  });
}

/**
 * Einzelnes Budget abrufen
 */
export function useBudget(budgetId: string, includeLines = true) {
  return useQuery({
    queryKey: budgetQueryKeys.budgetDetail(budgetId, includeLines),
    queryFn: () => budgetService.getBudget(budgetId, includeLines),
    staleTime: STALE_TIMES.budgets,
    enabled: !!budgetId,
  });
}

/**
 * Budget-Zusammenfassung abrufen
 */
export function useBudgetSummary(budgetId: string) {
  return useQuery({
    queryKey: budgetQueryKeys.budgetSummary(budgetId),
    queryFn: () => budgetService.getBudgetSummary(budgetId),
    staleTime: STALE_TIMES.summary,
    enabled: !!budgetId,
  });
}

/**
 * Budget erstellen
 */
export function useCreateBudget() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: BudgetCreateRequest) => budgetService.createBudget(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgets() });
    },
  });
}

/**
 * Budget aktivieren
 */
export function useActivateBudget() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (budgetId: string) => budgetService.activateBudget(budgetId),
    onSuccess: (_data, budgetId) => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetDetail(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgets() });
    },
  });
}

/**
 * Budget schließen
 */
export function useCloseBudget() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (budgetId: string) => budgetService.closeBudget(budgetId),
    onSuccess: (_data, budgetId) => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetDetail(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgets() });
    },
  });
}

// ==================== Budget Line Hooks ====================

/**
 * Budget-Positionen abrufen
 */
export function useBudgetLines(
  budgetId: string,
  kostenstelleId?: string,
  category?: string
) {
  return useQuery({
    queryKey: budgetQueryKeys.lineList(budgetId, kostenstelleId, category),
    queryFn: () => budgetService.listBudgetLines(budgetId, kostenstelleId, category),
    staleTime: STALE_TIMES.lines,
    enabled: !!budgetId,
  });
}

/**
 * Budget-Position erstellen
 */
export function useCreateBudgetLine(budgetId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: BudgetLineCreateRequest) =>
      budgetService.createBudgetLine(budgetId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.lines(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetDetail(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetSummary(budgetId) });
    },
  });
}

// ==================== Allocation Hooks ====================

/**
 * Zuweisungen abrufen
 */
export function useAllocations(
  budgetId: string,
  params?: {
    budgetLineId?: string;
    source?: AllocationSource;
    page?: number;
    pageSize?: number;
  }
) {
  return useQuery({
    queryKey: budgetQueryKeys.allocationList(budgetId, params),
    queryFn: () => budgetService.listAllocations(budgetId, params),
    staleTime: STALE_TIMES.allocations,
    enabled: !!budgetId,
  });
}

/**
 * Zuweisung erstellen
 */
export function useCreateAllocation(budgetId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: AllocationCreateRequest) =>
      budgetService.createAllocation(budgetId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.allocations(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.lines(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetSummary(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetDetail(budgetId) });
    },
  });
}

// ==================== Variance Report Hooks ====================

/**
 * Abweichungsbericht abrufen
 */
export function useVarianceReport(budgetId: string) {
  return useQuery({
    queryKey: budgetQueryKeys.varianceReport(budgetId),
    queryFn: () => budgetService.getVarianceReport(budgetId),
    staleTime: STALE_TIMES.variance,
    enabled: !!budgetId,
  });
}

// ==================== Alert Hooks ====================

/**
 * Alerts abrufen
 */
export function useBudgetAlerts(params?: {
  budgetId?: string;
  severity?: AlertSeverity;
  acknowledgedOnly?: boolean;
}) {
  return useQuery({
    queryKey: budgetQueryKeys.alertList(params),
    queryFn: () => budgetService.listAlerts(params),
    staleTime: STALE_TIMES.alerts,
  });
}

/**
 * Alert bestätigen
 */
export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (alertId: string) => budgetService.acknowledgeAlert(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.alerts() });
    },
  });
}

// ==================== Utility Hooks ====================

/**
 * Invalidiert alle Budget-relevanten Queries
 */
export function useInvalidateBudgetQueries() {
  const queryClient = useQueryClient();

  return {
    invalidateAll: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.all });
    },
    invalidateBudget: (budgetId: string) => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetDetail(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.budgetSummary(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.lines(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.allocations(budgetId) });
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.varianceReport(budgetId) });
    },
    invalidateKostenstellen: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.kostenstellen() });
    },
    invalidateAlerts: () => {
      queryClient.invalidateQueries({ queryKey: budgetQueryKeys.alerts() });
    },
  };
}
