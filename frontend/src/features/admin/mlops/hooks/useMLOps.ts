/**
 * MLOps Hooks
 *
 * Hooks für Model Registry und Retraining Management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// Types
// =============================================================================

export type ModelStatus = 'draft' | 'candidate' | 'active' | 'deprecated' | 'rolled_back' | 'archived';

export type ModelType =
  | 'ocr_confidence'
  | 'ocr_backend_router'
  | 'document_classifier'
  | 'entity_matcher'
  | 'extraction_model';

export type RetrainingTrigger = 'threshold' | 'scheduled' | 'drift' | 'manual' | 'ab_test_winner';
export type RetrainingStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface ModelMetadata {
  id: string;
  model_type: ModelType;
  version: string;
  status: ModelStatus;
  trained_at: string | null;
  training_samples: number;
  training_duration_seconds: number;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  custom_metrics: Record<string, number>;
  artifact_path: string | null;
  artifact_hash: string | null;
  artifact_size_bytes: number;
  parent_version: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  deployed_at: string | null;
  deprecated_at: string | null;
  rollback_reason: string | null;
  tags: string[];
  notes: string | null;
}

export interface ModelVersion {
  version: string;
  status: ModelStatus;
  accuracy: number | null;
  deployed_at: string | null;
}

export interface RetrainingConfig {
  feedback_threshold: number;
  feedback_window_hours: number;
  weekly_enabled: boolean;
  weekly_day: number;
  weekly_hour: number;
  drift_threshold: number;
  drift_check_interval_hours: number;
  min_training_samples: number;
  min_accuracy_improvement: number;
  min_hours_between_retrains: number;
}

export interface RetrainingJob {
  id: string;
  model_type: ModelType;
  trigger: RetrainingTrigger;
  status: RetrainingStatus;
  config: RetrainingConfig;
  training_samples: number;
  feedback_ids: string[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  old_version: string | null;
  new_version: string | null;
  accuracy_before: number | null;
  accuracy_after: number | null;
  error_message: string | null;
}

export interface MLOpsStats {
  total_models: number;
  active_models: number;
  pending_retraining: number;
  total_retraining_jobs: number;
  recent_jobs: RetrainingJob[];
  models_by_type: Record<ModelType, number>;
  average_accuracy: number;
}

// =============================================================================
// Query Keys
// =============================================================================

export const mlopsKeys = {
  all: ['mlops'] as const,
  stats: () => [...mlopsKeys.all, 'stats'] as const,
  models: () => [...mlopsKeys.all, 'models'] as const,
  modelsByType: (type: ModelType) => [...mlopsKeys.models(), type] as const,
  activeModel: (type: ModelType) => [...mlopsKeys.models(), type, 'active'] as const,
  jobs: () => [...mlopsKeys.all, 'jobs'] as const,
  jobDetail: (id: string) => [...mlopsKeys.jobs(), id] as const,
  config: () => [...mlopsKeys.all, 'config'] as const,
  performanceHistory: (type: ModelType) => [...mlopsKeys.all, 'history', type] as const,
};

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook zum Abrufen der MLOps Statistiken
 */
export function useMLOpsStats() {
  return useQuery({
    queryKey: mlopsKeys.stats(),
    queryFn: async () => {
      const response = await api.get<MLOpsStats>('/mlops/stats');
      return response.data;
    },
    staleTime: 30_000, // 30 Sekunden
  });
}

/**
 * Hook zum Abrufen aller Model-Versionen eines Typs
 */
