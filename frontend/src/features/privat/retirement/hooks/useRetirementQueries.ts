/**
 * React Query Hooks fuer Altersvorsorge-Planung
 *
 * Bietet:
 * - Rentenluecken-Berechnung
 * - Monte-Carlo-Simulation
 * - Entnahmestrategien
 * - Riester/Ruerup-Optimierung
 * - bAV-Analyse
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { retirementService } from '@/lib/api/services/retirement';
import type {
  PensionGapResult,
  MonteCarloResult,
  WithdrawalPlan,
  RiesterOptimization,
  BAVAnalysis,
  RetirementSummary,
  PensionGapRequest,
  MonteCarloRequest,
  WithdrawalPlanRequest,
  RiesterOptimizationRequest,
  BAVAnalysisRequest,
  RetirementSummaryRequest,
} from '@/lib/api/services/retirement';

// ==================== Query Keys ====================

export const retirementQueryKeys = {
  all: ['retirement'] as const,
  summary: (spaceId: string) => [...retirementQueryKeys.all, 'summary', spaceId] as const,
  pensionGap: (spaceId: string) => [...retirementQueryKeys.all, 'pension-gap', spaceId] as const,
  monteCarlo: (spaceId: string) => [...retirementQueryKeys.all, 'monte-carlo', spaceId] as const,
  withdrawalPlan: (spaceId: string) => [...retirementQueryKeys.all, 'withdrawal-plan', spaceId] as const,
  riester: (spaceId: string) => [...retirementQueryKeys.all, 'riester', spaceId] as const,
  bav: (spaceId: string) => [...retirementQueryKeys.all, 'bav', spaceId] as const,
};

// ==================== Pension Gap Hook ====================

export function usePensionGap(
  spaceId: string,
  request: PensionGapRequest | null,
  options?: Omit<UseQueryOptions<PensionGapResult>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.pensionGap(spaceId), request],
    queryFn: () => retirementService.calculatePensionGap(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...options,
  });
}

export function useCalculatePensionGap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: PensionGapRequest }) =>
      retirementService.calculatePensionGap(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData(retirementQueryKeys.pensionGap(spaceId), data);
      queryClient.invalidateQueries({ queryKey: retirementQueryKeys.summary(spaceId) });
    },
  });
}

// ==================== Monte Carlo Hook ====================

export function useMonteCarlo(
  spaceId: string,
  request: MonteCarloRequest | null,
  options?: Omit<UseQueryOptions<MonteCarloResult>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.monteCarlo(spaceId), request],
    queryFn: () => retirementService.runMonteCarlo(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useRunMonteCarlo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: MonteCarloRequest }) =>
      retirementService.runMonteCarlo(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData(
        [...retirementQueryKeys.monteCarlo(spaceId), data],
        data
      );
    },
  });
}

// ==================== Withdrawal Plan Hook ====================

export function useWithdrawalPlan(
  spaceId: string,
  request: WithdrawalPlanRequest | null,
  options?: Omit<UseQueryOptions<WithdrawalPlan>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.withdrawalPlan(spaceId), request],
    queryFn: () => retirementService.createWithdrawalPlan(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useCreateWithdrawalPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: WithdrawalPlanRequest }) =>
      retirementService.createWithdrawalPlan(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData(
        [...retirementQueryKeys.withdrawalPlan(spaceId), data],
        data
      );
    },
  });
}

// ==================== Riester Optimization Hook ====================

export function useRiesterOptimization(
  spaceId: string,
  request: RiesterOptimizationRequest | null,
  options?: Omit<UseQueryOptions<RiesterOptimization>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.riester(spaceId), request],
    queryFn: () => retirementService.optimizeRiester(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 10 * 60 * 1000, // 10 Minuten
    ...options,
  });
}

export function useOptimizeRiester() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: RiesterOptimizationRequest }) =>
      retirementService.optimizeRiester(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData([...retirementQueryKeys.riester(spaceId), data], data);
      queryClient.invalidateQueries({ queryKey: retirementQueryKeys.summary(spaceId) });
    },
  });
}

// ==================== BAV Analysis Hook ====================

export function useBAVAnalysis(
  spaceId: string,
  request: BAVAnalysisRequest | null,
  options?: Omit<UseQueryOptions<BAVAnalysis>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.bav(spaceId), request],
    queryFn: () => retirementService.analyzeBAV(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 10 * 60 * 1000,
    ...options,
  });
}

export function useAnalyzeBAV() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: BAVAnalysisRequest }) =>
      retirementService.analyzeBAV(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData([...retirementQueryKeys.bav(spaceId), data], data);
      queryClient.invalidateQueries({ queryKey: retirementQueryKeys.summary(spaceId) });
    },
  });
}

// ==================== Retirement Summary Hook ====================

export function useRetirementSummary(
  spaceId: string,
  request: RetirementSummaryRequest | null,
  options?: Omit<UseQueryOptions<RetirementSummary>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...retirementQueryKeys.summary(spaceId), request],
    queryFn: () => retirementService.getRetirementSummary(spaceId, request!),
    enabled: !!spaceId && !!request,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useGenerateRetirementSummary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, request }: { spaceId: string; request: RetirementSummaryRequest }) =>
      retirementService.getRetirementSummary(spaceId, request),
    onSuccess: (data, { spaceId }) => {
      queryClient.setQueryData(retirementQueryKeys.summary(spaceId), data);
    },
  });
}

// ==================== Utility Hooks ====================

export function useCalculatePensionPoints() {
  return useMutation({
    mutationFn: ({ grossAnnualIncome, year }: { grossAnnualIncome: number; year?: number }) =>
      retirementService.calculatePensionPoints(grossAnnualIncome, year),
  });
}

export function useCalculateStatutoryPension() {
  return useMutation({
    mutationFn: ({
      totalPensionPoints,
      earlyRetirementMonths,
    }: {
      totalPensionPoints: number;
      earlyRetirementMonths?: number;
    }) => retirementService.calculateStatutoryPension(totalPensionPoints, earlyRetirementMonths),
  });
}
