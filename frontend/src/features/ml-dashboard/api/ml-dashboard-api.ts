import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface LearningPoint {
    month?: string;
    recognition_rate: number;
    correction_count: number;
    avg_confidence_before: number;
    avg_confidence_after: number;
    improvement: number;
}

export interface ErrorType {
    category: string;
    description: string;
    count: number;
    percentage: number;
}

export interface ErrorStatistics {
    total_corrections: number;
    error_types: ErrorType[];
}

export interface CorrectionImpact {
    correction_count: number;
    avg_confidence_before: number;
    avg_confidence_after: number;
    accuracy_improvement_percent: number;
    summary: string;
}

export interface ModelPerformance {
    document_type: string;
    document_count: number;
    correction_count: number;
    avg_confidence: number;
    accuracy_rate: number;
}

export interface CategorizationAccuracy {
    total_documents: number;
    auto_categorized: number;
    accuracy_rate_percent: number;
    trend_percent: number;
    trend_direction: 'up' | 'down' | 'stable';
}

export interface MLDashboardData {
    period_months: number;
    period_start: string;
    period_end: string;
    learning_curve: LearningPoint[];
    error_statistics: ErrorStatistics;
    correction_impact: CorrectionImpact;
    model_performance_by_type: ModelPerformance[];
    categorization_accuracy: CategorizationAccuracy;
}

// Backend response types (snake_case)
interface LearningPointBackend {
    month?: string;
    recognition_rate: number;
    correction_count: number;
    avg_confidence_before: number;
    avg_confidence_after: number;
    improvement: number;
}

interface ErrorTypeBackend {
    category: string;
    description: string;
    count: number;
    percentage: number;
}

interface ErrorStatisticsBackend {
    total_corrections: number;
    error_types: ErrorTypeBackend[];
}

interface CorrectionImpactBackend {
    correction_count: number;
    avg_confidence_before: number;
    avg_confidence_after: number;
    accuracy_improvement_percent: number;
    summary: string;
}

interface ModelPerformanceBackend {
    document_type: string;
    document_count: number;
    correction_count: number;
    avg_confidence: number;
    accuracy_rate: number;
}

interface CategorizationAccuracyBackend {
    total_documents: number;
    auto_categorized: number;
    accuracy_rate_percent: number;
    trend_percent: number;
    trend_direction: string;
}

interface MLDashboardDataBackend {
    period_months: number;
    period_start: string;
    period_end: string;
    learning_curve: LearningPointBackend[];
    error_statistics: ErrorStatisticsBackend;
    correction_impact: CorrectionImpactBackend;
    model_performance_by_type: ModelPerformanceBackend[];
    categorization_accuracy: CategorizationAccuracyBackend;
}

// ==================== Transformers ====================

function transformLearningPoint(point: LearningPointBackend): LearningPoint {
    return {
        month: point.month,
        recognition_rate: point.recognition_rate,
        correction_count: point.correction_count,
        avg_confidence_before: point.avg_confidence_before,
        avg_confidence_after: point.avg_confidence_after,
        improvement: point.improvement,
    };
}

function transformErrorType(error: ErrorTypeBackend): ErrorType {
    return {
        category: error.category,
        description: error.description,
        count: error.count,
        percentage: error.percentage,
    };
}

function transformErrorStatistics(stats: ErrorStatisticsBackend): ErrorStatistics {
    return {
        total_corrections: stats.total_corrections,
        error_types: stats.error_types.map(transformErrorType),
    };
}

function transformCorrectionImpact(impact: CorrectionImpactBackend): CorrectionImpact {
    return {
        correction_count: impact.correction_count,
        avg_confidence_before: impact.avg_confidence_before,
        avg_confidence_after: impact.avg_confidence_after,
        accuracy_improvement_percent: impact.accuracy_improvement_percent,
        summary: impact.summary,
    };
}

function transformModelPerformance(perf: ModelPerformanceBackend): ModelPerformance {
    return {
        document_type: perf.document_type,
        document_count: perf.document_count,
        correction_count: perf.correction_count,
        avg_confidence: perf.avg_confidence,
        accuracy_rate: perf.accuracy_rate,
    };
}

function transformCategorizationAccuracy(acc: CategorizationAccuracyBackend): CategorizationAccuracy {
    return {
        total_documents: acc.total_documents,
        auto_categorized: acc.auto_categorized,
        accuracy_rate_percent: acc.accuracy_rate_percent,
        trend_percent: acc.trend_percent,
        trend_direction: acc.trend_direction as 'up' | 'down' | 'stable',
    };
}

function transformMLDashboardData(data: MLDashboardDataBackend): MLDashboardData {
    return {
        period_months: data.period_months,
        period_start: data.period_start,
        period_end: data.period_end,
        learning_curve: data.learning_curve.map(transformLearningPoint),
        error_statistics: transformErrorStatistics(data.error_statistics),
        correction_impact: transformCorrectionImpact(data.correction_impact),
        model_performance_by_type: data.model_performance_by_type.map(transformModelPerformance),
        categorization_accuracy: transformCategorizationAccuracy(data.categorization_accuracy),
    };
}

// ==================== API Functions ====================

/**
 * ML Dashboard API Service
 */
export const mlDashboardApi = {
    /**
     * Ruft alle Dashboard-Daten für den angegebenen Zeitraum ab.
     */
    getDashboard: async (months: number = 6): Promise<MLDashboardData> => {
        const response = await apiClient.get<MLDashboardDataBackend>(
            '/ml-dashboard/',
            {
                params: { months },
            }
        );

        return transformMLDashboardData(response.data);
    },

    /**
     * Ruft die Lernkurve für den angegebenen Zeitraum ab.
     */
    getLearningCurve: async (months: number = 6): Promise<LearningPoint[]> => {
        const response = await apiClient.get<LearningPointBackend[]>(
            '/ml-dashboard/learning-curve',
            {
                params: { months },
            }
        );

        return response.data.map(transformLearningPoint);
    },

    /**
     * Ruft die Fehlerstatistiken ab.
     */
    getErrorStats: async (): Promise<ErrorStatistics> => {
        const response = await apiClient.get<ErrorStatisticsBackend>(
            '/ml-dashboard/error-stats'
        );

        return transformErrorStatistics(response.data);
    },

    /**
     * Ruft die Korrektur-Auswirkungen für den angegebenen Zeitraum ab.
     */
    getCorrectionImpact: async (months: number = 6): Promise<CorrectionImpact> => {
        const response = await apiClient.get<CorrectionImpactBackend>(
            '/ml-dashboard/correction-impact',
            {
                params: { months },
            }
        );

        return transformCorrectionImpact(response.data);
    },

    /**
     * Ruft die Modell-Performance nach Dokumenttyp ab.
     */
    getModelPerformance: async (): Promise<ModelPerformance[]> => {
        const response = await apiClient.get<ModelPerformanceBackend[]>(
            '/ml-dashboard/model-performance'
        );

        return response.data.map(transformModelPerformance);
    },
};

/**
 * Query Keys für React Query
 */
export const mlDashboardQueryKeys = {
    all: ['ml-dashboard'] as const,
    dashboard: (months: number) => ['ml-dashboard', 'full', months] as const,
    learningCurve: (months: number) => ['ml-dashboard', 'learning-curve', months] as const,
    errorStats: () => ['ml-dashboard', 'error-stats'] as const,
    correctionImpact: (months: number) => ['ml-dashboard', 'correction-impact', months] as const,
    modelPerformance: () => ['ml-dashboard', 'model-performance'] as const,
};
