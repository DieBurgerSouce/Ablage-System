import { apiClient } from '../client';

// ==================== Types ====================

export interface TrainingSample {
    id: string;
    file_path: string;
    file_hash: string;
    thumbnail_path?: string;
    ground_truth_text?: string;
    language: string;
    document_type?: string;
    difficulty: string;
    has_umlauts: boolean;
    has_fraktur: boolean;
    has_tables: boolean;
    has_handwriting: boolean;
    has_stamps: boolean;
    has_signatures: boolean;
    umlaut_words: string[];
    extracted_fields: Record<string, string>;
    status: 'pending' | 'annotated' | 'verified' | 'rejected';
    annotated_by_id?: string;
    verified_by_id?: string;
    annotation_notes?: string;
    created_at: string;
    updated_at: string;
    annotated_at?: string;
    verified_at?: string;
}

export interface TrainingSampleListResponse {
    samples: TrainingSample[];
    total: number;
    limit: number;
    offset: number;
}

export interface BenchmarkResult {
    id: string;
    training_sample_id: string;
    backend_name: string;
    backend_version?: string;
    raw_text?: string;
    confidence_score?: number;
    cer?: number;
    wer?: number;
    umlaut_accuracy?: number;
    capitalization_accuracy?: number;
    field_accuracies?: Record<string, number>;
    error_patterns?: Record<string, unknown>;
    insertions: number;
    deletions: number;
    substitutions: number;
    processing_time_ms?: number;
    gpu_memory_mb?: number;
    processed_at: string;
}

export interface BackendComparison {
    backends: Record<string, {
        samples_processed: number;
        avg_cer?: number;
        avg_wer?: number;
        avg_umlaut_accuracy?: number;
        avg_processing_time_ms?: number;
        p50_cer?: number;
        p90_cer?: number;
        p95_cer?: number;
    }>;
    best_backend?: string;
    sample_count: number;
}

export interface TrainingBatch {
    id: string;
    name: string;
    description?: string;
    batch_type: string;
    stratification_config?: Record<string, unknown>;
    target_size: number;
    actual_size: number;
    status: 'draft' | 'ready' | 'in_progress' | 'completed';
    items_pending: number;
    items_completed: number;
    created_by_id?: string;
    created_at: string;
    updated_at: string;
    completed_at?: string;
}

export interface BatchItem {
    id: string;
    batch_id: string;
    training_sample_id: string;
    sequence_number: number;
    assigned_to_id?: string;
    status: 'pending' | 'in_progress' | 'completed' | 'skipped';
    validation_notes?: string;
    validation_time_seconds?: number;
    created_at: string;
    started_at?: string;
    completed_at?: string;
}

export interface Correction {
    id: string;
    document_id?: string;
    original_text: string;
    corrected_text: string;
    correction_type: string;
    field_corrected?: string;
    backend_used: string;
    confidence_before?: number;
    applies_to_training: boolean;
    learning_processed: boolean;
    learning_processed_at?: string;
    corrector_id?: string;
    created_at: string;
}

export interface TrainingOverviewStats {
    total_samples: number;
    verified_samples: number;
    pending_annotations: number;
    active_batches: number;
    recent_corrections_24h: number;
    unprocessed_corrections: number;
    samples_by_language: Record<string, number>;
    samples_by_document_type: Record<string, number>;
}

export interface BackendStats {
    backend_name: string;
    samples_processed: number;
    avg_cer?: number;
    avg_wer?: number;
    avg_umlaut_accuracy?: number;
    avg_processing_time_ms?: number;
}

export interface TrendDataPoint {
    date: string;
    backend: string;
    samples_processed: number;
    avg_cer?: number;
    avg_wer?: number;
    avg_umlaut_accuracy?: number;
    corrections_count: number;
}

export interface LearnedWeights {
    weights: Record<string, number>;
    last_updated: string;
    samples_analyzed: number;
    confidence: number;
}

export interface BackendInfo {
    name: string;
    display_name: string;
    requires_gpu: boolean;
    vram_gb: number;
    available: boolean;
}

// ==================== Training Service ====================

