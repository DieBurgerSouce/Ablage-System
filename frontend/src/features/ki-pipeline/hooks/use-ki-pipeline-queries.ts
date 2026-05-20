/**
 * KI-Pipeline React Query Hooks
 * German enterprise document processing - AI intelligence layer
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { kiPipelineApi } from '../api/ki-pipeline-api';
import type {
  LearnFromCorrectionsRequest,
  ExtractWithConfidenceRequest,
} from '../types/ki-pipeline-types';
import { toast } from 'sonner';

// ============= Query Keys =============

export const kiPipelineKeys = {
  all: ['ki-pipeline'] as const,
  confidences: (documentId: string) =>
    [...kiPipelineKeys.all, 'confidences', documentId] as const,
  learningProfiles: (filters?: {
    entity_type?: string;
    entity_id?: string;
  }) => [...kiPipelineKeys.all, 'learning-profiles', filters] as const,
  crossMatches: (documentId: string) =>
    [...kiPipelineKeys.all, 'cross-matches', documentId] as const,
  summary: (documentId: string) =>
    [...kiPipelineKeys.all, 'summary', documentId] as const,
  priceDeviations: (filters?: { min_deviation_percent?: number }) =>
    [...kiPipelineKeys.all, 'price-deviations', filters] as const,
  statistics: () => [...kiPipelineKeys.all, 'statistics'] as const,
  fieldAccuracy: () => [...kiPipelineKeys.all, 'field-accuracy'] as const,
  supplierAccuracy: (entityId: string) =>
    [...kiPipelineKeys.all, 'supplier-accuracy', entityId] as const,
};

// ============= Queries =============

/**
 * Get field-level confidence scores for a document
 */
export function useConfidences(documentId: string) {
  return useQuery({
    queryKey: kiPipelineKeys.confidences(documentId),
    queryFn: () => kiPipelineApi.getConfidences(documentId),
    enabled: !!documentId,
  });
}

/**
 * Get learning profiles (per supplier/document type)
 */
export function useLearningProfiles(params?: {
  entity_type?: 'supplier' | 'customer' | 'document_type';
  entity_id?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: kiPipelineKeys.learningProfiles(params),
    queryFn: () => kiPipelineApi.getLearningProfiles(params),
  });
}

/**
 * Get cross-document matches
 */
export function useCrossMatches(documentId: string) {
  return useQuery({
    queryKey: kiPipelineKeys.crossMatches(documentId),
    queryFn: () => kiPipelineApi.getCrossMatches(documentId),
    enabled: !!documentId,
  });
}

/**
 * Get AI-generated document summary
 */
export function useSummary(documentId: string) {
  return useQuery({
    queryKey: kiPipelineKeys.summary(documentId),
    queryFn: () => kiPipelineApi.getSummary(documentId),
    enabled: !!documentId,
  });
}

/**
 * Get price deviation alerts
 */
export function usePriceDeviations(params?: {
  min_deviation_percent?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: kiPipelineKeys.priceDeviations(params),
    queryFn: () => kiPipelineApi.getPriceDeviations(params),
  });
}

/**
 * Get overall KI pipeline statistics
 */
export function useStatistics() {
  return useQuery({
    queryKey: kiPipelineKeys.statistics(),
    queryFn: () => kiPipelineApi.getStatistics(),
  });
}

/**
 * Get per-field accuracy statistics
 */
export function useFieldAccuracy() {
  return useQuery({
    queryKey: kiPipelineKeys.fieldAccuracy(),
    queryFn: () => kiPipelineApi.getFieldAccuracy(),
  });
}

/**
 * Get supplier-specific accuracy statistics
 */
export function useSupplierAccuracy(entityId: string) {
  return useQuery({
    queryKey: kiPipelineKeys.supplierAccuracy(entityId),
    queryFn: () => kiPipelineApi.getSupplierAccuracy(entityId),
    enabled: !!entityId,
  });
}

// ============= Mutations =============

/**
 * Extract document with confidence scoring
 */
export function useExtractWithConfidence() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ExtractWithConfidenceRequest) =>
      kiPipelineApi.extractWithConfidence(request),
    onSuccess: (data) => {
      toast.success('Extraktion erfolgreich abgeschlossen');
      // Invalidate confidences for this document
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.confidences(data.document_id),
      });
      // Invalidate statistics
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.statistics(),
      });
    },
    onError: () => {
      toast.error('Fehler bei der Extraktion');
    },
  });
}

/**
 * Submit user corrections for learning
 */
export function useLearnFromCorrections() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: LearnFromCorrectionsRequest) =>
      kiPipelineApi.learnFromCorrections(request),
    onSuccess: (data, variables) => {
      toast.success(data.message || 'Korrekturen erfolgreich gespeichert');
      // Invalidate confidences for this document
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.confidences(variables.document_id),
      });
      // Invalidate learning profiles
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.learningProfiles(),
      });
      // Invalidate statistics
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.statistics(),
      });
      queryClient.invalidateQueries({
        queryKey: kiPipelineKeys.fieldAccuracy(),
      });
    },
    onError: () => {
      toast.error('Fehler beim Speichern der Korrekturen');
    },
  });
}
