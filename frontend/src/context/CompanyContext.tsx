/**
 * CompanyContext - Multi-Mandanten State Management
 *
 * Verwaltet den Zustand der aktuellen Firma:
 * - currentCompany: Die aktuell ausgewählte Firma
 * - companies: Alle verfügbaren Firmen des Benutzers
 * - switchCompany: Firma wechseln
 * - isLoading: Ladezustand
 *
 * Der X-Company-ID Header wird automatisch bei allen API-Requests gesetzt.
 */

import { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companyService } from '@/lib/api/services/companies';
import { useAuth } from '@/lib/auth/AuthContext';
import { QUERY_SEMI_STATIC } from '@/lib/api/query-config';
import type { Company, CompanyListResponse } from '@/types/models/company';

// ==================== Types ====================

interface CompanyContextType {
    /** Die aktuell ausgewählte Firma */
    currentCompany: Company | null;
    /** Alle verfügbaren Firmen des Benutzers */
    companies: Company[];
    /** Anzahl der Firmen */
    companyCount: number;
    /** Firma wechseln */
    switchCompany: (companyId: string) => Promise<void>;
    /** Ladezustand */
    isLoading: boolean;
    /** Fehler beim Laden */
    error: Error | null;
    /** Firmen neu laden */
    refetch: () => Promise<void>;
    /** Ob mehrere Firmen verfügbar sind */
    hasMultipleCompanies: boolean;
}

const CompanyContext = createContext<CompanyContextType | undefined>(undefined);

// ==================== Query Keys ====================

export const companyQueryKeys = {
    all: ['companies'] as const,
    list: () => [...companyQueryKeys.all, 'list'] as const,
    current: () => [...companyQueryKeys.all, 'current'] as const,
    detail: (id: string) => [...companyQueryKeys.all, 'detail', id] as const,
};

// ==================== Provider ====================

interface CompanyProviderProps {
    children: ReactNode;
}

export function CompanyProvider({ children }: CompanyProviderProps) {
    const queryClient = useQueryClient();
    const { isAuthenticated, user } = useAuth();
    const [switchError, setSwitchError] = useState<Error | null>(null);

    // Firmen laden
    const {
        data: listData,
        isLoading: isListLoading,
        error: listError,
        refetch: refetchList,
    } = useQuery({
        queryKey: companyQueryKeys.list(),
        queryFn: () => companyService.list({ include_inactive: false }),
        enabled: isAuthenticated,
        staleTime: QUERY_SEMI_STATIC.staleTime, // 5min
        refetchOnWindowFocus: false,
    });

    // Aktuelle Firma laden
    const {
        data: currentCompany,
        isLoading: isCurrentLoading,
        error: currentError,
        refetch: refetchCurrent,
    } = useQuery({
        queryKey: companyQueryKeys.current(),
        queryFn: () => companyService.getCurrent(),
        enabled: isAuthenticated,
        staleTime: QUERY_SEMI_STATIC.staleTime, // 5min
        refetchOnWindowFocus: false,
    });

    // Firma wechseln Mutation
    const switchMutation = useMutation({
        mutationFn: (companyId: string) => companyService.switchCompany(companyId),
        onSuccess: (newCompany) => {
            // Cache aktualisieren
            queryClient.setQueryData(companyQueryKeys.current(), newCompany);
            // Company-ID im sessionStorage speichern für API-Client Header
            sessionStorage.setItem('current_company_id', newCompany.id);
            // Alle dokument-bezogenen Queries invalidieren da sich die Daten ändern
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            queryClient.invalidateQueries({ queryKey: ['cash'] });
            queryClient.invalidateQueries({ queryKey: ['expenses'] });
            queryClient.invalidateQueries({ queryKey: ['banking'] });
            queryClient.invalidateQueries({ queryKey: ['finance'] });
            setSwitchError(null);
        },
        onError: (error) => {
            setSwitchError(error as Error);
        },
    });

    // switchCompany Callback
    const switchCompany = useCallback(async (companyId: string) => {
        await switchMutation.mutateAsync(companyId);
    }, [switchMutation]);

    // refetch Callback
    const refetch = useCallback(async () => {
        await Promise.all([refetchList(), refetchCurrent()]);
    }, [refetchList, refetchCurrent]);

    // Beim initialen Laden: Company-ID im sessionStorage setzen
    useEffect(() => {
        if (currentCompany?.id) {
            sessionStorage.setItem('current_company_id', currentCompany.id);
        }
    }, [currentCompany?.id]);

    // Daten extrahieren - API returns 'items' (nicht 'companies')
    const companies = listData?.items ?? [];
    const companyCount = listData?.total ?? 0;
    const isLoading = isListLoading || isCurrentLoading || switchMutation.isPending;
    const error = listError ?? currentError ?? switchError;

    const value = useMemo<CompanyContextType>(
        () => ({
            currentCompany: currentCompany ?? null,
            companies,
            companyCount,
            switchCompany,
            isLoading,
            error: error as Error | null,
            refetch,
            hasMultipleCompanies: companyCount > 1,
        }),
        [currentCompany, companies, companyCount, switchCompany, isLoading, error, refetch]
    );

    return (
        <CompanyContext.Provider value={value}>
            {children}
        </CompanyContext.Provider>
    );
}

// ==================== Hooks ====================

/**
 * Hook to access company context
 * @throws Error if used outside CompanyProvider
 */
export function useCompany(): CompanyContextType {
    const context = useContext(CompanyContext);
    if (context === undefined) {
        throw new Error('useCompany must be used within a CompanyProvider');
    }
    return context;
}

/**
 * Hook that safely returns company context (or undefined if not in provider)
 * Useful for components that may or may not be inside the provider
 */
export function useCompanySafe(): CompanyContextType | null {
    const context = useContext(CompanyContext);
    return context ?? null;
}

/**
 * Hook to get the current company ID
 * Returns null if no company is selected
 */
export function useCurrentCompanyId(): string | null {
    const context = useCompanySafe();
    return context?.currentCompany?.id ?? null;
}
