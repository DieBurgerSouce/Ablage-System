import { useQuery } from '@tanstack/react-query';
import {
    mlDashboardApi,
    mlDashboardQueryKeys,
    type MLDashboardData,
    type LearningPoint,
    type ErrorStatistics,
    type CorrectionImpact,
    type ModelPerformance,
} from '../api/ml-dashboard-api';

/**
 * Hook für vollständige Dashboard-Daten.
 */
export function useMLDashboard(months: number = 6) {
    return useQuery<MLDashboardData>({
        queryKey: mlDashboardQueryKeys.dashboard(months),
        queryFn: () => mlDashboardApi.getDashboard(months),
        staleTime: 300000, // 5 Minuten
    });
}

/**
 * Hook für Lernkurve.
 */
export function useLearningCurve(months: number = 6) {
    return useQuery<LearningPoint[]>({
        queryKey: mlDashboardQueryKeys.learningCurve(months),
        queryFn: () => mlDashboardApi.getLearningCurve(months),
        staleTime: 300000, // 5 Minuten
    });
}

/**
 * Hook für Fehlerstatistiken.
 */
export function useErrorStats() {
    return useQuery<ErrorStatistics>({
        queryKey: mlDashboardQueryKeys.errorStats(),
        queryFn: () => mlDashboardApi.getErrorStats(),
        staleTime: 300000, // 5 Minuten
    });
}

/**
 * Hook für Korrektur-Auswirkungen.
 */
export function useCorrectionImpact(months: number = 6) {
    return useQuery<CorrectionImpact>({
        queryKey: mlDashboardQueryKeys.correctionImpact(months),
        queryFn: () => mlDashboardApi.getCorrectionImpact(months),
        staleTime: 300000, // 5 Minuten
    });
}

/**
 * Hook für Modell-Performance.
 */
export function useModelPerformance() {
    return useQuery<ModelPerformance[]>({
        queryKey: mlDashboardQueryKeys.modelPerformance(),
        queryFn: () => mlDashboardApi.getModelPerformance(),
        staleTime: 300000, // 5 Minuten
    });
}
