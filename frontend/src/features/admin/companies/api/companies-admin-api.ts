/**
 * Companies Admin API
 *
 * React Query Hooks fuer die Firmenverwaltung im Admin-Bereich.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companyService } from '@/lib/api/services/companies';
import type {
  CompanyDashboardResponse,
  CompanyComparisonResponse,
  CompanyMetrics,
} from '@/lib/api/services/companies';
import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
  UserCompany,
  UserCompanyCreate,
  UserCompanyUpdate,
} from '@/types/models/company';

// ==================== Query Keys ====================

export const companyAdminKeys = {
  all: ['companies', 'admin'] as const,
  list: (params?: { include_inactive?: boolean }) =>
    [...companyAdminKeys.all, 'list', params] as const,
  detail: (id: string) => [...companyAdminKeys.all, 'detail', id] as const,
  users: (companyId: string) =>
    [...companyAdminKeys.all, 'users', companyId] as const,
  dashboard: (params?: { include_inactive?: boolean }) =>
    [...companyAdminKeys.all, 'dashboard', params] as const,
  comparison: (metric: string, companyIds?: string) =>
    [...companyAdminKeys.all, 'comparison', metric, companyIds] as const,
  metrics: (companyId: string) =>
    [...companyAdminKeys.all, 'metrics', companyId] as const,
};

// ==================== Company Hooks ====================

/**
 * Alle Firmen laden (Admin-Ansicht mit inaktiven)
 */
export function useCompaniesAdmin(params?: { include_inactive?: boolean }) {
  return useQuery({
    queryKey: companyAdminKeys.list(params),
    queryFn: () =>
      companyService.list({
        include_inactive: params?.include_inactive ?? true,
        limit: 100,
      }),
    staleTime: 30 * 1000, // 30 Sekunden
  });
}

/**
 * Einzelne Firma laden
 */
export function useCompanyDetail(companyId: string | null) {
  return useQuery({
    queryKey: companyAdminKeys.detail(companyId ?? ''),
    queryFn: () => companyService.get(companyId!),
    enabled: !!companyId,
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Firma erstellen
 */
export function useCreateCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CompanyCreate) => companyService.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: companyAdminKeys.all });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}

/**
 * Firma aktualisieren
 */
export function useUpdateCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CompanyUpdate }) =>
      companyService.update(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: companyAdminKeys.all });
      queryClient.invalidateQueries({
        queryKey: companyAdminKeys.detail(variables.id),
      });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}

/**
 * Firma loeschen
 */
export function useDeleteCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => companyService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: companyAdminKeys.all });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}

// ==================== User Management Hooks ====================

/**
 * Benutzer einer Firma laden
 */
export function useCompanyUsers(companyId: string | null) {
  return useQuery({
    queryKey: companyAdminKeys.users(companyId ?? ''),
    queryFn: () => companyService.listUsers(companyId!),
    enabled: !!companyId,
    staleTime: 30 * 1000,
  });
}

/**
 * Benutzer zu Firma hinzufuegen
 */
export function useAddUserToCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      companyId,
      data,
    }: {
      companyId: string;
      data: UserCompanyCreate;
    }) => companyService.addUser(companyId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: companyAdminKeys.users(variables.companyId),
      });
    },
  });
}

/**
 * Benutzerrolle aktualisieren
 */
export function useUpdateCompanyUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      companyId,
      userId,
      data,
    }: {
      companyId: string;
      userId: string;
      data: UserCompanyUpdate;
    }) => companyService.updateUser(companyId, userId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: companyAdminKeys.users(variables.companyId),
      });
    },
  });
}

/**
 * Benutzer aus Firma entfernen
 */
export function useRemoveUserFromCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ companyId, userId }: { companyId: string; userId: string }) =>
      companyService.removeUser(companyId, userId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: companyAdminKeys.users(variables.companyId),
      });
    },
  });
}

// ==================== Dashboard Hooks ====================

/**
 * Multi-Firma Dashboard laden
 */
export function useCompanyDashboard(params?: { include_inactive?: boolean }) {
  return useQuery({
    queryKey: companyAdminKeys.dashboard(params),
    queryFn: () => companyService.getDashboard(params),
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Firmen-Vergleich laden
 */
export function useCompanyComparison(metric: string, companyIds?: string) {
  return useQuery({
    queryKey: companyAdminKeys.comparison(metric, companyIds),
    queryFn: () =>
      companyService.getComparison({
        metric,
        company_ids: companyIds,
      }),
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Metriken einer einzelnen Firma laden
 */
export function useCompanyMetrics(companyId: string | null) {
  return useQuery({
    queryKey: companyAdminKeys.metrics(companyId ?? ''),
    queryFn: () => companyService.getMetrics(companyId!),
    enabled: !!companyId,
    staleTime: 60 * 1000, // 1 Minute
  });
}
