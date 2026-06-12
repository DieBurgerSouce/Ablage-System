/**
 * Company Context Hook
 *
 * Verwaltet die aktuelle Firma und stellt sie der gesamten App zur Verfügung.
 */

import * as React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companyService } from '@/lib/api/services/companies';
import { QUERY_SEMI_STATIC } from '@/lib/api/query-config';
import type { Company } from '@/types/models/company';

// ==================== Query Keys ====================

export const companyQueryKeys = {
  all: ['companies'] as const,
  list: (params?: { skip?: number; limit?: number; include_inactive?: boolean }) =>
    [...companyQueryKeys.all, 'list', params] as const,
  current: () => [...companyQueryKeys.all, 'current'] as const,
  detail: (id: string) => [...companyQueryKeys.all, 'detail', id] as const,
  users: (companyId: string) => [...companyQueryKeys.all, 'users', companyId] as const,
};

// ==================== Context ====================

interface CompanyContextValue {
  currentCompany: Company | null;
  companies: Company[];
  isLoading: boolean;
  error: Error | null;
  switchCompany: (companyId: string) => Promise<void>;
  refetchCompanies: () => void;
}

const CompanyContext = React.createContext<CompanyContextValue | undefined>(undefined);

// ==================== Provider ====================

interface CompanyProviderProps {
  children: React.ReactNode;
}

export function CompanyProvider({ children }: CompanyProviderProps) {
  const queryClient = useQueryClient();

  // Lade Firmenliste
  const {
    data: companiesData,
    isLoading: isLoadingCompanies,
    error: companiesError,
    refetch: refetchCompanies,
  } = useQuery({
    queryKey: companyQueryKeys.list(),
    queryFn: () => companyService.list(),
    staleTime: QUERY_SEMI_STATIC.staleTime, // 5min
  });

  // Lade aktuelle Firma
  const {
    data: currentCompany,
    isLoading: isLoadingCurrent,
    error: currentError,
  } = useQuery({
    queryKey: companyQueryKeys.current(),
    queryFn: () => companyService.getCurrent(),
    staleTime: QUERY_SEMI_STATIC.staleTime, // 5min
  });

  // Firma wechseln
  const switchMutation = useMutation({
    mutationFn: (companyId: string) => companyService.switchCompany(companyId),
    onSuccess: () => {
      // Invalidiere alle firmenabhängigen Queries
      queryClient.invalidateQueries({ queryKey: companyQueryKeys.current() });
      queryClient.invalidateQueries({ queryKey: companyQueryKeys.list() });
      // Invalidiere Cash und Expenses
      queryClient.invalidateQueries({ queryKey: ['cash'] });
      queryClient.invalidateQueries({ queryKey: ['expenses'] });
    },
  });

  const switchCompany = async (companyId: string) => {
    await switchMutation.mutateAsync(companyId);
  };

  const value: CompanyContextValue = {
    currentCompany: currentCompany ?? null,
    companies: companiesData?.items ?? [],
    isLoading: isLoadingCompanies || isLoadingCurrent,
    error: (companiesError as Error) ?? (currentError as Error) ?? null,
    switchCompany,
    refetchCompanies: () => refetchCompanies(),
  };

  return (
    <CompanyContext.Provider value={value}>
      {children}
    </CompanyContext.Provider>
  );
}

// ==================== Hook ====================

export function useCompanyContext() {
  const context = React.useContext(CompanyContext);
  if (context === undefined) {
    throw new Error('useCompanyContext muss innerhalb eines CompanyProvider verwendet werden');
  }
  return context;
}

// ==================== Convenience Hooks ====================

export function useCurrentCompany() {
  const { currentCompany, isLoading, error } = useCompanyContext();
  return { company: currentCompany, isLoading, error };
}

export function useCompanies() {
  const { companies, isLoading, error, refetchCompanies } = useCompanyContext();
  return { companies, isLoading, error, refetch: refetchCompanies };
}

export function useSwitchCompany() {
  const { switchCompany } = useCompanyContext();
  return switchCompany;
}