export const trainingService = {
    // Training Samples
    listSamples: async (params?: {
        status?: string;
        language?: string;
        document_type?: string;
        has_ground_truth?: boolean;
        verified_only?: boolean;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<TrainingSampleListResponse>('/training/samples', { params });
        return response.data;
    },

    getSample: async (id: string) => {
        const response = await apiClient.get<TrainingSample>(`/training/samples/${id}`);
        return response.data;
    },

    createSample: async (data: Partial<TrainingSample>) => {
        const response = await apiClient.post<TrainingSample>('/training/samples', data);
        return response.data;
    },

    updateSample: async (id: string, data: Partial<TrainingSample>) => {
        const response = await apiClient.put<TrainingSample>(`/training/samples/${id}`, data);
        return response.data;
    },

    verifySample: async (id: string, approved: boolean, notes?: string) => {
        const response = await apiClient.post<TrainingSample>(
            `/training/samples/${id}/verify`,
            null,
            { params: { approved, notes } }
        );
        return response.data;
    },

    deleteSample: async (id: string) => {
        await apiClient.delete(`/training/samples/${id}`);
    },

    // Benchmarks
    runBenchmark: async (data: {
        sample_ids: string[];
        backends?: string[];
        force_reprocess?: boolean;
    }) => {
        const response = await apiClient.post<{
            success: boolean;
            samples_processed: number;
            samples_failed: number;
            backends_used: string[];
            total_time_ms: number;
            task_id?: string;
        }>('/training/benchmarks/run', data);
        return response.data;
    },

    getBackendComparison: async (params?: {
        sample_ids?: string[];
        languages?: string[];
        document_types?: string[];
    }) => {
        const response = await apiClient.get<BackendComparison>('/training/benchmarks/compare', { params });
        return response.data;
    },

    getAvailableBackends: async () => {
        const response = await apiClient.get<{ backends: BackendInfo[] }>('/training/benchmarks/backends');
        return response.data.backends;
    },

    // Corrections (Self-Learning)
    createCorrection: async (data: {
        document_id?: string;
        original_text: string;
        corrected_text: string;
        correction_type: string;
        field_corrected?: string;
        backend_used: string;
        confidence_before?: number;
    }) => {
        const response = await apiClient.post<Correction>('/training/corrections', data);
        return response.data;
    },

    listCorrections: async (params?: {
        backend?: string;
        correction_type?: string;
        unprocessed_only?: boolean;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            corrections: Correction[];
            total: number;
            limit: number;
            offset: number;
        }>('/training/corrections', { params });
        return response.data;
    },

    // Training Batches
    listBatches: async (params?: {
        status?: string;
        limit?: number;
        offset?: number;
    }) => {
        const response = await apiClient.get<{
            batches: TrainingBatch[];
            total: number;
            limit: number;
            offset: number;
        }>('/training/batches', { params });
        return response.data;
    },

    createBatch: async (data: {
        name: string;
        description?: string;
        batch_type?: string;
        target_size: number;
        stratification_config?: {
            languages?: string[];
            document_types?: string[];
            difficulties?: string[];
            require_umlauts?: boolean;
            require_tables?: boolean;
            require_handwriting?: boolean;
        };
        auto_populate?: boolean;
    }) => {
        const response = await apiClient.post<TrainingBatch>('/training/batches', data);
        return response.data;
    },

    getBatch: async (id: string) => {
        const response = await apiClient.get<TrainingBatch & { items: BatchItem[] }>(`/training/batches/${id}`);
        return response.data;
    },

    startBatch: async (id: string) => {
        const response = await apiClient.post<TrainingBatch>(`/training/batches/${id}/start`);
        return response.data;
    },

    completeBatch: async (id: string) => {
        const response = await apiClient.post<TrainingBatch>(`/training/batches/${id}/complete`);
        return response.data;
    },

    getNextBatchItem: async (batchId: string) => {
        const response = await apiClient.get<BatchItem>(`/training/batches/${batchId}/next-item`);
        return response.data;
    },

    updateBatchItem: async (batchId: string, itemId: string, data: {
        status?: string;
        validation_notes?: string;
        validation_time_seconds?: number;
    }) => {
        const response = await apiClient.put<BatchItem>(`/training/batches/${batchId}/items/${itemId}`, data);
        return response.data;
    },

    // Statistics
    getOverviewStats: async () => {
        const response = await apiClient.get<TrainingOverviewStats>('/training/stats/overview');
        return response.data;
    },

    getBackendStats: async (days: number = 30) => {
        const response = await apiClient.get<BackendStats[]>('/training/stats/backends', { params: { days } });
        return response.data;
    },

    getTrendData: async (params?: { backend?: string; days?: number }) => {
        const response = await apiClient.get<{ data: TrendDataPoint[] }>('/training/stats/trends', { params });
        return response.data.data;
    },

    getLearnedWeights: async (forceRefresh: boolean = false) => {
        const response = await apiClient.get<LearnedWeights>('/training/stats/learned-weights', {
            params: { force_refresh: forceRefresh }
        });
        return response.data;
    },

    getBackendRecommendation: async (params?: {
        document_type?: string;
        has_umlauts?: boolean;
        has_tables?: boolean;
        fields_needed?: string[];
    }) => {
        const response = await apiClient.get<{
            recommended_backend: string;
            confidence: number;
        }>('/training/stats/backend-recommendation', { params });
        return response.data;
    },

    // Sample-spezifische Benchmarks abrufen
    getSampleBenchmarks: async (sampleId: string) => {
        const response = await apiClient.get<BenchmarkResult[]>(
            `/training/samples/${sampleId}/benchmarks`
        );
        return response.data;
    },
};
