/**
 * Contract Hooks - TanStack Query Hooks fuer Vertragsmanagement
 *
 * Features:
 * - Infinite Scroll fuer Vertragsliste
 * - Optimistische Updates
 * - Cache-Invalidierung
 * - Prefetching
 */

import { useCallback } from 'react';
import {
  useQuery,
  useMutation,
  useQueryClient,
  useInfiniteQuery,
  type UseQueryOptions,
  type UseInfiniteQueryOptions,
} from '@tanstack/react-query';
import { toast } from 'sonner';
import { contractsService, type ICalExportParams } from '@/lib/api/services/contracts';
import type {
  Contract,
  ContractDetail,
  ContractListResponse,
  ContractListParams,
  ContractCreateRequest,
  ContractUpdateRequest,
  ContractSummary,
  DeadlineListResponse,
  ContractTimeline,
  ContractMilestone,
  MilestoneCreateRequest,
  MilestoneUpdateRequest,
  ContractRenewalOption,
  RenewalOptionDecision,
  ContractAmendment,
  AmendmentCreateRequest,
  AmendmentUpdateRequest,
} from '../types/contract-types';

// =============================================================================
// Query Keys
// =============================================================================

export const contractQueryKeys = {
  all: ['contracts'] as const,
  lists: () => [...contractQueryKeys.all, 'list'] as const,
  list: (params: ContractListParams) => [...contractQueryKeys.lists(), params] as const,
  infinite: (params: ContractListParams) => [...contractQueryKeys.lists(), 'infinite', params] as const,
  details: () => [...contractQueryKeys.all, 'detail'] as const,
  detail: (id: string) => [...contractQueryKeys.details(), id] as const,
  timeline: (id: string) => [...contractQueryKeys.detail(id), 'timeline'] as const,
  summary: () => [...contractQueryKeys.all, 'summary'] as const,
  deadlines: (days?: number) => [...contractQueryKeys.all, 'deadlines', days ?? 90] as const,
  renewalOptions: (contractId: string) => [...contractQueryKeys.detail(contractId), 'renewals'] as const,
  icalExport: (params?: ICalExportParams) => [...contractQueryKeys.all, 'ical', params] as const,
};

// =============================================================================
// List Queries
// =============================================================================

/**
 * Hook fuer Vertraege mit Pagination
 */
export function useContracts(
  params: ContractListParams = {},
  options?: Omit<UseQueryOptions<ContractListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: contractQueryKeys.list(params),
    queryFn: () => contractsService.listContracts(params),
    ...options,
  });
}

/**
 * Hook fuer Vertraege mit Infinite Scroll
 */
export function useContractsInfinite(
  params: Omit<ContractListParams, 'offset'> = {},
  options?: Omit<
    UseInfiniteQueryOptions<ContractListResponse, Error, ContractListResponse>,
    'queryKey' | 'queryFn' | 'getNextPageParam' | 'initialPageParam'
  >
) {
  const pageSize = params.limit ?? 20;

  return useInfiniteQuery({
    queryKey: contractQueryKeys.infinite(params),
    queryFn: ({ pageParam = 0 }) =>
      contractsService.listContracts({
        ...params,
        offset: pageParam,
        limit: pageSize,
      }),
    getNextPageParam: (lastPage) => {
      const nextOffset = (lastPage.offset ?? 0) + pageSize;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
    initialPageParam: 0,
    ...options,
  });
}

// =============================================================================
// Detail Queries
// =============================================================================

/**
 * Hook fuer einzelnen Vertrag
 */
export function useContract(
  id: string,
  options?: Omit<UseQueryOptions<ContractDetail>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: contractQueryKeys.detail(id),
    queryFn: () => contractsService.getContract(id),
    enabled: !!id,
    ...options,
  });
}

/**
 * Hook fuer Vertrags-Timeline
 */
export function useContractTimeline(
  id: string,
  options?: Omit<UseQueryOptions<ContractTimeline>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: contractQueryKeys.timeline(id),
    queryFn: () => contractsService.getContractTimeline(id),
    enabled: !!id,
    ...options,
  });
}

// =============================================================================
// Summary & Statistics
// =============================================================================

/**
 * Hook fuer Vertragsstatistiken
 */
export function useContractSummary(options?: Omit<UseQueryOptions<ContractSummary>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractQueryKeys.summary(),
    queryFn: contractsService.getSummary,
    staleTime: 1000 * 60 * 5, // 5 Minuten Cache
    ...options,
  });
}

/**
 * Hook fuer anstehende Fristen
 */
export function useUpcomingDeadlines(
  daysAhead: number = 90,
  options?: Omit<UseQueryOptions<DeadlineListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: contractQueryKeys.deadlines(daysAhead),
    queryFn: () => contractsService.getUpcomingDeadlines(daysAhead),
    staleTime: 1000 * 60 * 5, // 5 Minuten Cache
    ...options,
  });
}