export function useModelVersions(modelType: ModelType, status?: ModelStatus) {
  return useQuery({
    queryKey: mlopsKeys.modelsByType(modelType),
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('model_type', modelType);
      if (status) params.set('status', status);

      const response = await api.get<ModelVersion[]>(
        `/mlops/models/versions?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 60_000, // 1 Minute
  });
}

/**
 * Hook zum Abrufen des aktiven Models eines Typs
 */
export function useActiveModel(modelType: ModelType) {
  return useQuery({
    queryKey: mlopsKeys.activeModel(modelType),
    queryFn: async () => {
      const response = await api.get<ModelMetadata | null>(
        `/mlops/models/${modelType}/active`
      );
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Abrufen aller Retraining Jobs
 */
export function useRetrainingJobs(limit = 20) {
  return useQuery({
    queryKey: mlopsKeys.jobs(),
    queryFn: async () => {
      const response = await api.get<RetrainingJob[]>(
        `/mlops/retraining/jobs?limit=${limit}`
      );
      return response.data;
    },
    staleTime: 30_000,
  });
}

/**
 * Hook zum Abrufen der Retraining-Konfiguration
 */
export function useRetrainingConfig() {
  return useQuery({
    queryKey: mlopsKeys.config(),
    queryFn: async () => {
      const response = await api.get<RetrainingConfig>('/mlops/retraining/config');
      return response.data;
    },
    staleTime: 300_000, // 5 Minuten
  });
}

/**
 * Hook zum Aktualisieren der Retraining-Konfiguration
 */
export function useUpdateRetrainingConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: Partial<RetrainingConfig>) => {
      const response = await api.patch<RetrainingConfig>(
        '/mlops/retraining/config',
        config
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mlopsKeys.config() });
    },
  });
}

/**
 * Hook zum Abrufen der Performance-Historie
 */
export function usePerformanceHistory(modelType: ModelType, days = 30) {
  return useQuery({
    queryKey: mlopsKeys.performanceHistory(modelType),
    queryFn: async () => {
      const response = await api.get<
        Array<{
          version: string;
          accuracy: number | null;
          training_samples: number;
          created_at: string;
          status: ModelStatus;
        }>
      >(`/mlops/models/${modelType}/history?days=${days}`);
      return response.data;
    },
    staleTime: 300_000,
  });
}

/**
 * Hook zum Starten eines Retraining Jobs
 */
export function useStartRetraining() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      modelType,
      trigger = 'manual',
    }: {
      modelType: ModelType;
      trigger?: RetrainingTrigger;
    }) => {
      const response = await api.post<RetrainingJob>('/mlops/retraining/start', {
        model_type: modelType,
        trigger,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mlopsKeys.jobs() });
      queryClient.invalidateQueries({ queryKey: mlopsKeys.stats() });
    },
  });
}

/**
 * Hook zum Promoten eines Models zu Active
 */
export function usePromoteModel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      modelType,
      version,
    }: {
      modelType: ModelType;
      version: string;
    }) => {
      const response = await api.post<ModelMetadata>(
        `/mlops/models/${modelType}/promote`,
        { version }
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: mlopsKeys.modelsByType(variables.modelType) });
      queryClient.invalidateQueries({ queryKey: mlopsKeys.activeModel(variables.modelType) });
      queryClient.invalidateQueries({ queryKey: mlopsKeys.stats() });
    },
  });
}

/**
 * Hook zum Rollback eines Models
 */
export function useRollbackModel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      modelType,
      reason,
    }: {
      modelType: ModelType;
      reason: string;
    }) => {
      const response = await api.post<ModelMetadata | null>(
        `/mlops/models/${modelType}/rollback`,
        { reason }
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: mlopsKeys.modelsByType(variables.modelType) });
      queryClient.invalidateQueries({ queryKey: mlopsKeys.activeModel(variables.modelType) });
      queryClient.invalidateQueries({ queryKey: mlopsKeys.stats() });
    },
  });
}

// =============================================================================
// A/B Test Types and Hooks (Vision 2.0 Phase 3)
// =============================================================================

export type ABTestStatus = 'running' | 'completed' | 'cancelled';

export interface ABTest {
  id: string;
  name: string;
  model_type: ModelType;
  variant_a_version: string;
  variant_b_version: string;
  traffic_split: number; // 0-100, percentage for variant B
  status: ABTestStatus;
  started_at: string;
  completed_at: string | null;
  samples_a: number;
  samples_b: number;
  accuracy_a: number | null;
  accuracy_b: number | null;
  winner: 'a' | 'b' | null;
  significance_level: number | null;
  is_significant: boolean;
  created_by: string | null;
}

export interface RollbackEvent {
  id: string;
  model_type: ModelType;
  from_version: string;
  to_version: string;
  reason: string;
  rolled_back_at: string;
  rolled_back_by: string | null;
  accuracy_before: number | null;
  accuracy_after: number | null;
  auto_triggered: boolean;
}

/**
 * Hook zum Abrufen der A/B Tests
 */
export function useABTests(modelType?: ModelType, status?: ABTestStatus, limit = 10) {
  return useQuery({
    queryKey: [...mlopsKeys.all, 'ab-tests', modelType, status] as const,
    queryFn: async () => {
      const params = new URLSearchParams();
      if (modelType) params.set('model_type', modelType);
      if (status) params.set('status', status);
      params.set('limit', String(limit));

      const response = await api.get<ABTest[]>(
        `/ocr-learning/ab-tests?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 30_000,
  });
}

/**
 * Hook zum Abrufen der Rollback-Historie
 */
export function useRollbackHistory(modelType?: ModelType, limit = 20) {
  return useQuery({
    queryKey: [...mlopsKeys.all, 'rollback-history', modelType] as const,
    queryFn: async () => {
      const params = new URLSearchParams();
      if (modelType) params.set('model_type', modelType);
      params.set('limit', String(limit));

      const response = await api.get<RollbackEvent[]>(
        `/mlops/rollback-history?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Starten eines A/B Tests
 */
export function useStartABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      name,
      modelType,
      variantAVersion,
      variantBVersion,
      trafficSplit = 50,
    }: {
      name: string;
      modelType: ModelType;
      variantAVersion: string;
      variantBVersion: string;
      trafficSplit?: number;
    }) => {
      const response = await api.post<ABTest>('/ocr-learning/ab-test/start', {
        name,
        model_type: modelType,
        variant_a_version: variantAVersion,
        variant_b_version: variantBVersion,
        traffic_split: trafficSplit,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...mlopsKeys.all, 'ab-tests'] });
    },
  });
}

/**
 * Hook zum Beenden eines A/B Tests
 */
export function useEndABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ testId }: { testId: string }) => {
      const response = await api.post<ABTest>(
        `/ocr-learning/ab-test/${testId}/end`,
        {}
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...mlopsKeys.all, 'ab-tests'] });
    },
  });
}
