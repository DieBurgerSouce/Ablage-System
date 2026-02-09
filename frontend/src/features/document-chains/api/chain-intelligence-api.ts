/**
 * Chain Intelligence API Service
 *
 * Kommuniziert mit den /api/v1/document-chains/v2/intelligence Endpoints
 * fuer proaktive Kettenluecken-Erkennung und Vorschlaege.
 */

import { apiClient } from '@/lib/api/client';
import { ChainApiError } from './chain-api';
import { AxiosError } from 'axios';

// ==================== Types ====================

export type GapSeverity = 'info' | 'warning' | 'critical';

export interface ChainGap {
  chainId: string;
  chainName: string;
  expectedType: string;
  afterDocument: string;
  daysOverdue: number;
  severity: GapSeverity;
  suggestedMatches: string[];
}

export interface ChainGapBackend {
  chain_id: string;
  chain_name: string;
  expected_type: string;
  after_document: string;
  days_overdue: number;
  severity: GapSeverity;
  suggested_matches: string[];
}

export interface OrphanDocument {
  documentId: string;
  filename: string;
  documentType: string;
  documentDate?: string;
  referenceNumbers: Record<string, string>;
  potentialChainIds: string[];
  matchConfidence: number;
}

export interface OrphanDocumentBackend {
  document_id: string;
  filename: string;
  document_type: string;
  document_date?: string;
  reference_numbers: Record<string, string>;
  potential_chain_ids: string[];
  match_confidence: number;
}

export interface ChainIntelligenceReport {
  totalChains: number;
  completeChains: number;
  chainsWithGaps: number;
  gaps: ChainGap[];
  orphanCount: number;
  suggestedNewChains: Record<string, string>[];
  scanTimestamp: string;
  averageCompletion: number;
}

export interface ChainIntelligenceReportBackend {
  total_chains: number;
  complete_chains: number;
  chains_with_gaps: number;
  gaps: ChainGapBackend[];
  orphan_count: number;
  suggested_new_chains: Record<string, string>[];
  scan_timestamp: string;
  average_completion: number;
}

export interface ChainSuggestionsResponse {
  chainId: string;
  suggestionCount: number;
  suggestions: ChainGap[];
}

// ==================== Transformers ====================

function transformGap(gap: ChainGapBackend): ChainGap {
  return {
    chainId: gap.chain_id,
    chainName: gap.chain_name,
    expectedType: gap.expected_type,
    afterDocument: gap.after_document,
    daysOverdue: gap.days_overdue,
    severity: gap.severity,
    suggestedMatches: gap.suggested_matches,
  };
}

function transformOrphan(orphan: OrphanDocumentBackend): OrphanDocument {
  return {
    documentId: orphan.document_id,
    filename: orphan.filename,
    documentType: orphan.document_type,
    documentDate: orphan.document_date,
    referenceNumbers: orphan.reference_numbers,
    potentialChainIds: orphan.potential_chain_ids,
    matchConfidence: orphan.match_confidence,
  };
}

function transformReport(report: ChainIntelligenceReportBackend): ChainIntelligenceReport {
  return {
    totalChains: report.total_chains,
    completeChains: report.complete_chains,
    chainsWithGaps: report.chains_with_gaps,
    gaps: report.gaps.map(transformGap),
    orphanCount: report.orphan_count,
    suggestedNewChains: report.suggested_new_chains,
    scanTimestamp: report.scan_timestamp,
    averageCompletion: report.average_completion,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;
    throw new ChainApiError(`${context}: ${message}`, statusCode, error);
  }
  throw new ChainApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== API Service ====================

export const chainIntelligenceService = {
  /**
   * Ruft den Ketten-Intelligenz-Bericht ab (Luecken, Statistiken)
   */
  getChainGaps: async (): Promise<ChainIntelligenceReport> => {
    try {
      const response = await apiClient.get<ChainIntelligenceReportBackend>(
        '/document-chains/v2/intelligence/gaps'
      );
      return transformReport(response.data);
    } catch (error) {
      handleApiError(error, 'Kettenluecken laden');
    }
  },

  /**
   * Ruft verwaiste Dokumente ab
   */
  getOrphanDocuments: async (): Promise<OrphanDocument[]> => {
    try {
      const response = await apiClient.get<{
        orphan_count: number;
        orphans: OrphanDocumentBackend[];
      }>('/document-chains/v2/intelligence/orphans');
      return response.data.orphans.map(transformOrphan);
    } catch (error) {
      handleApiError(error, 'Verwaiste Dokumente laden');
    }
  },

  /**
   * Ruft Vervollstaendigungs-Vorschlaege fuer eine Kette ab
   */
  getChainSuggestions: async (chainId: string): Promise<ChainSuggestionsResponse> => {
    try {
      const response = await apiClient.get<{
        chain_id: string;
        suggestion_count: number;
        suggestions: ChainGapBackend[];
      }>(`/document-chains/v2/intelligence/${chainId}/suggestions`);

      return {
        chainId: response.data.chain_id,
        suggestionCount: response.data.suggestion_count,
        suggestions: response.data.suggestions.map(transformGap),
      };
    } catch (error) {
      handleApiError(error, 'Kettenvorschlaege laden');
    }
  },
};
