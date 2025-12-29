/**
 * Zentrale Query Hooks für Spesenabrechnung
 * Konsistente Query-Keys und wiederverwendbare Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { expenseService } from '@/lib/api/services/expenses';
import type {
  ExpenseReportCreate,
  ExpenseReportUpdate,
  ExpenseItemCreate,
  ExpenseItemUpdate,
  ExpenseReportApproveRequest,
  ExpenseReportRejectRequest,
  ExpenseReportPayRequest,
  PerDiemCalculateRequest,
  MileageCalculateRequest,
  ExpenseReportStatus,
} from '@/types/models/expense';

// ==================== Stale Time Konfiguration ====================

const STALE_TIMES = {
  reports: 2 * 60 * 1000,      // 2 Minuten - Reports können sich ändern
  calculations: 60 * 60 * 1000, // 1 Stunde - Berechnungen ändern sich selten
} as const;

// ==================== Query Keys ====================

export const expenseQueryKeys = {
  all: ['expenses'] as const,

  // Reports
  reports: () => [...expenseQueryKeys.all, 'reports'] as const,
  reportList: (params?: {
    employee_id?: string;
    status?: ExpenseReportStatus;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }) => [...expenseQueryKeys.reports(), 'list', params] as const,
  reportDetail: (id: string) =>
    [...expenseQueryKeys.reports(), 'detail', id] as const,

  // Calculations
  calculations: () => [...expenseQueryKeys.all, 'calculations'] as const,
  perDiem: (params: PerDiemCalculateRequest) =>
    [...expenseQueryKeys.calculations(), 'per-diem', params] as const,
  mileage: (params: MileageCalculateRequest) =>
    [...expenseQueryKeys.calculations(), 'mileage', params] as const,
};

// ==================== Report Hooks ====================

export function useExpenseReports(params?: {
  employee_id?: string;
  status?: ExpenseReportStatus;
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: expenseQueryKeys.reportList(params),
    queryFn: () => expenseService.listReports(params),
    staleTime: STALE_TIMES.reports,
  });
}

export function useExpenseReport(reportId: string) {
  return useQuery({
    queryKey: expenseQueryKeys.reportDetail(reportId),
    queryFn: () => expenseService.getReport(reportId),
    staleTime: STALE_TIMES.reports,
    enabled: !!reportId,
  });
}

export function useCreateExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ExpenseReportCreate) => expenseService.createReport(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function useUpdateExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ExpenseReportUpdate }) =>
      expenseService.updateReport(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(id) });
    },
  });
}

export function useDeleteExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reportId: string) => expenseService.deleteReport(reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

// ==================== Item Hooks ====================

export function useAddExpenseItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ reportId, data }: { reportId: string; data: ExpenseItemCreate }) =>
      expenseService.addItem(reportId, data),
    onSuccess: (_, { reportId }) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(reportId) });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function useUpdateExpenseItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: string; data: ExpenseItemUpdate }) =>
      expenseService.updateItem(itemId, data),
    onSuccess: () => {
      // Invalidate all reports since we don't know which report this item belongs to
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function useDeleteExpenseItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => expenseService.deleteItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

// ==================== Workflow Hooks ====================

export function useSubmitExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reportId: string) => expenseService.submitReport(reportId),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(report.id) });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function useApproveExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ reportId, data }: { reportId: string; data: ExpenseReportApproveRequest }) =>
      expenseService.approveReport(reportId, data),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(report.id) });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function useRejectExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ reportId, data }: { reportId: string; data: ExpenseReportRejectRequest }) =>
      expenseService.rejectReport(reportId, data),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(report.id) });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
    },
  });
}

export function usePayExpenseReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ reportId, data }: { reportId: string; data: ExpenseReportPayRequest }) =>
      expenseService.payReport(reportId, data),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reportDetail(report.id) });
      queryClient.invalidateQueries({ queryKey: expenseQueryKeys.reports() });
      // Also invalidate cash if a cash entry was created
      queryClient.invalidateQueries({ queryKey: ['cash'] });
    },
  });
}

// ==================== Calculator Hooks ====================

export function usePerDiemCalculation(params: PerDiemCalculateRequest, enabled = true) {
  return useQuery({
    queryKey: expenseQueryKeys.perDiem(params),
    queryFn: () => expenseService.calculatePerDiem(params),
    staleTime: STALE_TIMES.calculations,
    enabled: enabled && !!params.travel_start && !!params.travel_end,
  });
}

export function useMileageCalculation(params: MileageCalculateRequest, enabled = true) {
  return useQuery({
    queryKey: expenseQueryKeys.mileage(params),
    queryFn: () => expenseService.calculateMileage(params),
    staleTime: STALE_TIMES.calculations,
    enabled: enabled && params.kilometers > 0,
  });
}

// ==================== Calculator Mutations (for forms) ====================

export function useCalculatePerDiem() {
  return useMutation({
    mutationFn: (data: PerDiemCalculateRequest) => expenseService.calculatePerDiem(data),
  });
}

export function useCalculateMileage() {
  return useMutation({
    mutationFn: (data: MileageCalculateRequest) => expenseService.calculateMileage(data),
  });
}