// =============================================================================
// Renewal Options
// =============================================================================

/**
 * Hook fuer Verlaengerungsoptionen
 */
export function useRenewalOptions(
  contractId: string,
  options?: Omit<UseQueryOptions<ContractRenewalOption[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: contractQueryKeys.renewalOptions(contractId),
    queryFn: () => contractsService.listRenewalOptions(contractId),
    enabled: !!contractId,
    ...options,
  });
}

// =============================================================================
// Contract Mutations
// =============================================================================

/**
 * Hook zum Erstellen eines Vertrags
 */
export function useCreateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: contractsService.createContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.all });
      toast.success('Vertrag erfolgreich erstellt');
    },
    onError: () => {
      toast.error('Fehler beim Erstellen des Vertrags');
    },
  });
}

/**
 * Hook zum Aktualisieren eines Vertrags
 */
export function useUpdateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ContractUpdateRequest }) =>
      contractsService.updateContract(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.summary() });
      toast.success('Vertrag erfolgreich aktualisiert');
    },
    onError: () => {
      toast.error('Fehler beim Aktualisieren des Vertrags');
    },
  });
}

/**
 * Hook zum Loeschen eines Vertrags
 */
export function useDeleteContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: contractsService.deleteContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.all });
      toast.success('Vertrag erfolgreich gelöscht');
    },
    onError: () => {
      toast.error('Fehler beim Löschen des Vertrags');
    },
  });
}

// =============================================================================
// Milestone Mutations
// =============================================================================

/**
 * Hook zum Erstellen eines Meilensteins
 */
export function useCreateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, data }: { contractId: string; data: MilestoneCreateRequest }) =>
      contractsService.createMilestone(contractId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Meilenstein erstellt');
    },
    onError: () => {
      toast.error('Fehler beim Erstellen des Meilensteins');
    },
  });
}

/**
 * Hook zum Aktualisieren eines Meilensteins
 */
export function useUpdateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      milestoneId,
      data,
    }: {
      contractId: string;
      milestoneId: string;
      data: MilestoneUpdateRequest;
    }) => contractsService.updateMilestone(contractId, milestoneId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Meilenstein aktualisiert');
    },
    onError: () => {
      toast.error('Fehler beim Aktualisieren des Meilensteins');
    },
  });
}

/**
 * Hook zum Abschliessen eines Meilensteins
 */
export function useCompleteMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      milestoneId,
      notes,
    }: {
      contractId: string;
      milestoneId: string;
      notes?: string;
    }) => contractsService.completeMilestone(contractId, milestoneId, notes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.deadlines() });
      toast.success('Meilenstein abgeschlossen');
    },
    onError: () => {
      toast.error('Fehler beim Abschliessen des Meilensteins');
    },
  });
}

/**
 * Hook zum Loeschen eines Meilensteins
 */
export function useDeleteMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, milestoneId }: { contractId: string; milestoneId: string }) =>
      contractsService.deleteMilestone(contractId, milestoneId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Meilenstein gelöscht');
    },
    onError: () => {
      toast.error('Fehler beim Löschen des Meilensteins');
    },
  });
}

// =============================================================================
// Renewal Decision
// =============================================================================

/**
 * Hook fuer Verlaengerungsentscheidung
 */
export function useRenewalDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      optionId,
      data,
    }: {
      contractId: string;
      optionId: string;
      data: RenewalOptionDecision;
    }) => contractsService.makeRenewalDecision(contractId, optionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.renewalOptions(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.summary() });
      const isExercise = variables.data.decision === 'exercise';
      toast.success(isExercise ? 'Verlängerung ausgeübt' : 'Verlängerung abgelehnt');
    },
    onError: () => {
      toast.error('Fehler bei der Verlängerungsentscheidung');
    },
  });
}

// =============================================================================
// Amendment Mutations
// =============================================================================

/**
 * Hook zum Erstellen eines Nachtrags
 */
export function useCreateAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, data }: { contractId: string; data: AmendmentCreateRequest }) =>
      contractsService.createAmendment(contractId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Nachtrag erstellt');
    },
    onError: () => {
      toast.error('Fehler beim Erstellen des Nachtrags');
    },
  });
}

/**
 * Hook zum Aktualisieren eines Nachtrags
 */
export function useUpdateAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      amendmentId,
      data,
    }: {
      contractId: string;
      amendmentId: string;
      data: AmendmentUpdateRequest;
    }) => contractsService.updateAmendment(contractId, amendmentId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Nachtrag aktualisiert');
    },
    onError: () => {
      toast.error('Fehler beim Aktualisieren des Nachtrags');
    },
  });
}

