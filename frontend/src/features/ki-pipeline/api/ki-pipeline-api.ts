/**
 * KI-Pipeline API Service
 * German enterprise document processing - AI intelligence layer
 */

import { apiClient } from '@/lib/api/client';
import type {
  FieldConfidence,
  LearningProfile,
  CrossDocumentMatch,
  DocumentSummary,
  PriceDeviation,
  LearnFromCorrectionsRequest,
  ExtractWithConfidenceRequest,
  ExtractWithConfidenceResponse,
  KIPipelineStatistics,
  FieldAccuracyStats,
  SupplierAccuracyStats,
} from '../types/ki-pipeline-types';

const BASE_PATH = '/ki-pipeline';

// ============= Error Messages =============

const ERROR_MESSAGES = {
  fetchConfidences: 'Fehler beim Laden der Konfidenzwerte',
  fetchLearningProfiles: 'Fehler beim Laden der Lernprofile',
  extractWithConfidence: 'Fehler bei der Extraktion mit Konfidenz',
  fetchCrossMatches: 'Fehler beim Laden der Dokumentenverknüpfungen',
  fetchSummary: 'Fehler beim Laden der Zusammenfassung',
  learnFromCorrections: 'Fehler beim Speichern der Korrekturen',
  fetchPriceDeviations: 'Fehler beim Laden der Preisabweichungen',
  fetchStatistics: 'Fehler beim Laden der Statistiken',
  fetchFieldAccuracy: 'Fehler beim Laden der Feldgenauigkeit',
  fetchSupplierAccuracy: 'Fehler beim Laden der Lieferantengenauigkeit',
};

// ============= API Methods =============

export const kiPipelineApi = {
  /**
   * Get field-level confidence scores for a document
   */
  async getConfidences(documentId: string): Promise<FieldConfidence[]> {
    try {
      const { data } = await apiClient.get<FieldConfidence[]>(
        `${BASE_PATH}/confidences/${documentId}`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchConfidences);
    }
  },

  /**
   * Get learning profiles (per supplier/document type)
   */
  async getLearningProfiles(params?: {
    entity_type?: 'supplier' | 'customer' | 'document_type';
    entity_id?: string;
    limit?: number;
  }): Promise<LearningProfile[]> {
    try {
      const { data } = await apiClient.get<LearningProfile[]>(
        `${BASE_PATH}/learning-profiles`,
        { params }
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchLearningProfiles);
    }
  },

  /**
   * Extract document fields with confidence scoring
   */
  async extractWithConfidence(
    request: ExtractWithConfidenceRequest
  ): Promise<ExtractWithConfidenceResponse> {
    try {
      const { data } = await apiClient.post<ExtractWithConfidenceResponse>(
        `${BASE_PATH}/extract-with-confidence`,
        request
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.extractWithConfidence);
    }
  },

  /**
   * Get cross-document matches (Bestellung-Lieferschein-Rechnung chain)
   */
  async getCrossMatches(documentId: string): Promise<CrossDocumentMatch[]> {
    try {
      const { data } = await apiClient.get<CrossDocumentMatch[]>(
        `${BASE_PATH}/cross-matches/${documentId}`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchCrossMatches);
    }
  },

  /**
   * Get AI-generated document summary
   */
  async getSummary(documentId: string): Promise<DocumentSummary> {
    try {
      const { data } = await apiClient.get<DocumentSummary>(
        `${BASE_PATH}/summaries/${documentId}`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchSummary);
    }
  },

  /**
   * Submit user corrections for learning
   */
  async learnFromCorrections(
    request: LearnFromCorrectionsRequest
  ): Promise<{ success: boolean; message: string }> {
    try {
      const { data } = await apiClient.post<{
        success: boolean;
        message: string;
      }>(`${BASE_PATH}/learn-from-corrections`, request);
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.learnFromCorrections);
    }
  },

  /**
   * Get price deviation alerts
   */
  async getPriceDeviations(params?: {
    min_deviation_percent?: number;
    limit?: number;
  }): Promise<PriceDeviation[]> {
    try {
      const { data } = await apiClient.get<PriceDeviation[]>(
        `${BASE_PATH}/price-deviations`,
        { params }
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchPriceDeviations);
    }
  },

  /**
   * Get overall KI pipeline statistics
   */
  async getStatistics(): Promise<KIPipelineStatistics> {
    try {
      const { data } = await apiClient.get<KIPipelineStatistics>(
        `${BASE_PATH}/statistics`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchStatistics);
    }
  },

  /**
   * Get per-field accuracy statistics
   */
  async getFieldAccuracy(): Promise<FieldAccuracyStats[]> {
    try {
      const { data } = await apiClient.get<FieldAccuracyStats[]>(
        `${BASE_PATH}/field-accuracy`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchFieldAccuracy);
    }
  },

  /**
   * Get supplier-specific accuracy statistics
   */
  async getSupplierAccuracy(entityId: string): Promise<SupplierAccuracyStats> {
    try {
      const { data } = await apiClient.get<SupplierAccuracyStats>(
        `${BASE_PATH}/supplier-accuracy/${entityId}`
      );
      return data;
    } catch (error) {
      throw new Error(ERROR_MESSAGES.fetchSupplierAccuracy);
    }
  },
};