/**
 * Hook zum Loeschen eines Nachtrags
 */
export function useDeleteAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, amendmentId }: { contractId: string; amendmentId: string }) =>
      contractsService.deleteAmendment(contractId, amendmentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Nachtrag gelöscht');
    },
    onError: () => {
      toast.error('Fehler beim Löschen des Nachtrags');
    },
  });
}

/**
 * Hook zum Genehmigen eines Nachtrags
 */
export function useApproveAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, amendmentId }: { contractId: string; amendmentId: string }) =>
      contractsService.approveAmendment(contractId, amendmentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractQueryKeys.detail(variables.contractId) });
      toast.success('Nachtrag genehmigt');
    },
    onError: () => {
      toast.error('Fehler beim Genehmigen des Nachtrags');
    },
  });
}

// =============================================================================
// iCal Export
// =============================================================================

/**
 * Hook fuer iCal-Export
 */
export function useICalExport() {
  return useMutation({
    mutationFn: async (params: ICalExportParams = {}) => {
      const blob = await contractsService.downloadICal(params);
      // Trigger Download
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `vertragsfristen-${new Date().toISOString().split('T')[0]}.ics`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },
    onSuccess: () => {
      toast.success('Kalender-Export erfolgreich');
    },
    onError: () => {
      toast.error('Fehler beim Kalender-Export');
    },
  });
}

// =============================================================================
// Bulk Operations
// =============================================================================

/**
 * Hook fuer Bulk-Export
 */
export function useBulkExport() {
  return useMutation({
    mutationFn: async ({
      contractIds,
      format = 'xlsx',
    }: {
      contractIds: string[];
      format?: 'csv' | 'xlsx' | 'pdf';
    }) => {
      const blob = await contractsService.bulkExport(contractIds, format);
      // Trigger Download
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `vertraege-export-${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },
    onSuccess: () => {
      toast.success('Export erfolgreich');
    },
    onError: () => {
      toast.error('Fehler beim Export');
    },
  });
}

/**
 * Hook fuer Bulk-Erinnerungen
 */
export function useBulkSendReminders() {
  return useMutation({
    mutationFn: contractsService.bulkSendReminders,
    onSuccess: (result) => {
      if (result.failed > 0) {
        toast.warning(`${result.sent} Erinnerungen gesendet, ${result.failed} fehlgeschlagen`);
      } else {
        toast.success(`${result.sent} Erinnerungen gesendet`);
      }
    },
    onError: () => {
      toast.error('Fehler beim Senden der Erinnerungen');
    },
  });
}

// =============================================================================
// Utility Hooks
// =============================================================================

/**
 * Hook zum Invalidieren aller Contract-Queries
 */
export function useInvalidateContractQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: contractQueryKeys.all });
  }, [queryClient]);
}

/**
 * Combined Hook fuer die Contracts Page
 */
export function useContractsPage(params: ContractListParams = {}) {
  const contractsQuery = useContracts(params);
  const summaryQuery = useContractSummary();
  const deadlinesQuery = useUpcomingDeadlines(90);

  return {
    contracts: contractsQuery.data?.items ?? [],
    total: contractsQuery.data?.total ?? 0,
    isLoading: contractsQuery.isLoading,
    isError: contractsQuery.isError,
    isFetching: contractsQuery.isFetching,
    refetch: contractsQuery.refetch,
    summary: summaryQuery.data,
    isLoadingSummary: summaryQuery.isLoading,
    deadlines: deadlinesQuery.data?.items ?? [],
    isLoadingDeadlines: deadlinesQuery.isLoading,
  };
}

/**
 * Combined Hook fuer Contract Detail Page
 */
export function useContractDetail(id: string) {
  const contractQuery = useContract(id);
  const timelineQuery = useContractTimeline(id);
  const renewalOptionsQuery = useRenewalOptions(id);

  return {
    contract: contractQuery.data,
    isLoading: contractQuery.isLoading,
    isError: contractQuery.isError,
    timeline: timelineQuery.data,
    isLoadingTimeline: timelineQuery.isLoading,
    renewalOptions: renewalOptionsQuery.data ?? [],
    isLoadingRenewalOptions: renewalOptionsQuery.isLoading,
  };
}

/**
 * Combined Mutations Hook
 */
export function useContractMutations() {
  const createContract = useCreateContract();
  const updateContract = useUpdateContract();
  const deleteContract = useDeleteContract();
  const renewalDecision = useRenewalDecision();
  const icalExport = useICalExport();

  return {
    createContract,
    updateContract,
    deleteContract,
    renewalDecision,
    icalExport,
    isLoading:
      createContract.isPending ||
      updateContract.isPending ||
      deleteContract.isPending ||
      renewalDecision.isPending,
  };
}
